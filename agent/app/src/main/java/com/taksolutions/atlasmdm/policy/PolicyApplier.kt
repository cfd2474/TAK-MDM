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

package com.taksolutions.atlasmdm.policy

import android.app.WallpaperManager
import android.app.admin.DevicePolicyManager
import android.app.ActivityOptions
import android.content.Intent
import android.content.IntentFilter
import android.content.Context
import android.content.pm.PackageManager
import android.net.wifi.WifiConfiguration
import android.net.wifi.WifiManager
import android.os.UserManager
import android.provider.Settings
import android.util.Base64
import androidx.core.content.ContextCompat
import com.taksolutions.atlasmdm.core.AgentConfig
import com.taksolutions.atlasmdm.diag.AgentLog
import org.json.JSONObject
import java.io.File
import com.taksolutions.atlasmdm.admin.MdmDeviceAdminReceiver

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

    private val config: AgentConfig by lazy { AgentConfig(context) }

    private val oem: OemPolicyApplier by lazy { OemPolicyApplier.forDevice(context) }

    val isDeviceOwner: Boolean
        get() = dpm.isDeviceOwnerApp(context.packageName)

    fun apply(policy: JSONObject): List<String> {
        if (!isDeviceOwner) {
            return listOf("not device owner; policy cannot be applied")
        }
        val failures = mutableListOf<String>()
        // ⚠️ PASSWORD, RESTRICTIONS and NETWORKS run **even when their section is
        // absent**, because every one of them can leave something behind on the
        // device that only they can take away.
        //
        // Skipping an absent section looks harmless and is the same bug as R14 and
        // R19 one level up: DevicePolicyManager setters latch, so "no policy says
        // anything" has to be pushed as a state, not treated as no work. Removing
        // the last PASSWORD policy left `minimumPasswordLength` stuck at its old
        // value — the W26 fix drove those fields to permissive but never ran,
        // because there was no section left to carry them. Removing the last
        // RESTRICTIONS policy left the screen timeout stuck the same way (R19), and
        // its restore could not fire for the same reason.
        //
        // APP_CATALOG stays conditional on purpose: "no policy requires any apps"
        // means leave the device's apps alone, not uninstall them.
        failures += applyPassword(policy.optJSONObject("PASSWORD") ?: JSONObject())
        failures += applyRestrictions(policy.optJSONObject("RESTRICTIONS") ?: JSONObject())
        policy.optJSONObject("APP_CATALOG")?.let { failures += applyAppCatalog(it) }
        failures += applyNetworks(policy.optJSONObject("NETWORKS") ?: JSONObject())
        failures += applyCustomizations(policy.optJSONObject("CUSTOMIZATIONS") ?: JSONObject())
        return failures
    }

    // ----------------------------------------------------------------------- //
    // Operator-authored text shown on the device (W42)
    // ----------------------------------------------------------------------- //

    /**
     * Push the support messages and the lock screen message, or clear them.
     *
     * All three latch, so this runs even with no CUSTOMIZATIONS section at all and
     * pushes `null` for whatever the policy does not carry — the same rule as the
     * passcode and restriction families above. Unlike `setPasswordMinimumLength`
     * (W41) none of these gate on any other state, so clearing is always safe.
     *
     * Blank collapses to `null` rather than `""` — see [CustomizationsPlan], where
     * that rule lives and is tested, because for the lock screen the two are
     * genuinely different instructions to the platform.
     */
    private fun applyCustomizations(spec: JSONObject): List<String> {
        val failures = mutableListOf<String>()

        runCatching {
            dpm.setShortSupportMessage(
                admin, CustomizationsPlan.message(spec, "disabled_setting_message")
            )
        }.onFailure { failures += "disabled setting message: ${it.message}" }

        runCatching {
            dpm.setLongSupportMessage(
                admin, CustomizationsPlan.message(spec, "admin_app_description")
            )
        }.onFailure { failures += "admin app description: ${it.message}" }

        runCatching {
            dpm.setDeviceOwnerLockScreenInfo(
                admin, CustomizationsPlan.message(spec, "lock_screen_message")
            )
        }.onFailure { failures += "lock screen message: ${it.message}" }

        return failures
    }

    // ----------------------------------------------------------------------- //
    // Passcode
    // ----------------------------------------------------------------------- //

    @Suppress("DEPRECATION")
    private fun applyPassword(spec: JSONObject): List<String> {
        val failures = mutableListOf<String>()

        // The granular setPasswordMinimum* family, not the complexity buckets: it
        // maps 1:1 onto the spec (quality / min_length / min_letters / min_digits
        // / min_symbols) and a Device Owner on a company-owned device may still
        // use it (see the Android platform reference §6c). setPasswordQuality
        // must run first — the per-character-class setters throw below COMPLEX,
        // and calling it also clears any earlier setRequiredPasswordComplexity.
        val quality = PasswordPlan.effectiveQuality(
            quality = spec.optInt("quality").takeIf { spec.has("quality") },
            minLength = spec.optInt("min_length").takeIf { spec.has("min_length") },
            minLetters = spec.optInt("min_letters").takeIf { spec.has("min_letters") },
            minDigits = spec.optInt("min_digits").takeIf { spec.has("min_digits") },
            minSymbols = spec.optInt("min_symbols").takeIf { spec.has("min_symbols") },
        )
        // R14: every field below is driven to a definite value on every reconcile,
        // and the value for "absent" is the permissive one. Only setting a field
        // when the spec carries it left the previous value latched on the device
        // forever — which is how a `minimumPasswordLength` of 13, from a policy
        // that no longer applied, silently rejected a later 4-digit passcode with
        // no way to clear it from the console. Absent means "not managed", which
        // on the device has to mean "not enforced", exactly as the boolean
        // `allow_*` restrictions already behave.
        fun scalar(key: String): Int? = spec.optInt(key).takeIf { spec.has(key) }

        runCatching {
            dpm.setPasswordQuality(admin, dpmPasswordQuality(quality))
        }.onFailure { failures += "password quality: ${it.message}" }

        // Only reachable at NUMERIC or above: below it the platform throws
        // IllegalStateException even for a release to 0 (PasswordPlan
        // .minLengthApplies), and the value is inert anyway — so there is
        // nothing latched that can bite when quality is below NUMERIC.
        if (PasswordPlan.minLengthApplies(quality)) {
            runCatching {
                dpm.setPasswordMinimumLength(admin, scalar("min_length") ?: 0)
            }.onFailure { failures += "password min length: ${it.message}" }
        }

        // Only reachable at COMPLEX: below it these setters throw for an app
        // targeting API 30+, and the values are inert. So when quality is not
        // COMPLEX there is nothing latched that can bite, and nothing to release.
        if (PasswordPlan.charClassMinimumsApply(quality)) {
            runCatching {
                dpm.setPasswordMinimumLetters(admin, scalar("min_letters") ?: 0)
            }.onFailure { failures += "password min letters: ${it.message}" }
            runCatching {
                dpm.setPasswordMinimumNumeric(admin, scalar("min_digits") ?: 0)
            }.onFailure { failures += "password min digits: ${it.message}" }
            runCatching {
                dpm.setPasswordMinimumSymbols(admin, scalar("min_symbols") ?: 0)
            }.onFailure { failures += "password min symbols: ${it.message}" }
        }

        // 0 means "never wipe". Leaving a stale attempt limit latched is the most
        // dangerous case of this bug: a device could wipe itself to satisfy a
        // policy nobody had assigned to it for months.
        runCatching {
            dpm.setMaximumFailedPasswordsForWipe(
                admin, scalar("max_failed_attempts_before_wipe") ?: 0
            )
        }.onFailure { failures += "max failed attempts: ${it.message}" }

        // 0 means "no restriction beyond the user's own choice".
        runCatching {
            dpm.setMaximumTimeToLock(admin, (scalar("lock_timeout_seconds") ?: 0) * 1000L)
        }.onFailure { failures += "lock timeout: ${it.message}" }

        // 0 means "never expires".
        runCatching {
            dpm.setPasswordExpirationTimeout(
                admin, (scalar("expiration_days") ?: 0) * 86_400_000L
            )
        }.onFailure { failures += "password expiry: ${it.message}" }

        // Not deprecated with the setPasswordMinimum* family at API 31 — history
        // length has no complexity-bucket equivalent and still applies directly.
        runCatching {
            dpm.setPasswordHistoryLength(admin, scalar("history_length") ?: 0)
        }.onFailure { failures += "password history: ${it.message}" }

        // Force an exact passcode (W20). Last, so the quality/length constraints
        // above are in place before resetPasswordWithToken checks the value
        // against them. Re-asserted on every reconcile — Android has no way to
        // stop the user changing it, so setting it back is the only enforcement.
        if (spec.has("set_password")) {
            failures += ensurePasswordSet(spec.getString("set_password"))
        }

        return failures
    }

    /**
     * Make the device's screen-lock passcode equal [desired].
     *
     * `resetPasswordWithToken` needs a reset token from `setResetPasswordToken`
     * (≥32 bytes). The token activates immediately only if the device has no
     * passcode; if one is already set, the user must confirm their current
     * credential once before it works — which cannot be forced, so that case is
     * reported rather than worked around. The token is kept in the agent's
     * private prefs (same store as the enrollment secret) so it survives a
     * process restart; an un-activated one is lost on reboot and regenerated.
     */
    private fun ensurePasswordSet(desired: String): List<String> {
        if (desired.isBlank()) return emptyList()
        val failures = mutableListOf<String>()

        val token = loadOrCreateResetToken()

        if (!dpm.isResetPasswordTokenActive(admin)) {
            val set = runCatching { dpm.setResetPasswordToken(admin, token) }
                .onFailure { failures += "set passcode: reset token rejected: ${it.message}" }
                .getOrDefault(false)
            if (!set) return failures
            if (!dpm.isResetPasswordTokenActive(admin)) {
                failures += "set passcode: the device already has a passcode, so the " +
                    "reset token needs the user to confirm it once " +
                    "(Settings ▸ security ▸ confirm credentials) before it can be changed"
                return failures
            }
        }

        val ok = runCatching { dpm.resetPasswordWithToken(admin, desired, token, 0) }
            .onFailure { failures += "set passcode: ${it.message}" }
            .getOrDefault(false)
        if (!ok && failures.isEmpty()) {
            failures += "set passcode: rejected — the value does not meet the policy's " +
                "own length/quality rules"
        } else if (ok) {
            AgentLog.i(TAG, "passcode set from policy (${desired.length} chars)")
        }
        return failures
    }

    private fun loadOrCreateResetToken(): ByteArray {
        config.resetPasswordToken?.let { stored ->
            runCatching { Base64.decode(stored, Base64.NO_WRAP) }.getOrNull()
                ?.takeIf { it.size >= 32 }
                ?.let { return it }
        }
        val fresh = ByteArray(32).also { java.security.SecureRandom().nextBytes(it) }
        config.resetPasswordToken = Base64.encodeToString(fresh, Base64.NO_WRAP)
        return fresh
    }

    @Suppress("DEPRECATION")
    private fun dpmPasswordQuality(q: PasswordPlan.PwQuality): Int = when (q) {
        PasswordPlan.PwQuality.UNSPECIFIED -> DevicePolicyManager.PASSWORD_QUALITY_UNSPECIFIED
        PasswordPlan.PwQuality.SOMETHING -> DevicePolicyManager.PASSWORD_QUALITY_SOMETHING
        PasswordPlan.PwQuality.NUMERIC -> DevicePolicyManager.PASSWORD_QUALITY_NUMERIC
        PasswordPlan.PwQuality.NUMERIC_COMPLEX -> DevicePolicyManager.PASSWORD_QUALITY_NUMERIC_COMPLEX
        PasswordPlan.PwQuality.ALPHABETIC -> DevicePolicyManager.PASSWORD_QUALITY_ALPHABETIC
        PasswordPlan.PwQuality.ALPHANUMERIC -> DevicePolicyManager.PASSWORD_QUALITY_ALPHANUMERIC
        PasswordPlan.PwQuality.COMPLEX -> DevicePolicyManager.PASSWORD_QUALITY_COMPLEX
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

        // SCREEN_OFF_TIMEOUT is one of the three system settings a Device Owner may
        // write via setSystemSetting (API 28). Milliseconds, as a string. Applies
        // even when DISALLOW_CONFIG_SCREEN_TIMEOUT is set.
        //
        // It latches, and unlike the password minimums it has no permissive value
        // to push instead — so the agent remembers what it displaced and puts that
        // back when the field goes away (R19). See ScreenTimeoutPlan.
        failures += applyScreenTimeout(spec)

        failures += oem.applyRestrictions(context, spec)
        return failures
    }

    /**
     * Set [image] as the wallpaper. Returns null on success, or the reason.
     *
     * ⚠️ Order matters. `DISALLOW_SET_WALLPAPER` is applied **after** the image,
     * because the restriction may block the agent as well as the user — it is a
     * user restriction, not an admin exemption, and nothing in the documentation
     * promises the setter is exempt. Setting it first would risk a policy that
     * permanently prevents its own image from ever being applied.
     */
    fun setWallpaper(image: File, alsoLockScreen: Boolean, preventUserChange: Boolean): String? {
        val manager = WallpaperManager.getInstance(context)

        val failure = runCatching {
            // Cleared first: an existing restriction from a previous reconcile would
            // otherwise block this write, and the device would keep the old image
            // with no indication why.
            runCatching { dpm.clearUserRestriction(admin, UserManager.DISALLOW_SET_WALLPAPER) }

            var which = WallpaperManager.FLAG_SYSTEM
            if (alsoLockScreen) which = which or WallpaperManager.FLAG_LOCK
            image.inputStream().use { stream ->
                manager.setStream(stream, null, true, which)
            }
        }.exceptionOrNull()

        if (failure != null) {
            return "${failure.javaClass.simpleName}: ${failure.message ?: "no message"}"
        }

        if (preventUserChange) {
            runCatching { dpm.addUserRestriction(admin, UserManager.DISALLOW_SET_WALLPAPER) }
                .onFailure { return "image applied, but the user restriction failed: ${it.message}" }
        }
        return null
    }

    /**
     * Put the device back on its factory wallpaper. Returns null on success.
     *
     * The restriction is lifted first: `DISALLOW_SET_WALLPAPER` may block the agent
     * as well as the user, and a policy that left it in place would strand the
     * device on an image no policy asks for and the user cannot change.
     */
    fun clearWallpaper(): String? {
        runCatching { dpm.clearUserRestriction(admin, UserManager.DISALLOW_SET_WALLPAPER) }
        return runCatching {
            WallpaperManager.getInstance(context)
                .clear(WallpaperManager.FLAG_SYSTEM or WallpaperManager.FLAG_LOCK)
        }.fold({ null }, { "${it.javaClass.simpleName}: ${it.message ?: "no message"}" })
    }

    private fun applyScreenTimeout(spec: JSONObject): List<String> {
        val config = AgentConfig(context)
        val desired = if (spec.has("screen_timeout_seconds")) {
            spec.getInt("screen_timeout_seconds")
        } else {
            null
        }
        val saved = config.savedScreenTimeoutMillis.takeIf { it >= 0 }
        val current = runCatching {
            Settings.System.getInt(context.contentResolver, Settings.System.SCREEN_OFF_TIMEOUT)
        }.getOrNull()

        return when (val action = ScreenTimeoutPlan.decide(desired, current, saved)) {
            is ScreenTimeoutPlan.Action.Nothing -> emptyList()

            is ScreenTimeoutPlan.Action.Apply -> {
                // Recorded *before* the write. A crash between the two would
                // otherwise leave the setting changed with nothing remembering what
                // it replaced — the exact state R19 describes.
                action.remember?.let { config.savedScreenTimeoutMillis = it }
                runCatching {
                    dpm.setSystemSetting(
                        admin, Settings.System.SCREEN_OFF_TIMEOUT, action.millis.toString()
                    )
                }.fold({ emptyList() }, { listOf("screen timeout: ${it.message}") })
            }

            is ScreenTimeoutPlan.Action.Restore -> {
                AgentLog.i(
                    TAG,
                    "no policy sets a screen timeout; restoring the ${action.millis} ms " +
                        "the first policy displaced"
                )
                runCatching {
                    dpm.setSystemSetting(
                        admin, Settings.System.SCREEN_OFF_TIMEOUT, action.millis.toString()
                    )
                }.fold(
                    {
                        // Only forgotten once the write succeeded, so a failure is
                        // retried on the next reconcile rather than losing the value.
                        config.savedScreenTimeoutMillis = -1
                        emptyList()
                    },
                    { listOf("screen timeout restore: ${it.message}") }
                )
            }
        }
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
                // network auto-joins by default and there is no public per-network
                // auto-join toggle for a DO (the spec dropped the field in W18).
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

    /**
     * Suspend or un-suspend a set of packages (`allowed_packages` enforcement).
     * `setPackagesSuspended` returns the packages it *refused* — the DPC, the
     * active launcher, the package installer, the default dialer and the
     * permission controller are all protected regardless of what we ask.
     *
     * Returns those refusals as error strings; an empty list means every package
     * took effect.
     */
    fun setSuspended(packages: Set<String>, suspended: Boolean): List<String> {
        if (packages.isEmpty()) return emptyList()
        if (!isDeviceOwner) return listOf("not device owner")
        val verb = if (suspended) "suspend" else "un-suspend"
        return runCatching {
            dpm.setPackagesSuspended(admin, packages.toTypedArray(), suspended)
                .map { "$it: platform refused to $verb it" }
        }.getOrElse { listOf("$verb: ${it.message ?: it.javaClass.simpleName}") }
    }

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
