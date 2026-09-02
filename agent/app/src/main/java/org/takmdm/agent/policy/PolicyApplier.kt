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

package org.takmdm.agent.policy

import android.app.admin.DevicePolicyManager
import android.app.ActivityOptions
import android.content.Intent
import android.content.IntentFilter
import android.content.Context
import android.content.pm.PackageManager
import android.net.wifi.WifiConfiguration
import android.net.wifi.WifiManager
import android.os.UserManager
import androidx.core.content.ContextCompat
import org.takmdm.agent.core.AgentConfig
import org.takmdm.agent.diag.AgentLog
import org.json.JSONObject
import org.takmdm.agent.admin.MdmDeviceAdminReceiver

/**
 * Applies the AOSP-expressible parts of a desired state through
 * [DevicePolicyManager].
 *
 * Every method reports what failed rather than throwing: one unsupported
 * restriction must not abandon the rest of the policy. The collected failures go
 * back to the server as `apply_errors`, which is what turns a device DEGRADED
 * instead of silently non-compliant.
 */
class PolicyApplier(private val context: Context) {

    private val dpm: DevicePolicyManager =
        context.getSystemService(DevicePolicyManager::class.java)

    private val admin = MdmDeviceAdminReceiver.componentName(context)

    private val oem: OemPolicyApplier by lazy { OemPolicyApplier.forDevice(context) }

    val isDeviceOwner: Boolean
        get() = dpm.isDeviceOwnerApp(context.packageName)

    fun apply(policy: JSONObject): List<String> {
        if (!isDeviceOwner) {
            return listOf("not device owner; policy cannot be applied")
        }
        val failures = mutableListOf<String>()
        policy.optJSONObject("PASSWORD")?.let { failures += applyPassword(it) }
        policy.optJSONObject("RESTRICTIONS")?.let { failures += applyRestrictions(it) }
        policy.optJSONObject("APP_CATALOG")?.let { failures += applyAppCatalog(it) }
        // NETWORKS runs even when absent: an emptied policy must remove the Wi-Fi
        // networks the agent previously added.
        failures += applyNetworks(policy.optJSONObject("NETWORKS") ?: JSONObject())
        return failures
    }

    // ----------------------------------------------------------------------- //
    // Passcode
    // ----------------------------------------------------------------------- //

    private fun applyPassword(spec: JSONObject): List<String> {
        val failures = mutableListOf<String>()

        runCatching {
            // Android 12 deprecated the granular setPasswordMinimum* family in
            // favour of complexity buckets. Mapping the server's numeric strength
            // onto a bucket keeps the policy meaningful on modern releases.
            val complexity = when {
                spec.optInt("min_length", 0) >= 12 -> DevicePolicyManager.PASSWORD_COMPLEXITY_HIGH
                spec.optInt("min_length", 0) >= 8 -> DevicePolicyManager.PASSWORD_COMPLEXITY_MEDIUM
                spec.has("min_length") || spec.has("quality") ->
                    DevicePolicyManager.PASSWORD_COMPLEXITY_LOW
                else -> DevicePolicyManager.PASSWORD_COMPLEXITY_NONE
            }
            if (complexity != DevicePolicyManager.PASSWORD_COMPLEXITY_NONE) {
                dpm.requiredPasswordComplexity = complexity
            }
        }.onFailure { failures += "password complexity: ${it.message}" }

        if (spec.has("max_failed_attempts_before_wipe")) {
            runCatching {
                dpm.setMaximumFailedPasswordsForWipe(
                    admin, spec.getInt("max_failed_attempts_before_wipe")
                )
            }.onFailure { failures += "max failed attempts: ${it.message}" }
        }

        if (spec.has("lock_timeout_seconds")) {
            runCatching {
                dpm.setMaximumTimeToLock(admin, spec.getInt("lock_timeout_seconds") * 1000L)
            }.onFailure { failures += "lock timeout: ${it.message}" }
        }

        if (spec.has("expiration_days")) {
            runCatching {
                dpm.setPasswordExpirationTimeout(
                    admin, spec.getInt("expiration_days") * 86_400_000L
                )
            }.onFailure { failures += "password expiry: ${it.message}" }
        }

        return failures
    }

    // ----------------------------------------------------------------------- //
    // Restrictions
    // ----------------------------------------------------------------------- //

