/*
 * Copyright 2026 TAK-Solutions LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

package org.takmdm.agent.ui

import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.google.android.material.bottomnavigation.BottomNavigationView
import com.google.android.material.button.MaterialButton
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import org.takmdm.agent.BuildConfig
import org.takmdm.agent.R
import org.takmdm.agent.admin.MdmDeviceAdminReceiver
import org.takmdm.agent.admin.PolicyComplianceActivity
import org.takmdm.agent.core.AgentConfig
import org.takmdm.agent.files.FileDeployer
import org.takmdm.agent.install.AppInstaller
import org.takmdm.agent.net.DeviceIdentity
import org.takmdm.agent.permissions.PermissionRequirement
import org.takmdm.agent.sync.Reconciler
import org.takmdm.agent.sync.SyncScheduler
import org.takmdm.agent.ui.ConsoleViews.Tone
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * The ATLAS MDM status console.
 *
 * Deliberately not a launcher and not a kiosk shell — the agent stays out of the
 * way unless a policy asks for lockdown (F6). It exists so an operator standing
 * in front of a device can see why it is or is not managed, grant the handful of
 * permissions a Device Owner cannot grant itself, and force a sync — all without
 * USB debugging.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var config: AgentConfig
    private lateinit var installer: AppInstaller
    private lateinit var deployer: FileDeployer

    private val sectionFor = linkedMapOf(
        R.id.nav_device to R.id.section_device,
        R.id.nav_permissions to R.id.section_permissions,
        R.id.nav_apps to R.id.section_apps,
        R.id.nav_files to R.id.section_files,
        R.id.nav_policies to R.id.section_policies,
    )
    private var currentNav = R.id.nav_device
    private var syncing = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        config = AgentConfig(this)
        installer = AppInstaller(this)
        deployer = FileDeployer(this, config)

        findViewById<MaterialButton>(R.id.sync_now).setOnClickListener { syncNow() }

        findViewById<BottomNavigationView>(R.id.bottom_nav).apply {
            setOnItemSelectedListener { item -> show(item.itemId); true }
            selectedItemId = R.id.nav_device
        }

        SyncScheduler.startAll(this)
    }

    override fun onResume() {
        super.onResume()
        render()
    }

    private fun show(navId: Int) {
        currentNav = navId
        for ((nav, section) in sectionFor) {
            findViewById<View>(section).visibility = if (nav == navId) View.VISIBLE else View.GONE
        }
        render()
    }

    private fun render() {
        val desired = config.cachedDesiredState?.let { runCatching { JSONObject(it) }.getOrNull() }
        when (currentNav) {
            R.id.nav_device -> renderDevice(container(R.id.container_device))
            R.id.nav_permissions -> renderPermissions(container(R.id.container_permissions))
            R.id.nav_apps -> renderApps(container(R.id.container_apps), desired)
            R.id.nav_files -> renderFiles(container(R.id.container_files), desired)
            R.id.nav_policies -> renderPolicies(container(R.id.container_policies), desired)
        }
    }

    private fun container(id: Int): LinearLayout =
        findViewById<LinearLayout>(id).also { it.removeAllViews() }

    // --------------------------------------------------------------------- //
    // Device information + manual sync
    // --------------------------------------------------------------------- //

    private fun renderDevice(root: LinearLayout) {
        root.addView(ConsoleViews.sectionTitle(this, getString(R.string.section_device_title)))

        val enrolled = config.isEnrolled
        val owner = MdmDeviceAdminReceiver.isDeviceOwner(this)

        val enrolCard = ConsoleViews.card(this)
        ConsoleViews.body(enrolCard).apply {
            addRow(
                getString(R.string.label_enrollment),
                if (enrolled) getString(R.string.status_enrolled) else getString(R.string.status_not_enrolled),
                pill = if (enrolled) Tone.OK else Tone.ERROR,
            )
            addView(ConsoleViews.divider(this@MainActivity))
            addView(ConsoleViews.kv(this@MainActivity, getString(R.string.label_device_owner), owner.toString()))
            addView(ConsoleViews.kv(this@MainActivity, getString(R.string.label_device_name),
                config.deviceName ?: getString(R.string.value_not_set)))
            addView(ConsoleViews.kv(this@MainActivity, getString(R.string.label_device_id),
                config.deviceId ?: "—", mono = true))
            addView(ConsoleViews.kv(this@MainActivity, getString(R.string.label_serial), serial(), mono = true))
            addView(ConsoleViews.kv(this@MainActivity, getString(R.string.label_server),
                config.serverUrl ?: getString(R.string.value_not_set), mono = true))
            addView(ConsoleViews.kv(this@MainActivity, getString(R.string.label_agent_version), BuildConfig.VERSION_NAME))
        }
        root.addView(enrolCard)

        val syncCard = ConsoleViews.card(this)
        ConsoleViews.body(syncCard).apply {
            addView(ConsoleViews.kv(this@MainActivity, getString(R.string.label_last_sync), lastSyncText()))
            addView(ConsoleViews.kv(this@MainActivity, getString(R.string.label_state_version),
                "${config.stateVersion}  (applied ${config.appliedStateVersion})"))
            val err = config.lastError
            if (!err.isNullOrBlank() && err != "none") {
                addView(ConsoleViews.divider(this@MainActivity))
                addRow(getString(R.string.label_last_error), err, pill = null, valueTone = Tone.ERROR)
            }
            val applyErrors = config.lastApplyErrors
            if (applyErrors.isNotEmpty()) {
                addView(ConsoleViews.divider(this@MainActivity))
                addRow(
                    "Apply problems (${applyErrors.size})",
                    applyErrors.joinToString("\n\n"),
                    pill = null, valueTone = Tone.WARN,
                )
            }
            addView(MaterialButton(this@MainActivity).apply {
                text = getString(R.string.action_sync_now)
                isEnabled = !syncing
                if (syncing) text = getString(R.string.syncing)
                layoutParams = LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
                ).apply { topMargin = ConsoleViews.dp(this@MainActivity, 12) }
                setOnClickListener { syncNow() }
            })
        }
        root.addView(syncCard)

        // Re-enrol — the escape hatch for a device whose key or certificate is
        // unusable, so recovery does not need a factory reset.
        val reCard = ConsoleViews.card(this)
        ConsoleViews.body(reCard).apply {
            addView(TextView(this@MainActivity).apply {
                text = getString(R.string.reenroll_rationale)
                setTextAppearance(R.style.TextAppearance_Atlas_Value)
                textSize = 13f
            })
            val input = EditText(this@MainActivity).apply {
                hint = getString(R.string.reenroll_hint)
                setSingleLine()
                layoutParams = LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
                ).apply { topMargin = ConsoleViews.dp(this@MainActivity, 8) }
            }
            addView(input)
            addView(MaterialButton(this@MainActivity,
                null, com.google.android.material.R.attr.materialButtonOutlinedStyle).apply {
                text = getString(R.string.action_reenroll)
                layoutParams = LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
                ).apply { topMargin = ConsoleViews.dp(this@MainActivity, 8) }
                setOnClickListener { reEnroll(input.text.toString().trim()) }
            })
        }
        root.addView(reCard)
    }

    // --------------------------------------------------------------------- //
    // Permissions
    // --------------------------------------------------------------------- //

    private fun renderPermissions(root: LinearLayout) {
        root.addView(ConsoleViews.sectionTitle(this, getString(R.string.section_permissions_title)))

        for (req in PermissionRequirement.ALL) {
            val granted = req.isGranted(this)
            val intent = req.grantIntent(this)
            val card = ConsoleViews.card(this)
            ConsoleViews.body(card).apply {
                val head = LinearLayout(this@MainActivity).apply {
                    orientation = LinearLayout.HORIZONTAL
                    gravity = android.view.Gravity.CENTER_VERTICAL
                }
                head.addView(TextView(this@MainActivity).apply {
                    text = req.title
                    setTextAppearance(R.style.TextAppearance_Atlas_SectionTitle)
                    textSize = 16f
                    layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
                })
                head.addView(
                    ConsoleViews.pill(
                        this@MainActivity,
                        when {
                            granted -> getString(R.string.perm_granted)
                            intent != null -> getString(R.string.perm_needs_tap)
                            else -> getString(R.string.perm_auto)
                        },
                        when {
                            granted -> Tone.OK
                            intent != null -> Tone.WARN
                            else -> Tone.NEUTRAL
                        },
                    )
                )
                addView(head)
                addView(TextView(this@MainActivity).apply {
                    text = req.rationale
                    setTextAppearance(R.style.TextAppearance_Atlas_Value)
                    textSize = 13f
                    setTextColor(getColor(R.color.atlas_text_muted))
                    setPadding(0, ConsoleViews.dp(this@MainActivity, 6), 0, 0)
                })
                if (!granted && intent != null) {
                    addView(MaterialButton(this@MainActivity).apply {
                        text = getString(R.string.compliance_grant)
                        layoutParams = LinearLayout.LayoutParams(
                            ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT
                        ).apply { topMargin = ConsoleViews.dp(this@MainActivity, 8) }
                        setOnClickListener { runCatching { startActivity(intent) } }
                    })
                }
            }
            root.addView(card)
        }

        root.addView(MaterialButton(this,
            null, com.google.android.material.R.attr.materialButtonOutlinedStyle).apply {
            text = getString(R.string.perm_open_setup)
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
            )
            setOnClickListener { startActivity(Intent(this@MainActivity, PolicyComplianceActivity::class.java)) }
        })
    }

    // --------------------------------------------------------------------- //
    // Available app downloads
    // --------------------------------------------------------------------- //

    private fun renderApps(root: LinearLayout, desired: JSONObject?) {
        root.addView(ConsoleViews.sectionTitle(this, getString(R.string.section_apps_title)))
        val apps = desired?.optJSONArray("apps") ?: JSONArray()
        if (apps.length() == 0) {
            root.addView(ConsoleViews.emptyNote(this, getString(R.string.empty_apps)))
            return
        }

        for (i in 0 until apps.length()) {
            val app = apps.optJSONObject(i) ?: continue
            val pkg = app.optString("package_name")
            val wanted = app.optLong("version_code", -1)
            val available = app.optBoolean("available", false)
            val installed = installer.installedVersionCode(pkg)
            val size = app.optJSONArray("files")?.let { files ->
                (0 until files.length()).sumOf { files.optJSONObject(it)?.optLong("size_bytes", 0) ?: 0 }
            } ?: 0L

            val (statusText, tone) = when {
                !available -> getString(R.string.app_status_nothing) to Tone.ERROR
                installed == null -> getString(R.string.app_status_missing) to Tone.WARN
                installed >= wanted -> getString(R.string.app_status_installed, installed) to Tone.OK
                else -> getString(R.string.app_status_update, wanted) to Tone.WARN
            }

            val card = ConsoleViews.card(this)
            ConsoleViews.body(card).apply {
                val head = LinearLayout(this@MainActivity).apply {
                    orientation = LinearLayout.HORIZONTAL
                    gravity = android.view.Gravity.CENTER_VERTICAL
                }
                head.addView(TextView(this@MainActivity).apply {
                    text = appLabel(pkg)
                    setTextAppearance(R.style.TextAppearance_Atlas_SectionTitle)
                    textSize = 16f
                    layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
                })
                head.addView(ConsoleViews.pill(this@MainActivity, statusText, tone))
                addView(head)
                addView(TextView(this@MainActivity).apply {
                    text = buildString {
                        append(pkg)
                        append("  ·  target v").append(wanted)
                        app.str("version_name")?.let { append(" (").append(it).append(")") }
                        if (size > 0) append("  ·  ").append(humanSize(size))
                    }
                    setTextAppearance(R.style.TextAppearance_Atlas_Mono)
                    textSize = 12f
                    setPadding(0, ConsoleViews.dp(this@MainActivity, 6), 0, 0)
                })
            }
            root.addView(card)
        }

        root.addView(hintSync())
    }

    // --------------------------------------------------------------------- //
    // Available file downloads (the marketplace, F4)
    // --------------------------------------------------------------------- //

    private fun renderFiles(root: LinearLayout, desired: JSONObject?) {
        root.addView(ConsoleViews.sectionTitle(this, getString(R.string.section_files_title)))
        val files = desired?.optJSONObject("files")
        val required = files?.optJSONArray("required") ?: JSONArray()
        val available = files?.optJSONArray("available") ?: JSONArray()

        if (required.length() == 0 && available.length() == 0) {
            root.addView(ConsoleViews.emptyNote(this, getString(R.string.empty_files)))
            return
        }

        for (i in 0 until required.length()) {
            required.optJSONObject(i)?.let { root.addView(fileCard(it, optional = false)) }
        }
        for (i in 0 until available.length()) {
            available.optJSONObject(i)?.let { root.addView(fileCard(it, optional = true)) }
        }
    }

    private fun fileCard(entry: JSONObject, optional: Boolean): View {
        val size = entry.optLong("size_bytes", 0)
        val placed = deployer.isDeployed(entry, size)
        val selected = entry.optString("file_id") in config.selectedOptionalFiles

        val card = ConsoleViews.card(this)
        ConsoleViews.body(card).apply {
            val head = LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = android.view.Gravity.CENTER_VERTICAL
            }
            head.addView(TextView(this@MainActivity).apply {
                text = entry.str("title") ?: entry.str("name") ?: "File"
                setTextAppearance(R.style.TextAppearance_Atlas_SectionTitle)
                textSize = 16f
                layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
            })
            head.addView(ConsoleViews.pill(
                this@MainActivity,
                getString(if (optional) R.string.file_tag_optional else R.string.file_tag_automatic),
                if (optional) Tone.NEUTRAL else Tone.OK,
            ))
            addView(head)

            entry.str("description")?.let {
                addView(TextView(this@MainActivity).apply {
                    text = it
                    setTextAppearance(R.style.TextAppearance_Atlas_Value)
                    textSize = 13f
                    setTextColor(getColor(R.color.atlas_text_muted))
                    setPadding(0, ConsoleViews.dp(this@MainActivity, 6), 0, 0)
                })
            }
            addView(TextView(this@MainActivity).apply {
                text = buildString {
                    if (size > 0) append(humanSize(size)).append("  →  ")
                    append(entry.optString("dest_path"))
                }
                setTextAppearance(R.style.TextAppearance_Atlas_Mono)
                textSize = 12f
                setPadding(0, ConsoleViews.dp(this@MainActivity, 6), 0, 0)
            })

            if (optional) {
                addView(MaterialButton(this@MainActivity).apply {
                    text = getString(if (selected) R.string.remove else R.string.install)
                    layoutParams = LinearLayout.LayoutParams(
                        ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT
                    ).apply { topMargin = ConsoleViews.dp(this@MainActivity, 8) }
                    setOnClickListener { toggleOptionalFile(entry) }
                })
            } else {
                addView(ConsoleViews.pill(
                    this@MainActivity,
                    if (placed) getString(R.string.installed) else "Pending",
                    if (placed) Tone.OK else Tone.WARN,
                ).apply {
                    (layoutParams as LinearLayout.LayoutParams).topMargin =
                        ConsoleViews.dp(this@MainActivity, 8)
                })
            }
        }
        return card
    }

    /** F4: the admin curates what is available; the user picks. Applied at once. */
    private fun toggleOptionalFile(entry: JSONObject) {
        val fileId = entry.optString("file_id")
        val selected = config.selectedOptionalFiles.toMutableSet()
        if (fileId in selected) {
            selected.remove(fileId)
            // Forget we placed it so the user can take it again later; leave the
            // file itself alone — removing it is their business, not ours.
            config.forgetAppliedFile(FileDeployer.stateKeyFor(entry))
        } else {
            selected.add(fileId)
        }
        config.selectedOptionalFiles = selected
        syncNow()
    }

    // --------------------------------------------------------------------- //
    // Applied policy
    // --------------------------------------------------------------------- //

    private fun renderPolicies(root: LinearLayout, desired: JSONObject?) {
        root.addView(ConsoleViews.sectionTitle(this, getString(R.string.section_policies_title)))
        val policy = desired?.optJSONObject("policy")
        if (policy == null || policy.length() == 0) {
            root.addView(ConsoleViews.emptyNote(this, getString(R.string.empty_policies)))
            return
        }

        for (type in policy.keys()) {
            val section = policy.optJSONObject(type) ?: continue
            val card = ConsoleViews.card(this)
            val body = ConsoleViews.body(card)
            body.addView(TextView(this).apply {
                text = prettyType(type)
                setTextAppearance(R.style.TextAppearance_Atlas_SectionTitle)
                textSize = 16f
                setPadding(0, 0, 0, ConsoleViews.dp(this@MainActivity, 4))
            })
            for (field in section.keys()) {
                val shown =
                    if (field in SECRET_POLICY_FIELDS) "•••••• (enforced)"
                    else summarise(section.get(field))
                body.addView(ConsoleViews.kv(this, prettyField(field), shown))
            }
            root.addView(card)
        }

        root.addView(ConsoleViews.emptyNote(
            this, "Policy version ${config.stateVersion} (applied ${config.appliedStateVersion})",
        ))
    }

    // --------------------------------------------------------------------- //
    // Sync + re-enrol
    // --------------------------------------------------------------------- //

    private fun syncNow() {
        if (syncing) return
        syncing = true
        render()
        lifecycleScope.launch {
            val outcome = withContext(Dispatchers.IO) {
                runCatching { Reconciler(applicationContext).sync() }
            }
            syncing = false
            outcome.onSuccess { result ->
                val msg = if (result.errors.isEmpty()) {
                    getString(R.string.sync_ok, result.stateVersion)
                } else {
                    getString(R.string.sync_problems, result.errors.size, result.errors.first())
                }
                Toast.makeText(this@MainActivity, msg, Toast.LENGTH_LONG).show()
            }.onFailure {
                Toast.makeText(this@MainActivity, getString(R.string.sync_failed, it.message ?: ""),
                    Toast.LENGTH_LONG).show()
            }
            render()
        }
    }

    private fun reEnroll(token: String) {
        if (token.isEmpty()) {
            Toast.makeText(this, "Paste an enrollment token first", Toast.LENGTH_LONG).show()
            return
        }
        DeviceIdentity.deleteIdentity()
        config.deviceId = null
        config.enrollmentToken = token
        config.lastError = "re-enrolling…"
        syncNow()
    }

    // --------------------------------------------------------------------- //
    // Helpers
    // --------------------------------------------------------------------- //

    private fun LinearLayout.addRow(
        label: String, value: String, pill: Tone?, valueTone: Tone? = null,
    ) {
        val row = LinearLayout(this@MainActivity).apply { orientation = LinearLayout.VERTICAL }
        val header = LinearLayout(this@MainActivity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = android.view.Gravity.CENTER_VERTICAL
        }
        header.addView(TextView(this@MainActivity).apply {
            text = label
            setTextAppearance(R.style.TextAppearance_Atlas_Label)
            textSize = 11f
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
        })
        if (pill != null) header.addView(ConsoleViews.pill(this@MainActivity, value, pill))
        row.addView(header)
        if (pill == null) {
            row.addView(TextView(this@MainActivity).apply {
                text = value
                setTextAppearance(R.style.TextAppearance_Atlas_Value)
                textSize = 14f
                if (valueTone != null) setTextColor(getColor(
                    when (valueTone) {
                        Tone.OK -> R.color.atlas_ok
                        Tone.WARN -> R.color.atlas_warn
                        Tone.ERROR -> R.color.atlas_error
                        Tone.NEUTRAL -> R.color.atlas_steel
                    }
                ))
                setPadding(0, ConsoleViews.dp(this@MainActivity, 2), 0, 0)
                setTextIsSelectable(true)
            })
        }
        (row.layoutParams ?: LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
        )).let {
            row.layoutParams = (it as LinearLayout.LayoutParams).apply {
                topMargin = ConsoleViews.dp(this@MainActivity, 6)
                bottomMargin = ConsoleViews.dp(this@MainActivity, 6)
            }
        }
        addView(row)
    }

    private fun hintSync(): TextView = ConsoleViews.emptyNote(
        this, "Downloads happen automatically. Use Sync now to check immediately."
    )

    @Suppress("HardwareIds")
    private fun serial(): String =
        runCatching { Build.getSerial() }.getOrNull()
            ?.takeIf { it.isNotBlank() && it != Build.UNKNOWN }
            ?: getString(R.string.value_unknown)

    private fun appLabel(pkg: String): String = runCatching {
        val pm = packageManager
        pm.getApplicationLabel(pm.getApplicationInfo(pkg, 0)).toString()
    }.getOrDefault(pkg)

    private fun lastSyncText(): String {
        val at = config.lastSyncAt
        if (at == 0L) return getString(R.string.value_never)
        val exact = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(Date(at))
        val ago = System.currentTimeMillis() - at
        val rel = when {
            ago < 60_000 -> "just now"
            ago < 3_600_000 -> "${ago / 60_000} min ago"
            ago < 86_400_000 -> "${ago / 3_600_000} h ago"
            else -> "${ago / 86_400_000} d ago"
        }
        return "$rel  ·  $exact"
    }

    private fun humanSize(bytes: Long): String = when {
        bytes < 1024 -> "$bytes B"
        bytes < 1024 * 1024 -> "${bytes / 1024} KB"
        else -> String.format(Locale.US, "%.1f MB", bytes / (1024.0 * 1024.0))
    }

    private fun prettyType(type: String): String = when (type) {
        "PASSWORD" -> "Passcode"
        "RESTRICTIONS" -> "Restrictions"
        "APP_CATALOG" -> "Apps & kiosk"
        "FILES" -> "Managed files"
        "NETWORKS" -> "Networks"
        else -> type.lowercase().replace('_', ' ').replaceFirstChar { it.uppercase() }
    }

    private fun prettyField(field: String): String =
        field.replace('_', ' ').replaceFirstChar { it.uppercase() }

    /** Scalars verbatim; arrays and objects as a short readable summary. */
    private fun summarise(value: Any?): String = when (value) {
        is JSONArray -> {
            val items = (0 until value.length()).map { value.get(it) }
            when {
                items.isEmpty() -> getString(R.string.value_none)
                items.all { it is JSONObject } -> items.joinToString("\n") { "• " + describeObject(it as JSONObject) }
                else -> items.joinToString(", ") { it.toString() }
            }
        }
        is JSONObject -> describeObject(value)
        JSONObject.NULL, null -> getString(R.string.value_none)
        is Boolean -> if (value) "Yes" else "No"
        else -> value.toString()
    }

    private fun describeObject(obj: JSONObject): String {
        for (key in listOf("title", "name", "package_name", "ssid", "dest_path", "file_id")) {
            obj.str(key)?.let { primary ->
                val extra = obj.str("min_version_code")?.let { " (min v$it)" } ?: ""
                return primary + extra
            }
        }
        return obj.toString()
    }

    /**
     * A string field, or null. Android's [JSONObject.optString] returns the
     * literal "null" for an explicit JSON null and "" for a missing key — this
     * collapses both, and blanks, to null.
     */
    private fun JSONObject.str(key: String): String? =
        if (isNull(key)) null else optString(key).takeIf { it.isNotBlank() }

    private companion object {
        /** Policy fields whose value is a credential — never shown on the console. */
        val SECRET_POLICY_FIELDS = setOf("set_password", "password")
    }
}
