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

package com.taksolutions.atlasmdm.ui

import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.view.View
import android.view.ViewGroup
import android.widget.Button
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
import com.taksolutions.atlasmdm.BuildConfig
import com.taksolutions.atlasmdm.R
import com.taksolutions.atlasmdm.admin.MdmDeviceAdminReceiver
import com.taksolutions.atlasmdm.admin.PolicyComplianceActivity
import com.taksolutions.atlasmdm.core.AgentConfig
import com.taksolutions.atlasmdm.files.FileDeployer
import com.taksolutions.atlasmdm.install.AppInstaller
import com.taksolutions.atlasmdm.net.ApiClient
import com.taksolutions.atlasmdm.permissions.PermissionRequirement
import com.taksolutions.atlasmdm.sync.Reconciler
import com.taksolutions.atlasmdm.sync.SyncScheduler
import com.taksolutions.atlasmdm.ui.ConsoleViews.Tone
import java.io.File
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

        showSplash(savedInstanceState)

        SyncScheduler.startAll(this)
    }

    /**
     * Hold the ATLAS logo over the screen for [SPLASH_MILLIS], then fade it out.
     *
     * ⚠️ **Only on a fresh start.** `onCreate` runs again on every configuration
     * change — a rotation, a font-size change, folding a device — and a splash
     * that replays each time would cover the app for three seconds every time the
     * operator turns the tablet. `savedInstanceState` being non-null is what tells
     * the two apart.
     *
     * The view is posted away rather than merely hidden: it is a full-screen
     * `FrameLayout` over the whole UI, and leaving it in the hierarchy would keep
     * costing a measure and draw pass for the life of the activity.
     */
    private fun showSplash(savedInstanceState: Bundle?) {
        val splash = findViewById<View>(R.id.splash)
        if (savedInstanceState != null) {
            (splash.parent as? ViewGroup)?.removeView(splash)
            return
        }
        splash.postDelayed({
            splash.animate()
                .alpha(0f)
                .setDuration(SPLASH_FADE_MILLIS)
                .withEndAction { (splash.parent as? ViewGroup)?.removeView(splash) }
        }, SPLASH_MILLIS)
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
            // Both numbers, because they answer different questions and only one
            // of them is the one the server acts on. The console publishes a
            // *versionCode*, and an operator checking whether this device took
            // that build cannot do it from "0.33.0" alone — two builds can share
            // a version name, and it is the code that decides an update.
            addView(ConsoleViews.kv(
                this@MainActivity,
                getString(R.string.label_agent_version),
                "${BuildConfig.VERSION_NAME}  (build ${BuildConfig.VERSION_CODE})",
            ))
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

    /** Which slice of the managed apps the Apps section is showing (W48). */
    private var appsTab = AppsTabPlan.AppsTab.AVAILABLE

    private fun renderApps(root: LinearLayout, desired: JSONObject?) {
        root.addView(ConsoleViews.sectionTitle(this, getString(R.string.section_apps_title)))

        // Required apps and store offers share this screen, flagged apart (W56).
        //
        // ⚠️ They are not the same kind of thing and must not read as though they
        // are. A required app sitting in Available is a *pending obligation* — the
        // device has not converged yet. A store app there is an *offer* nobody has
        // taken. Showing them identically would make a broken policy look like a
        // shopping list.
        val apps = JSONArray()
        (desired?.optJSONArray("apps") ?: JSONArray()).let { required ->
            for (i in 0 until required.length()) apps.put(required.optJSONObject(i))
        }
        (desired?.optJSONArray("store") ?: JSONArray()).let { store ->
            for (i in 0 until store.length()) {
                store.optJSONObject(i)?.let { apps.put(it.put(OFFERED, true)) }
            }
        }

        if (apps.length() == 0) {
            root.addView(ConsoleViews.emptyNote(this, getString(R.string.empty_apps)))
            return
        }

        // Bucket first, so the tab labels can carry counts. A count is the point:
        // "Updates" is only worth opening when it has something in it.
        val buckets = linkedMapOf(
            AppsTabPlan.AppsTab.AVAILABLE to mutableListOf<JSONObject>(),
            AppsTabPlan.AppsTab.INSTALLED to mutableListOf(),
            AppsTabPlan.AppsTab.UPDATES to mutableListOf(),
        )
        for (i in 0 until apps.length()) {
            val app = apps.optJSONObject(i) ?: continue
            val tab = AppsTabPlan.tabFor(
                available = app.optBoolean("available", false),
                installedVersionCode = installer.installedVersionCode(app.optString("package_name")),
                wantedVersionCode = app.optLong("version_code", -1),
            )
            buckets.getValue(tab).add(app)
        }

        root.addView(appsTabBar(buckets))

        val shown = buckets.getValue(appsTab)
        if (shown.isEmpty()) {
            root.addView(
                ConsoleViews.emptyNote(
                    this,
                    getString(
                        when (appsTab) {
                            AppsTabPlan.AppsTab.AVAILABLE -> R.string.empty_apps_available
                            AppsTabPlan.AppsTab.INSTALLED -> R.string.empty_apps_installed
                            AppsTabPlan.AppsTab.UPDATES -> R.string.empty_apps_updates
                        }
                    ),
                )
            )
            root.addView(hintSync())
            return
        }

        for (app in shown) {
            val pkg = app.optString("package_name")
            val wanted = app.optLong("version_code", -1)
            val available = app.optBoolean("available", false)
            val installed = installer.installedVersionCode(pkg)
            val size = app.optJSONArray("files")?.let { files ->
                (0 until files.length()).sumOf { files.optJSONObject(it)?.optLong("size_bytes", 0) ?: 0 }
            } ?: 0L

            val offered = app.optBoolean(OFFERED, false)

            val (statusText, tone) = when {
                !available -> getString(R.string.app_status_nothing) to Tone.ERROR
                // An offer is never WARN. Nothing is wrong with a store app the
                // user has simply not taken, and colouring it like an unmet
                // requirement would cry wolf on every device that ignores the shop.
                offered && installed == null -> getString(R.string.app_status_offered) to Tone.NEUTRAL
                installed == null -> getString(R.string.app_status_missing) to Tone.WARN
                installed >= wanted -> getString(R.string.app_status_installed, installed) to Tone.OK
                offered -> getString(R.string.app_status_update_offered, wanted) to Tone.NEUTRAL
                else -> getString(R.string.app_status_update, wanted) to Tone.WARN
            }

            val card = ConsoleViews.card(this)
            ConsoleViews.body(card).apply {
                val head = LinearLayout(this@MainActivity).apply {
                    orientation = LinearLayout.HORIZONTAL
                    gravity = android.view.Gravity.CENTER_VERTICAL
                }
                // The icon leads, as it does in the console's app list. Absent for
                // an app whose artwork could not be extracted, and the row simply
                // starts at the name — a placeholder box would add nothing.
                appIcon(app)?.let { art ->
                    head.addView(android.widget.ImageView(this@MainActivity).apply {
                        setImageDrawable(art)
                        layoutParams = LinearLayout.LayoutParams(
                            ConsoleViews.dp(this@MainActivity, 36),
                            ConsoleViews.dp(this@MainActivity, 36),
                        ).apply { marginEnd = ConsoleViews.dp(this@MainActivity, 10) }
                    })
                }
                head.addView(TextView(this@MainActivity).apply {
                    text = appLabel(pkg, app.str("label"))
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

                // The offer's only affordance. A required app has no button here
                // on purpose: the device installs it whether anyone asks or not,
                // so a button would imply a choice the user does not have.
                if (offered && available && (installed == null || installed < wanted)) {
                    addView(installRow(app, pkg, fresh = installed == null))
                }
            }
            root.addView(card)
        }

        root.addView(hintSync())
    }

    /** A store install in flight, and how far it has got (W58). */
    private class Install(
        @Volatile var phase: Reconciler.InstallPhase = Reconciler.InstallPhase.DOWNLOADING,
        @Volatile var read: Long = 0,
        @Volatile var total: Long = 0,
        val cancel: java.util.concurrent.atomic.AtomicBoolean =
            java.util.concurrent.atomic.AtomicBoolean(false),
    )

    private val installs = mutableMapOf<String, Install>()

    /** Bar and label per package, so the worker can update them without a render. */
    private val progressViews = mutableMapOf<String, Pair<android.widget.ProgressBar, TextView>>()

    /**
     * The Install button — or, while one is running, a progress bar and Cancel.
     *
     * ⚠️ The two phases fail and feel differently, so the row says which it is in.
     * **Downloading** is slow, measurable and safely abandonable. **Installing** is
     * `PackageInstaller` committing: quick, unmeasurable, and *not* safe to abandon,
     * because Android is mutating the package by then. Hence a determinate bar and
     * a live Cancel for the first, an indeterminate bar and a dead one for the
     * second.
     */
    private fun installRow(entry: JSONObject, pkg: String, fresh: Boolean): LinearLayout {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = android.view.Gravity.CENTER_VERTICAL
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
            ).apply { topMargin = ConsoleViews.dp(this@MainActivity, 10) }
        }

        val running = installs[pkg]

        row.addView(MaterialButton(this).apply {
            text = getString(
                when {
                    running != null -> R.string.action_cancel
                    fresh -> R.string.action_install
                    else -> R.string.action_update
                }
            )
            isEnabled = running == null || running.phase == Reconciler.InstallPhase.DOWNLOADING
            setOnClickListener {
                if (running != null) running.cancel.set(true) else installOffered(entry)
            }
        })

        if (running != null) {
            val bar = android.widget.ProgressBar(
                this, null, android.R.attr.progressBarStyleHorizontal
            ).apply {
                max = 100
                isIndeterminate = running.phase == Reconciler.InstallPhase.INSTALLING
                progress = percentOf(running)
                layoutParams = LinearLayout.LayoutParams(
                    0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f
                ).apply { marginStart = ConsoleViews.dp(this@MainActivity, 12) }
            }
            val label = TextView(this).apply {
                text = progressText(running)
                setTextAppearance(R.style.TextAppearance_Atlas_Mono)
                textSize = 12f
                layoutParams = LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT
                ).apply { marginStart = ConsoleViews.dp(this@MainActivity, 8) }
            }
            row.addView(bar)
            row.addView(label)
            progressViews[pkg] = bar to label
        }
        return row
    }

    private fun percentOf(state: Install): Int =
        if (state.total <= 0) 0 else ((state.read * 100) / state.total).toInt().coerceIn(0, 100)

    private fun progressText(state: Install): String = when (state.phase) {
        Reconciler.InstallPhase.INSTALLING -> getString(R.string.action_installing)
        Reconciler.InstallPhase.DOWNLOADING ->
            if (state.total <= 0) getString(R.string.action_downloading)
            else getString(R.string.progress_downloading, percentOf(state))
    }

    /**
     * Install a store app the user asked for (W56; progress and cancel in W58).
     *
     * Off the main thread: this downloads tens of megabytes and then blocks on
     * `PackageInstaller`.
     *
     * ⚠️ The bar is updated **in place** by the worker, never by re-rendering the
     * list. The progress callback fires once per 8 KB buffer — roughly two thousand
     * times for a 16 MB app — and rebuilding every card at that rate would make the
     * screen unusable, so only a whole-percent change reaches the main thread.
     */
    private fun installOffered(entry: JSONObject) {
        val pkg = entry.optString("package_name")
        if (installs.containsKey(pkg)) return
        val state = Install()
        installs[pkg] = state
        render()

        lifecycleScope.launch {
            val outcome = withContext(Dispatchers.IO) {
                runCatching {
                    Reconciler(applicationContext).installFromStore(
                        entry,
                        onProgress = { phase, read, total ->
                            val wasWhole = percentOf(state)
                            val changedPhase = phase != state.phase
                            state.phase = phase
                            state.read = read
                            state.total = if (total > 0) total else state.total
                            if (changedPhase || percentOf(state) != wasWhole) {
                                runOnUiThread { paintProgress(pkg, state) }
                            }
                        },
                        isCancelled = { state.cancel.get() },
                    )
                }.getOrElse {
                    Reconciler.StoreInstall.Failed(it.message ?: "the install could not be started")
                }
            }

            installs.remove(pkg)
            progressViews.remove(pkg)
            val name = appLabel(pkg, entry.str("label"))
            when (outcome) {
                is Reconciler.StoreInstall.Done -> toast(getString(R.string.install_ok, name))
                is Reconciler.StoreInstall.Cancelled ->
                    toast(getString(R.string.install_cancelled, name))
                is Reconciler.StoreInstall.Failed ->
                    toast(getString(R.string.install_failed, name, outcome.reason))
            }
            render()
        }
    }

    private fun paintProgress(pkg: String, state: Install) {
        val (bar, label) = progressViews[pkg] ?: return
        bar.isIndeterminate = state.phase == Reconciler.InstallPhase.INSTALLING
        if (!bar.isIndeterminate) bar.progress = percentOf(state)
        label.text = progressText(state)
    }

    private fun toast(message: String) =
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()

    /**
     * The Available / Installed / Updates selector.
     *
     * Three buttons rather than a `TabLayout`: the section switcher already works
     * by re-rendering off a field, and adding a second navigation idiom for three
     * options would cost more than it explains.
     */
    private fun appsTabBar(buckets: Map<AppsTabPlan.AppsTab, List<JSONObject>>): LinearLayout {
        val bar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
            ).apply { bottomMargin = ConsoleViews.dp(this@MainActivity, 8) }
        }

        for (tab in AppsTabPlan.AppsTab.entries) {
            val count = buckets[tab]?.size ?: 0
            val label = getString(
                when (tab) {
                    AppsTabPlan.AppsTab.AVAILABLE -> R.string.apps_tab_available
                    AppsTabPlan.AppsTab.INSTALLED -> R.string.apps_tab_installed
                    AppsTabPlan.AppsTab.UPDATES -> R.string.apps_tab_updates
                },
                count,
            )
            val selected = tab == appsTab
            bar.addView(
                MaterialButton(
                    this,
                    null,
                    if (selected) com.google.android.material.R.attr.materialButtonStyle
                    else com.google.android.material.R.attr.materialButtonOutlinedStyle,
                ).apply {
                    text = label
                    textSize = 12f
                    isAllCaps = false
                    layoutParams = LinearLayout.LayoutParams(
                        0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f
                    ).apply { marginEnd = ConsoleViews.dp(this@MainActivity, 6) }
                    setOnClickListener {
                        appsTab = tab
                        render()
                    }
                }
            )
        }
        return bar
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

        val names = config.policyNames
        // Fall back to the category types from the cached bundle if the server has
        // not sent names yet (older server, or first sync still pending).
        val fallback = desired?.optJSONObject("policy")?.keys()?.asSequence()?.map { prettyType(it) }?.toList()

        val show = when {
            names.isNotEmpty() -> names
            !fallback.isNullOrEmpty() -> fallback
            else -> {
                root.addView(ConsoleViews.emptyNote(this, getString(R.string.empty_policies)))
                root.addView(policyVersionNote())
                return
            }
        }

        val card = ConsoleViews.card(this)
        val body = ConsoleViews.body(card)
        show.forEachIndexed { i, name ->
            if (i > 0) body.addView(ConsoleViews.divider(this))
            body.addView(ConsoleViews.kv(this, "Policy", name))
        }
        root.addView(card)
        root.addView(policyVersionNote())
    }

    private fun policyVersionNote(): TextView = ConsoleViews.emptyNote(
        this, "Policy version ${config.stateVersion} (applied ${config.appliedStateVersion})",
    )

    // --------------------------------------------------------------------- //
    // Sync
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

    /**
     * What to call an app, best source first.
     *
     * ⚠️ `PackageManager` only knows apps that are **installed**, and the Apps
     * screen most needs a name for one that is not — an offer nobody has taken
     * yet. Asking it first is why a store entry showed as
     * `com.taksolutions.uasready` (W57). The server sends the name it read out of
     * the APK, so that is preferred; the package id remains the last resort,
     * because it is at least true.
     */
    private fun appLabel(pkg: String, fromServer: String? = null): String =
        fromServer?.takeIf { it.isNotBlank() }
            ?: runCatching {
                val pm = packageManager
                pm.getApplicationLabel(pm.getApplicationInfo(pkg, 0)).toString()
            }.getOrDefault(pkg)

    /**
     * The app's icon, fetched once per build and cached (W57).
     *
     * Returns null when the app has no extractable icon, when it has not been
     * fetched yet, or when the file will not decode — all of which the caller
     * treats the same way, by showing nothing rather than a broken placeholder.
     *
     * Keyed by `version_code`: the artwork only changes when a new build brings
     * new artwork, and the server has no cheap hash of the icon to offer instead.
     */
    private fun appIcon(entry: JSONObject): android.graphics.drawable.Drawable? {
        val path = entry.str("icon_url") ?: return null
        val pkg = entry.optString("package_name")
        val version = entry.optLong("version_code", 0)
        val cached = File(cacheDir, "icon_${pkg}_$version")

        if (!cached.exists()) {
            // Fetched on a worker and the screen re-rendered when it lands, so a
            // slow link cannot stall the list being drawn.
            if (iconsFetching.add(cached.name)) {
                lifecycleScope.launch {
                    val ok = withContext(Dispatchers.IO) {
                        runCatching { ApiClient(config).downloadIcon(path, cached) }
                            .getOrDefault(false)
                    }
                    iconsFetching.remove(cached.name)
                    if (ok) render()
                }
            }
            return null
        }

        return runCatching {
            android.graphics.BitmapFactory.decodeFile(cached.absolutePath)?.let {
                android.graphics.drawable.BitmapDrawable(resources, it)
            }
        }.getOrNull()
    }

    /** Icon fetches in flight, so a re-render does not start the same one twice. */
    private val iconsFetching = mutableSetOf<String>()

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

    /**
     * A string field, or null. Android's [JSONObject.optString] returns the
     * literal "null" for an explicit JSON null and "" for a missing key — this
     * collapses both, and blanks, to null.
     */
    private fun JSONObject.str(key: String): String? =
        if (isNull(key)) null else optString(key).takeIf { it.isNotBlank() }

    private companion object {
        /**
         * Marks a merged entry as a store offer rather than a required app (W56).
         *
         * Set on the JSON object itself so the two lists can share one render
         * path; the server never sends this key.
         */
        const val OFFERED = "_atlas_offered"

        /** How long the ATLAS logo is held on screen, as the operator asked. */
        const val SPLASH_MILLIS = 3_000L

        /** Fade, so the logo hands over to the app rather than vanishing. */
        const val SPLASH_FADE_MILLIS = 320L
    }
}