    /**
     * Server field names are all phrased as "allow"; user restrictions are phrased
     * as "disallow". The inversion happens once, here, rather than at each call
     * site where a missed negation would quietly permit something.
     */
    private val restrictionMap = mapOf(
        "allow_usb_file_transfer" to UserManager.DISALLOW_USB_FILE_TRANSFER,
        "allow_factory_reset" to UserManager.DISALLOW_FACTORY_RESET,
        "allow_safe_mode" to UserManager.DISALLOW_SAFE_BOOT,
        "allow_developer_options" to UserManager.DISALLOW_DEBUGGING_FEATURES,
        "allow_install_unknown_sources" to UserManager.DISALLOW_INSTALL_UNKNOWN_SOURCES,
        "allow_outgoing_calls" to UserManager.DISALLOW_OUTGOING_CALLS,
        "allow_bluetooth" to UserManager.DISALLOW_BLUETOOTH,
        "allow_location_services" to UserManager.DISALLOW_SHARE_LOCATION
    )

    private fun applyRestrictions(spec: JSONObject): List<String> {
        val failures = mutableListOf<String>()

        for ((allowKey, restriction) in restrictionMap) {
            if (!spec.has(allowKey)) continue
            val allowed = spec.optBoolean(allowKey, true)
            runCatching {
                if (allowed) dpm.clearUserRestriction(admin, restriction)
                else dpm.addUserRestriction(admin, restriction)
            }.onFailure { failures += "$allowKey: ${it.message}" }
        }

        if (spec.has("allow_camera")) {
            runCatching {
                dpm.setCameraDisabled(admin, !spec.getBoolean("allow_camera"))
            }.onFailure { failures += "camera: ${it.message}" }
        }

        if (spec.has("allow_screen_capture")) {
            runCatching {
                dpm.setScreenCaptureDisabled(admin, !spec.getBoolean("allow_screen_capture"))
            }.onFailure { failures += "screen capture: ${it.message}" }
        }

        failures += oem.applyRestrictions(context, spec)
        return failures
    }

    // ----------------------------------------------------------------------- //
    // Apps: blocklist and kiosk
    // ----------------------------------------------------------------------- //

    private fun applyAppCatalog(spec: JSONObject): List<String> {
        val failures = mutableListOf<String>()

        // blocked_packages is handled by the reconciler's suppression step, not
        // here: blacklisting now tries uninstall before falling back to hiding, and
        // that needs PackageInstaller as well as DevicePolicyManager.

        // Kiosk is opt-in (F6). No kiosk_package means the agent stays a background
        // service and leaves the home screen alone.
        failures += applyKiosk(spec.optString("kiosk_package").takeIf { it.isNotBlank() })

        return failures
    }

    // ----------------------------------------------------------------------- //
    // Networks: Wi-Fi
    //
    // WifiManager.addNetwork(WifiConfiguration) is deprecated (API 29) but
    // grandfathered for a Device Owner: a normal app gets -1 back, a DO gets a
    // real network id. If -1 comes back here on real hardware, that assumption is
    // wrong for this OEM and the failure says so.
    // ----------------------------------------------------------------------- //

    @Suppress("DEPRECATION")
    private fun applyNetworks(spec: JSONObject): List<String> {
        val failures = mutableListOf<String>()
        val desired = WifiPlan.desired(spec)
        val config = AgentConfig(context)

        if (desired.isEmpty() && config.wifiByPolicy.isEmpty()) return failures

        val wifi = context.getSystemService(WifiManager::class.java)
            ?: return listOf("networks: WifiManager unavailable")

        val managed = config.wifiByPolicy.toMutableSet()

        for (ssid in WifiPlan.toRemove(config.wifiByPolicy, desired)) {
            runCatching {
                val id = config.wifiNetworkId(ssid)
                val gone = id >= 0 && wifi.removeNetwork(id)
                config.forgetWifiNetworkId(ssid)
                AgentLog.i(TAG, "wifi: removing $ssid (id=$id, removed=$gone)")
            }.onFailure { failures += "wifi remove $ssid: ${it.message}" }
            managed.remove(ssid)
        }

        for (n in desired) {
            runCatching {
                // Replace any config we previously added for this SSID.
                config.wifiNetworkId(n.ssid).takeIf { it >= 0 }?.let { wifi.removeNetwork(it) }
                val id = wifi.addNetwork(buildWifiConfig(n))
                if (id < 0) {
                    failures += "wifi ${n.ssid}: addNetwork returned -1 " +
                        "(the Device Owner Wi-Fi config path is not available on this device)"
                    return@runCatching
                }
                // enableNetwork makes it a connection candidate; a configured
                // network auto-joins by default. There is no public per-network
                // auto-join toggle for a DO, so `auto_join: false` is accepted and
                // recorded on the server but not enforced here.
                wifi.enableNetwork(id, false)
                config.recordWifiNetworkId(n.ssid, id)
                managed.add(n.ssid)
                AgentLog.i(TAG, "wifi: configured ${n.ssid} (${n.security}, id=$id)")
            }.onFailure { failures += "wifi ${n.ssid}: ${it.message}" }
        }

        config.wifiByPolicy = managed
        return failures
    }

