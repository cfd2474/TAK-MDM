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
import android.os.Bundle
import android.content.pm.PackageManager
import android.net.wifi.WifiConfiguration
import android.net.wifi.WifiManager
import android.os.UserManager
import android.provider.Settings
import android.util.Base64
import androidx.core.content.ContextCompat
import com.taksolutions.atlasmdm.core.AgentConfig
import com.taksolutions.atlasmdm.diag.AgentLog
import com.taksolutions.atlasmdm.ui.KioskExitGate
import org.json.JSONArray
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
        // Unconditional, unlike the rest of APP_CATALOG: these latch, so an
        // empty section has to mean "clear what we set" rather than "skip".
        failures += applyAppConfigs(policy.optJSONObject("APP_CATALOG") ?: JSONObject())
        // ⚠️ Kiosk is **not** applied here — see [applyKiosk], called by the
        // reconciler *after* app installs. Locking to an app the device has not
        // installed yet cannot work, and the install is what makes it present
        // (W63).
        failures += applyNetworks(policy.optJSONObject("NETWORKS") ?: JSONObject())
        failures += applyCustomizations(policy.optJSONObject("CUSTOMIZATIONS") ?: JSONObject())
        return failures
    }

    /**
     * Push each app's managed configuration, and clear the ones no longer named.
     *
     * ⚠️ **Keyed on the package being present, not on the DPC having installed
     * it** (W50). A policy naming Chrome 10 on a device already carrying Chrome 12
     * installs nothing — and the configuration must still apply, because the app
     * is there and readable. Tying config to "we installed this" would silently
     * skip exactly the devices an operator is most likely to be looking at.
     *
     * `setApplicationRestrictions` latches like every other DPM setter, so an app
     * dropped from the policy has its configuration cleared rather than left to
     * outlive the policy that set it.
     */
    private fun applyAppConfigs(spec: JSONObject): List<String> {
        val failures = mutableListOf<String>()
        val configured = mutableSetOf<String>()

        val entries = spec.optJSONArray("app_configs") ?: JSONArray()
        for (i in 0 until entries.length()) {
            val entry = entries.optJSONObject(i) ?: continue
            val packageName = entry.optString("package_name").takeIf { it.isNotBlank() } ?: continue
            val values = entry.optJSONObject("values") ?: continue
            val types = entry.optJSONObject("types") ?: JSONObject()

            if (!isInstalled(packageName)) {
                // Not an error: the app may simply not have installed yet, and the
                // install path reports its own failures. Saying it twice would make
                // one problem look like two.
                AgentLog.d(TAG, "$packageName not installed; skipping its configuration")
                continue
            }

            val bundle = Bundle()
            for (key in values.keys()) {
                val raw = values.optString(key)
                val declared = if (types.has(key)) types.optInt(key) else null
                when (val coerced = AppConfigPlan.coerce(key, raw, declared)) {
                    is AppConfigPlan.Value.AsBoolean -> bundle.putBoolean(key, coerced.value)
                    is AppConfigPlan.Value.AsInt -> bundle.putInt(key, coerced.value)
                    is AppConfigPlan.Value.AsString -> bundle.putString(key, coerced.value)
                    // putStringArray, not putString: `getStringArray` returns null
                    // for a scalar and the app falls back to its default silently.
                    is AppConfigPlan.Value.AsStringList ->
                        bundle.putStringArray(key, coerced.value.toTypedArray())
                    is AppConfigPlan.Value.Rejected ->
                        // Reported, never sent as a best guess: a wrong type reads
                        // as the app's default and looks like the setting was
                        // ignored, which is indistinguishable from not trying.
                        failures += "$packageName config: ${coerced.reason}"
                }
            }

            runCatching {
                dpm.setApplicationRestrictions(admin, packageName, bundle)
                configured += packageName
                AgentLog.i(TAG, "applied ${bundle.size()} config keys to $packageName")
            }.onFailure { failures += "$packageName config: ${it.message}" }
        }

        // Anything we configured before and the policy no longer names.
        for (packageName in config.appConfigured - configured) {
            runCatching {
                dpm.setApplicationRestrictions(admin, packageName, Bundle())
                AgentLog.i(TAG, "cleared managed configuration from $packageName")
            }.onFailure { failures += "$packageName config: could not clear - ${it.message}" }
        }
        config.appConfigured = configured

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

        // Kiosk moved to its own KIOSK policy (W59) and is applied from `apply`,
        // not from here.

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
    /**
     * Apply the KIOSK policy, falling back to the old APP_CATALOG location (W59).
     *
     * The fallback is not tidiness. Kiosk lived on APP_CATALOG until W59, and a
     * device whose agent or server is mid-changeover would otherwise drop straight
     * out of kiosk the moment one side deploys — a wall-mounted tablet quietly
     * becoming a general-purpose one.
     */
    /**
     * ⚠️ Called from [Reconciler.sync] **after** app installs, not from [apply].
     *
     * A kiosk policy names an app to lock to, and the server now makes that app a
     * required install (W63) — but installs run after the policy pass. Applied in
     * `apply()` it would fail on the very sync that installs the app, mark the
     * device DEGRADED, and only engage on the next check-in.
     */
    fun applyKioskPolicy(
        kiosk: JSONObject,
        appCatalog: JSONObject,
        restrictions: JSONObject = JSONObject(),
    ): List<String> {
        val pkg = kiosk.optString("kiosk_package").takeIf { it.isNotBlank() }
            ?: appCatalog.optString("kiosk_package").takeIf { it.isNotBlank() }
        return applyKiosk(pkg, kiosk, restrictions)
    }

    fun applyKiosk(
        kioskPackage: String?,
        spec: JSONObject = JSONObject(),
        restrictions: JSONObject = JSONObject(),
    ): List<String> {
        val failures = mutableListOf<String>()

        if (kioskPackage == null) {
            KioskExitGate.remove(context)
            config.kioskExitedAtElapsed = 0L
            failures += releaseKiosk(restrictions)
            return failures
        }

        // ⚠️ Someone at the device left kiosk with the passcode (W65). Policy still
        // says kiosk, and policy is not wrong — but re-locking them out two minutes
        // later would make the exit useless, so the device's answer stands until it
        // reboots or the operator turns auto re-entry on.
        //
        // elapsedRealtime, not wall clock: it resets on reboot, which *is* the
        // rule, and cannot be moved by changing the device's date.
        if (config.kioskExitedAtElapsed > 0) {
            if (!spec.optBoolean("auto_reenter_kiosk", false)) {
                AgentLog.i(TAG, "kiosk: exited on-device; leaving it out until reboot")
                return failures
            }
            config.kioskExitedAtElapsed = 0L
        }

        // A delay after boot, so "reboot and tap to exit" has a window to happen in
        // — and so an engineer at a device whose kiosk app is the problem is not
        // racing the lock.
        val relaunchAfter = spec.optInt("relaunch_after_reboot_seconds", 0) * 1000L
        val sinceBoot = android.os.SystemClock.elapsedRealtime()
        if (relaunchAfter > 0 && sinceBoot < relaunchAfter) {
            armExitGate(spec, kioskPackage)
            AgentLog.i(
                TAG,
                "kiosk: holding off ${(relaunchAfter - sinceBoot) / 1000}s more after boot"
            )
            return failures
        }

        if (!isInstalled(kioskPackage)) {
            // Locking the device to an app that is not there would leave it on a
            // blank screen with no way out. Refuse, and say what happens next —
            // the server requires the kiosk app, so this is normally a sync that
            // has not finished installing rather than a policy that is wrong.
            return listOf(
                "kiosk: $kioskPackage is not installed yet, so the device was not " +
                    "locked to it. It is a required app and should install on this " +
                    "or the next check-in; if it never does, the install error says why."
            )
        }

        // Before the features are set, because those enable HOME. Doing it the
        // other way round leaves a window in which the home button is live and
        // still points at the system launcher.
        failures += setHomeTo(kioskPackage)

        runCatching {
            // The kiosk app, this agent, and anything the policy names as a
            // background app — a keyboard, a VPN client, an app the kiosk hands
            // off to. Without being on this list, entering one of those breaks
            // the user out of lock task entirely.
            val permitted = linkedSetOf(kioskPackage, context.packageName)
            spec.optJSONArray("background_packages")?.let { extras ->
                for (i in 0 until extras.length()) {
                    extras.optString(i).takeIf { it.isNotBlank() }?.let { permitted += it }
                }
            }
            dpm.setLockTaskPackages(admin, permitted.toTypedArray())
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
            dpm.setLockTaskFeatures(admin, lockTaskFeatures(spec))
        }.onFailure { return listOf("kiosk: could not configure lock task - ${it.message}") }

        // Asked rather than assumed: startActivity throws SecurityException when the
        // package is not permitted, and a crash is a worse diagnostic than a
        // sentence.
        if (!runCatching { dpm.isLockTaskPermitted(kioskPackage) }.getOrDefault(false)) {
            return listOf("kiosk: the system did not permit lock task for $kioskPackage")
        }

        armExitGate(spec, kioskPackage)
        failures += applyKioskPeripherals(spec)
        failures += launchIntoLockTask(
            kioskPackage,
            spec.optString("kiosk_activity").takeIf { it.isNotBlank() },
        )
        return failures
    }

    /**
     * Which lock-task features the user keeps, from the Kiosk policy (W59).
     *
     * ⚠️ Every flag omitted here is **implicitly disabled** — `setLockTaskFeatures`
     * replaces the set rather than adding to it. That is why each default is
     * stated rather than left out, and why the power menu defaults to *on*:
     * dropping GLOBAL_ACTIONS removes the only on-device way to power off, and a
     * field device that then misbehaves is recoverable by factory reset and little
     * else.
     *
     * HOME defaults on because `setHomeTo()` has already pointed it at the kiosk
     * app, so it returns there rather than escaping to the launcher — and because
     * NOTIFICATIONS cannot be set without it. The server refuses that combination
     * before it reaches here; this keeps the device safe if an older server sends
     * one anyway, since from Android 14 a rejected feature set takes the package
     * allowlist down with it.
     */
    private fun lockTaskFeatures(spec: JSONObject): Int {
        fun keeps(key: String, default: Boolean): Boolean =
            if (spec.has(key) && !spec.isNull(key)) spec.optBoolean(key, default) else default

        val home = keeps("keep_home_button", true)
        // Asked for but impossible without HOME: honour the intent by keeping HOME
        // rather than dropping notifications, because HOME is already safe here.
        val notifications = keeps("keep_notifications", true)

        var features = 0
        if (keeps("keep_power_menu", true)) {
            features = features or DevicePolicyManager.LOCK_TASK_FEATURE_GLOBAL_ACTIONS
        }
        if (home || notifications) features = features or DevicePolicyManager.LOCK_TASK_FEATURE_HOME
        if (notifications) {
            features = features or DevicePolicyManager.LOCK_TASK_FEATURE_NOTIFICATIONS
        }
        if (keeps("keep_recents_button", false)) {
            features = features or DevicePolicyManager.LOCK_TASK_FEATURE_OVERVIEW
        }
        if (keeps("keep_system_info", true)) {
            features = features or DevicePolicyManager.LOCK_TASK_FEATURE_SYSTEM_INFO
        }
        if (keeps("keep_keyguard", true)) {
            features = features or DevicePolicyManager.LOCK_TASK_FEATURE_KEYGUARD
        }
        // ⚠️ "Restrict to this activity only", and it is worth being precise about
        // what it buys. This blocks activities that are **not on the lock-task
        // allowlist** from opening inside the locked task. It does *not* stop the
        // kiosk app moving between its own screens: an app in lock task may start
        // its own activities freely, and Android has no per-activity lock. The
        // console says so on the field rather than letting the name imply more.
        if (spec.optBoolean("kiosk_restrict_to_activity", false)) {
            features = features or
                DevicePolicyManager.LOCK_TASK_FEATURE_BLOCK_ACTIVITY_START_IN_TASK
        }
        return features
    }

    /**
     * Peripheral restrictions that hold **only while the device is in kiosk** (W59).
     *
     * The operator's design, and a better one than a second copy of the
     * Restrictions policy: a device bolted to a wall wants different rules from the
     * same device in someone's hand, so the overlap is resolved in *time* rather
     * than by two policies disagreeing about one setting.
     *
     * ⚠️ Which means [releaseKiosk] must put every one of these back. A restriction
     * applied on entry and left behind on exit would follow the device out of
     * kiosk, and nothing in the Restrictions policy would ever take it off — the
     * latching trap this file already carries three scars from.
     */
    private fun applyKioskPeripherals(spec: JSONObject): List<String> {
        val failures = mutableListOf<String>()
        for ((key, restriction) in KIOSK_PERIPHERALS) {
            if (!spec.has(key) || spec.isNull(key)) continue
            val allowed = spec.optBoolean(key, true)
            runCatching {
                if (allowed) dpm.clearUserRestriction(admin, restriction)
                else dpm.addUserRestriction(admin, restriction)
            }.onFailure {
                failures += "kiosk peripheral $key: ${it.message}"
            }
        }
        // Camera and screen capture have dedicated setters rather than user
        // restrictions, so they sit outside the loop above.
        if (spec.has("kiosk_allow_camera") && !spec.isNull("kiosk_allow_camera")) {
            runCatching {
                dpm.setCameraDisabled(admin, !spec.optBoolean("kiosk_allow_camera", true))
            }.onFailure { failures += "kiosk peripheral camera: ${it.message}" }
        }
        if (spec.has("kiosk_allow_screen_capture") && !spec.isNull("kiosk_allow_screen_capture")) {
            runCatching {
                dpm.setScreenCaptureDisabled(admin, !spec.optBoolean("kiosk_allow_screen_capture", true))
            }.onFailure { failures += "kiosk peripheral screen capture: ${it.message}" }
        }
        return failures
    }

    /**
     * Hand the device back to the ordinary Restrictions policy (W59).
     *
     * ⚠️ **Restores what Restrictions asked for; it does not blanket-clear.**
     * Three of these — camera, Bluetooth, screen capture — are also Restrictions
     * fields, and `applyRestrictions` has already run by the time this does. A
     * clear-everything release therefore undid the Restrictions policy on *every*
     * sync of *every* device, kiosk or not: block Bluetooth in Restrictions, and
     * the next check-in silently switched it back on.
     *
     * So each peripheral is handed back to whatever Restrictions says about it,
     * and only genuinely kiosk-only ones (Wi-Fi config, volume, brightness,
     * airplane mode) are cleared.
     */
    private fun releaseKioskPeripherals(restrictions: JSONObject): List<String> {
        val failures = mutableListOf<String>()

        for ((kioskKey, restriction) in KIOSK_PERIPHERALS) {
            val owner = RESTRICTIONS_EQUIVALENT[kioskKey]
            val allowed = when {
                owner != null && restrictions.has(owner) && !restrictions.isNull(owner) ->
                    restrictions.optBoolean(owner, true)
                // Kiosk-only, or Restrictions is silent: kiosk had no business
                // holding it once the device is out.
                else -> true
            }
            runCatching {
                if (allowed) dpm.clearUserRestriction(admin, restriction)
                else dpm.addUserRestriction(admin, restriction)
            }.onFailure { failures += "kiosk peripheral release: ${it.message}" }
        }

        // The two with their own setters, restored the same way.
        runCatching {
            dpm.setCameraDisabled(admin, !restrictions.optBoolean("allow_camera", true))
        }
        runCatching {
            dpm.setScreenCaptureDisabled(
                admin, !restrictions.optBoolean("allow_screen_capture", true)
            )
        }
        return failures
    }

    /**
     * Arm or disarm the on-device exit (W65).
     *
     * Idempotent, and called on every reconcile: a kiosk that is still a kiosk must
     * not stack a new overlay every two minutes.
     */
    private fun armExitGate(spec: JSONObject, kioskPackage: String) {
        val allowed = spec.optBoolean("allow_manual_exit", false)
        val passcode = spec.optString("exit_password")
        KioskExitGate.set(
            context,
            enabled = allowed,
            tapCount = spec.optInt("exit_tap_count", 10),
            passcode = passcode,
        ) {
            // Recorded *before* releasing, so a crash between the two leaves the
            // device out of kiosk with the reason known, rather than locked again
            // with no trace of why someone was trying to get out.
            config.kioskExitedAtElapsed = android.os.SystemClock.elapsedRealtime()
            AgentLog.i(TAG, "kiosk: released on-device by passcode for $kioskPackage")
            releaseKiosk(JSONObject())
            KioskExitGate.remove(context)
        }
    }

    /** Undo everything kiosk set, in the reverse order it was applied. */
    fun releaseKiosk(restrictions: JSONObject = JSONObject()): List<String> {
        val failures = mutableListOf<String>()

        // ⚠️ First, and unconditionally. Kiosk peripheral rules apply only while
        // the device is locked in; left behind they would follow it out of kiosk,
        // and the Restrictions policy has no way to know it should take them off.
        failures += releaseKioskPeripherals(restrictions)

        runCatching {
            // Clearing the allowlist is what actually ejects an app that is
            // currently locked; there is no remote stopLockTask.
            dpm.setLockTaskPackages(admin, emptyArray())
            dpm.setLockTaskFeatures(admin, DevicePolicyManager.LOCK_TASK_FEATURE_NONE)
        }.onFailure { failures += "kiosk: could not clear lock task - ${it.message}" }

        runCatching {
            dpm.clearPackagePersistentPreferredActivities(admin, context.packageName)
        }.onFailure { failures += "kiosk: could not restore the home screen - ${it.message}" }

        // Here rather than in the callers, because this is the one place the
        // device actually leaves lock task — the on-device passcode exit reaches
        // it too. Re-entering kiosk later must force a real relaunch, not
        // re-front an app that is no longer locked to anything (W67).
        config.kioskLaunched = null
        config.kioskLaunchedAtElapsed = 0L

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

    private fun launchIntoLockTask(packageName: String, activity: String? = null): List<String> {
        // A named activity is an explicit component, not the app's launcher entry.
        // Some kiosk screens are deliberately not the default one — and some are
        // not exported as launchers at all — so "select app with activity" cannot
        // go through getLaunchIntentForPackage (W61).
        val intent = if (activity != null) {
            Intent(Intent.ACTION_MAIN).setComponent(
                android.content.ComponentName(
                    packageName,
                    // A leading dot is Android's shorthand for "relative to the
                    // package", the same trap component_class() fixes server-side.
                    if (activity.startsWith(".")) packageName + activity else activity,
                )
            )
        } else {
            context.packageManager.getLaunchIntentForPackage(packageName)
                ?: return listOf("kiosk: $packageName has no launchable activity")
        }

        // ⚠️ CLEAR_TASK is right **once** and destructive every time after: see
        // KioskLaunchPlan, which owns the decision and says why (W67).
        val component = (activity?.let { "$packageName/$it" } ?: packageName)
        val now = android.os.SystemClock.elapsedRealtime()
        val action = KioskLaunchPlan.decide(
            wanted = component,
            launched = config.kioskLaunched,
            launchedAtElapsed = config.kioskLaunchedAtElapsed,
            nowElapsed = now,
        )
        val fresh = action == KioskLaunchPlan.Action.RELAUNCH

        intent.addFlags(
            if (fresh) Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            else Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP
        )
        val options = ActivityOptions.makeBasic().setLockTaskEnabled(true).toBundle()

        return runCatching {
            context.startActivity(intent, options)
            config.kioskLaunched = component
            config.kioskLaunchedAtElapsed = now
            // Says which of the two happened, because "launched" logged every two
            // minutes was the symptom and read as normal.
            AgentLog.i(
                TAG,
                if (fresh) "kiosk: launched $component into lock task"
                else "kiosk: $component already in lock task; brought to front"
            )
            emptyList<String>()
        }.getOrElse {
            // Names the component, because "could not launch" against a mistyped
            // class is the likeliest failure here and the class is the clue.
            val what = activity?.let { a -> "$packageName/$a" } ?: packageName
            listOf("kiosk: could not launch $what - ${it.message}")
        }
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

        /**
         * Kiosk peripheral field → the `UserManager` restriction that enforces it.
         *
         * Every one is a documented Device Owner restriction, so this whole section
         * works on AOSP with no OEM extension. Camera and screen capture are
         * deliberately absent: neither is a user restriction — there is no
         * `DISALLOW_CAMERA` — and both have their own setter.
         */
        /**
         * Kiosk peripheral field → the Restrictions field that owns it outside
         * kiosk. Absent means kiosk-only, and clearing it on exit is correct.
         */
        private val RESTRICTIONS_EQUIVALENT = mapOf(
            "kiosk_allow_bluetooth" to "allow_bluetooth",
            "kiosk_allow_camera" to "allow_camera",
            "kiosk_allow_screen_capture" to "allow_screen_capture",
        )

        private val KIOSK_PERIPHERALS = linkedMapOf(
            "kiosk_allow_bluetooth" to UserManager.DISALLOW_BLUETOOTH,
            "kiosk_allow_wifi_config" to UserManager.DISALLOW_CONFIG_WIFI,
            "kiosk_allow_volume_change" to UserManager.DISALLOW_ADJUST_VOLUME,
            "kiosk_allow_brightness_change" to UserManager.DISALLOW_CONFIG_BRIGHTNESS,
            "kiosk_allow_airplane_mode" to UserManager.DISALLOW_AIRPLANE_MODE,
        )
    }
}