    @Suppress("DEPRECATION")
    private fun buildWifiConfig(n: DesiredWifi): WifiConfiguration = WifiConfiguration().apply {
        SSID = "\"${n.ssid}\""
        hiddenSSID = n.hidden
        when (n.security) {
            "open" -> allowedKeyManagement.set(WifiConfiguration.KeyMgmt.NONE)
            "wep" -> {
                allowedKeyManagement.set(WifiConfiguration.KeyMgmt.NONE)
                allowedAuthAlgorithms.set(WifiConfiguration.AuthAlgorithm.OPEN)
                allowedAuthAlgorithms.set(WifiConfiguration.AuthAlgorithm.SHARED)
                wepKeys[0] = "\"${n.password.orEmpty()}\""
                wepTxKeyIndex = 0
            }
            "wpa3_sae" -> {
                allowedKeyManagement.set(WifiConfiguration.KeyMgmt.SAE)
                preSharedKey = "\"${n.password.orEmpty()}\""
            }
            else -> { // wpa_psk
                allowedKeyManagement.set(WifiConfiguration.KeyMgmt.WPA_PSK)
                preSharedKey = "\"${n.password.orEmpty()}\""
            }
        }
    }

    // ----------------------------------------------------------------------- //
    // Permission pre-granting
    // ----------------------------------------------------------------------- //

    /**
     * Pre-grant runtime permissions to a managed app.
     *
     * **R9:** on Android 11+, granting `WRITE_EXTERNAL_STORAGE` to an app
     * permanently prevents it from requesting `MANAGE_EXTERNAL_STORAGE`. An app that
     * needs all-files access — ATAK does — must therefore be denied the legacy
     * storage permissions, not given them. The obvious "grant everything it asks
     * for" loop breaks exactly the apps that matter, and does it silently.
     */
    fun grantRuntimePermissions(packageName: String): List<String> {
        if (!isDeviceOwner) return listOf("not device owner")
        val failures = mutableListOf<String>()

        val info = runCatching {
            context.packageManager.getPackageInfo(
                packageName, PackageManager.GET_PERMISSIONS
            )
        }.getOrNull() ?: return listOf("$packageName not installed")

        val requested = info.requestedPermissions?.toList().orEmpty()
        val wantsAllFiles = requested.contains(PERMISSION_MANAGE_EXTERNAL_STORAGE)

        runCatching {
            dpm.setPermissionPolicy(admin, DevicePolicyManager.PERMISSION_POLICY_AUTO_GRANT)
        }.onFailure { failures += "permission policy: ${it.message}" }

        for (permission in requested) {
            if (wantsAllFiles && permission in LEGACY_STORAGE_PERMISSIONS) {
                AgentLog.i(
                    TAG,
                    "skipping $permission for $packageName: granting it would lock the " +
                        "app out of MANAGE_EXTERNAL_STORAGE (R9)"
                )
                continue
            }
            if (!isDangerous(permission)) continue

            runCatching {
                dpm.setPermissionGrantState(
                    admin, packageName, permission,
                    DevicePolicyManager.PERMISSION_GRANT_STATE_GRANTED
                )
            }.onFailure { failures += "$permission: ${it.message}" }
        }

        if (wantsAllFiles && !oem.grantAllFilesAccess(context, packageName)) {
            // Not a failure: no AOSP path exists, so this is a fact to report rather
            // than an error to retry.
            AgentLog.i(TAG, "$packageName needs all-files access; requires a manual grant")
        }

        return failures
    }

    // ----------------------------------------------------------------------- //
    // Kiosk
    // ----------------------------------------------------------------------- //

    /**
     * Put the device into kiosk mode, or take it out of one.
     *
     * Both directions, deliberately. A policy that can only ever lock a device down
     * is not desired state, it is a latch — and a latch on *this* feature strands a
     * tablet. Everything set here is undone when `kiosk_package` goes away.
     *
     * Permitting an app is not the same as locking it: lock task features and the
     * allowlist are one policy from Android 14 onward, and
     * `ActivityOptions.setLockTaskEnabled` "doesn't affect activities that are
     * already running", so the app has to be relaunched rather than merely allowed.
     */
    fun applyKiosk(kioskPackage: String?): List<String> {
        val failures = mutableListOf<String>()

        if (kioskPackage == null) {
            failures += releaseKiosk()
            return failures
        }

        if (!isInstalled(kioskPackage)) {
            // Locking the device to an app that is not there would leave it on a
            // blank screen with no way out. Refuse, and say why.
            return listOf("kiosk: $kioskPackage is not installed; not engaging")
        }

        // Before the features are set, because those enable HOME. Doing it the
        // other way round leaves a window in which the home button is live and
        // still points at the system launcher.
        failures += setHomeTo(kioskPackage)

        runCatching {
            dpm.setLockTaskPackages(admin, arrayOf(kioskPackage, context.packageName))
            // GLOBAL_ACTIONS is the default but must be repeated: any feature not
            // named here is implicitly disabled. Dropping it would remove the power
            // menu and leave a field device recoverable only by a hard reset.
            //
            // HOME is not optional here, though it looks like a hole. The platform
            // refuses NOTIFICATIONS without it:
            //
            //   "Cannot use LOCK_TASK_FEATURE_NOTIFICATIONS without
            //    LOCK_TASK_FEATURE_HOME"
            //
            // - observed on SM-X520, and stated in neither doc consulted. It is
            // safe only because setHomeTo() has already pointed HOME at the kiosk
            // app itself, so pressing it returns to the kiosk rather than escaping
            // to the launcher. The two decisions turn out to depend on each other:
            // without the home takeover, enabling HOME here would be a way out.
            dpm.setLockTaskFeatures(
                admin,
                DevicePolicyManager.LOCK_TASK_FEATURE_GLOBAL_ACTIONS or
                    DevicePolicyManager.LOCK_TASK_FEATURE_HOME or
                    DevicePolicyManager.LOCK_TASK_FEATURE_NOTIFICATIONS or
                    DevicePolicyManager.LOCK_TASK_FEATURE_KEYGUARD
            )
        }.onFailure { return listOf("kiosk: could not configure lock task - ${it.message}") }

        // Asked rather than assumed: startActivity throws SecurityException when the
        // package is not permitted, and a crash is a worse diagnostic than a
        // sentence.
        if (!runCatching { dpm.isLockTaskPermitted(kioskPackage) }.getOrDefault(false)) {
            return listOf("kiosk: the system did not permit lock task for $kioskPackage")
        }

        failures += launchIntoLockTask(kioskPackage)
        return failures
    }

    /** Undo everything kiosk set, in the reverse order it was applied. */
    fun releaseKiosk(): List<String> {
        val failures = mutableListOf<String>()

        runCatching {
            // Clearing the allowlist is what actually ejects an app that is
            // currently locked; there is no remote stopLockTask.
            dpm.setLockTaskPackages(admin, emptyArray())
            dpm.setLockTaskFeatures(admin, DevicePolicyManager.LOCK_TASK_FEATURE_NONE)
        }.onFailure { failures += "kiosk: could not clear lock task - ${it.message}" }

        runCatching {
            dpm.clearPackagePersistentPreferredActivities(admin, context.packageName)
        }.onFailure { failures += "kiosk: could not restore the home screen - ${it.message}" }

        return failures
    }

    private fun setHomeTo(packageName: String): List<String> {
        val home = IntentFilter(Intent.ACTION_MAIN).apply {
            addCategory(Intent.CATEGORY_HOME)
            addCategory(Intent.CATEGORY_DEFAULT)
        }
        val activity = context.packageManager
            .getLaunchIntentForPackage(packageName)?.component
            ?: return listOf("kiosk: $packageName has no launchable activity")

        return runCatching {
            dpm.addPersistentPreferredActivity(admin, home, activity)
            emptyList<String>()
        }.getOrElse { listOf("kiosk: could not make $packageName the home screen - ${it.message}") }
    }

    private fun launchIntoLockTask(packageName: String): List<String> {
        val intent = context.packageManager.getLaunchIntentForPackage(packageName)
            ?: return listOf("kiosk: $packageName has no launchable activity")

        // CLEAR_TASK forces a relaunch. Without it an app that is already running
        // stays exactly as it is, outside lock task, and the kiosk silently is not
        // one.
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
        val options = ActivityOptions.makeBasic().setLockTaskEnabled(true).toBundle()

        return runCatching {
            context.startActivity(intent, options)
            AgentLog.i(TAG, "kiosk: launched $packageName into lock task")
            emptyList<String>()
        }.getOrElse { listOf("kiosk: could not launch $packageName - ${it.message}") }
    }

    fun isInstalled(packageName: String): Boolean = runCatching {
        context.packageManager.getPackageInfo(packageName, 0)
        true
    }.getOrDefault(false)

    /**
     * Grant the agent the runtime permissions its own manifest declares.
     *
     * Called on every sync, not only at provisioning, and that is the whole point.
     * Self-granting used to happen once inside `PolicyComplianceActivity`, which
     * never runs again after provisioning — so a permission added in a later agent
     * build stayed **declared and ungranted forever** on every device already in the
     * field, silently.
     *
     * That is not hypothetical. `READ_PHONE_STATE` was added to fix `Build.getSerial()`
     * falling back to `ANDROID_ID` and breaking D24's re-enrolment matching. The
     * manifest comment describing the fix was correct, the permission was correct,
     * and on the one enrolled tablet it was never granted, so the bug it fixed was
     * still happening — with a comment in the tree saying it was solved.
     *
     * Idempotent and cheap: `setPermissionGrantState` on an already-granted
     * permission is a no-op.
     */
    fun ensureSelfPermissions(): List<String> {
        if (!isDeviceOwner) return emptyList()
        val missing = context.packageManager
            .getPackageInfo(context.packageName, PackageManager.GET_PERMISSIONS)
            .requestedPermissions?.toList().orEmpty()
            .filter { isDangerous(it) }
            .filterNot {
                ContextCompat.checkSelfPermission(context, it) ==
                    PackageManager.PERMISSION_GRANTED
            }
        if (missing.isEmpty()) return emptyList()

        AgentLog.i(TAG, "self-granting ${missing.size} permission(s): ${missing.joinToString()}")
        return grantRuntimePermissions(context.packageName)
    }

    /**
     * Hide or unhide a package.
     *
     * **The return value matters and used to be discarded.**
     * `setApplicationHidden` reports failure by returning `false`, not by throwing,
     * so a `runCatching` around it treats "refused" as "done" — which is how a
     * blacklist ends up silently leaving an app usable.
     */
    fun setHidden(packageName: String, hidden: Boolean): String? {
        if (!isDeviceOwner) return "not device owner"
        return runCatching {
            if (dpm.setApplicationHidden(admin, packageName, hidden)) null
            else "the platform refused to ${if (hidden) "hide" else "unhide"} it"
        }.getOrElse { it.message ?: it.javaClass.simpleName }
    }

    fun isHidden(packageName: String): Boolean = runCatching {
        dpm.isApplicationHidden(admin, packageName)
    }.getOrDefault(false)

    private fun isDangerous(permission: String): Boolean = runCatching {
        val info = context.packageManager.getPermissionInfo(permission, 0)
        (info.protection and android.content.pm.PermissionInfo.PROTECTION_DANGEROUS) != 0
    }.getOrDefault(false)

    companion object {
        private const val TAG = "PolicyApplier"
        private const val PERMISSION_MANAGE_EXTERNAL_STORAGE =
            "android.permission.MANAGE_EXTERNAL_STORAGE"
        private val LEGACY_STORAGE_PERMISSIONS = setOf(
            "android.permission.READ_EXTERNAL_STORAGE",
            "android.permission.WRITE_EXTERNAL_STORAGE"
        )
    }
}
