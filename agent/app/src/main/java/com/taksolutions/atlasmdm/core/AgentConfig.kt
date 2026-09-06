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

package com.taksolutions.atlasmdm.core

import android.content.Context
import android.content.SharedPreferences
import androidx.core.content.edit

/**
 * Persistent agent settings.
 *
 * Seeded from the provisioning extras bundle that QR or Knox Mobile Enrollment
 * delivers, then updated as enrollment progresses.
 */
class AgentConfig(context: Context) {

    private val prefs: SharedPreferences =
        context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    var serverUrl: String?
        get() = prefs.getString(KEY_SERVER_URL, null)
        set(value) = prefs.edit { putString(KEY_SERVER_URL, value) }

    /** One-time enrollment secret. Cleared once a certificate is held. */
    var enrollmentToken: String?
        get() = prefs.getString(KEY_ENROLL_TOKEN, null)
        set(value) = prefs.edit { putString(KEY_ENROLL_TOKEN, value) }

    /**
     * PEM of the CA that signed the server's TLS certificate.
     *
     * Only needed for a self-signed development server. Absent means the platform
     * trust store is used, which is what a real deployment does.
     */
    var serverCaPem: String?
        get() = prefs.getString(KEY_SERVER_CA, null)
        set(value) = prefs.edit { putString(KEY_SERVER_CA, value) }

    var deviceId: String?
        get() = prefs.getString(KEY_DEVICE_ID, null)
        set(value) = prefs.edit { putString(KEY_DEVICE_ID, value) }

    /**
     * The friendly device name the operator set on the server, echoed back on
     * every check-in so the on-device console can show it. Null until the first
     * check-in after enrolment, or when the operator has not named the device.
     */
    var deviceName: String?
        get() = prefs.getString(KEY_DEVICE_NAME, null)
        set(value) = prefs.edit { putString(KEY_DEVICE_NAME, value) }

    /**
     * Names of the policies currently reaching this device, echoed on every
     * check-in. The on-device console lists these instead of policy content —
     * the desired-state bundle carries values only, no names.
     */
    var policyNames: List<String>
        get() = prefs.getString(KEY_POLICY_NAMES, "")
            ?.split("\n")?.filter { it.isNotBlank() } ?: emptyList()
        set(value) = prefs.edit { putString(KEY_POLICY_NAMES, value.joinToString("\n")) }

    /** Ed25519 public key, base64, pinned at enrollment to verify policy bundles. */
    var bundleKeyBase64: String?
        get() = prefs.getString(KEY_BUNDLE_KEY, null)
        set(value) = prefs.edit { putString(KEY_BUNDLE_KEY, value) }

    /**
     * Base64 of the 32-byte reset-password token (W20), kept so a forced passcode
     * (`PASSWORD.set_password`) can be re-applied after a process restart.
     *
     * Android warns this is credential-grade and must not be stored in plaintext.
     * It sits in the agent's private prefs alongside [enrollmentToken] — the same
     * exposure envelope — which is the pragmatic choice for a normally-installed
     * Device Owner with no keystore-wrapped prefs. An un-activated token is
     * memory-only in the OS and lost on reboot; the agent regenerates one.
     */
    var resetPasswordToken: String?
        get() = prefs.getString(KEY_RESET_PW_TOKEN, null)
        set(value) = prefs.edit { putString(KEY_RESET_PW_TOKEN, value) }

    /** The desired-state version the agent currently holds. */
    var stateVersion: Int
        get() = prefs.getInt(KEY_STATE_VERSION, -1)
        set(value) = prefs.edit { putInt(KEY_STATE_VERSION, value) }

    /** The version last applied cleanly. Distinct from what is held (D28). */
    var appliedStateVersion: Int
        get() = prefs.getInt(KEY_APPLIED_VERSION, 0)
        set(value) = prefs.edit { putInt(KEY_APPLIED_VERSION, value) }

    /** The last desired-state document, so a reboot need not wait for a fetch. */
    var cachedDesiredState: String?
        get() = prefs.getString(KEY_DESIRED_STATE, null)
        set(value) = prefs.edit { putString(KEY_DESIRED_STATE, value) }

    /**
     * The last sync failure, kept so it can be read off the device's own screen.
     *
     * Diagnosing an agent that will not enrol otherwise requires USB debugging,
     * which needs Developer Options enabled on a device that may already be locked
     * down — exactly when the information is hardest to get and most needed.
     */
    var lastError: String?
        get() = prefs.getString(KEY_LAST_ERROR, null)
        set(value) = prefs.edit { putString(KEY_LAST_ERROR, value) }

    /** Problems from the last apply, reported to the server on the next check-in. */
    var lastApplyErrors: List<String>
        get() = prefs.getStringSet(KEY_APPLY_ERRORS, emptySet())?.toList() ?: emptyList()
        set(value) = prefs.edit { putStringSet(KEY_APPLY_ERRORS, value.take(20).toSet()) }

    /**
     * Things worth telling the operator about an apply that nonetheless succeeded
     * (W50) — a policy naming an older build than the device already carries, say.
     *
     * Stored apart from [lastApplyErrors] because the server must be able to tell
     * them apart: an error degrades a device, a warning must not. A degraded device
     * is refused agent updates, so filing a benign mismatch as an error would cut
     * that device off from every future agent build.
     */
    var lastApplyWarnings: List<String>
        get() = prefs.getStringSet(KEY_APPLY_WARNINGS, emptySet())?.toList() ?: emptyList()
        set(value) = prefs.edit { putStringSet(KEY_APPLY_WARNINGS, value.take(20).toSet()) }

    /**
     * The `SCREEN_OFF_TIMEOUT` a policy displaced, in milliseconds, or -1 if the
     * agent has never written that setting.
     *
     * `setSystemSetting` latches and Android will not hand the previous value back,
     * so the only way a policy can ever be *un*applied is for the agent to have
     * recorded what it replaced (R19).
     */
    var savedScreenTimeoutMillis: Int
        get() = prefs.getInt(KEY_SAVED_SCREEN_TIMEOUT, -1)
        set(value) = prefs.edit { putInt(KEY_SAVED_SCREEN_TIMEOUT, value) }

    /**
     * sha256 of the wallpaper currently applied, or null.
     *
     * Re-setting a wallpaper flickers visibly, so an idempotent reconcile has to
     * genuinely do nothing — and `WallpaperManager` offers no way to ask what is
     * already set that would survive a crop.
     */
    var appliedWallpaperSha: String?
        get() = prefs.getString(KEY_WALLPAPER_SHA, null)
        set(value) = prefs.edit { putString(KEY_WALLPAPER_SHA, value) }

    var lastSyncAt: Long
        get() = prefs.getLong(KEY_LAST_SYNC, 0L)
        set(value) = prefs.edit { putLong(KEY_LAST_SYNC, value) }

    /**
     * Command outcomes awaiting delivery, each a serialised result object.
     *
     * Persisted rather than held in memory: a command executed just before the
     * process is killed would otherwise be redelivered and run a second time, which
     * for `clear_app_data` means destroying data the user recreated in between.
     * At-least-once delivery (D31) obliges the agent to remember what it has done.
     */
    var pendingCommandResults: List<String>
        get() = prefs.getStringSet(KEY_COMMAND_RESULTS, emptySet())?.toList() ?: emptyList()
        set(value) = prefs.edit { putStringSet(KEY_COMMAND_RESULTS, value.takeLast(50).toSet()) }

    /**
     * Packages this agent hid, so it can unhide them when policy stops asking.
     *
     * Recorded rather than inferred from "everything currently hidden": something
     * else may have hidden a package for its own reasons, and unhiding it because
     * our blocklist no longer mentions it would be us undoing a decision that was
     * never ours.
     */
    var hiddenByPolicy: Set<String>
        get() = prefs.getStringSet(KEY_HIDDEN_BY_POLICY, emptySet()) ?: emptySet()
        set(value) = prefs.edit { putStringSet(KEY_HIDDEN_BY_POLICY, value) }

    /**
     * SSIDs of Wi-Fi networks this agent configured from policy, so it can remove
     * them when the policy stops listing them. Same reasoning as [hiddenByPolicy]:
     * never touch a network the user or another app set up.
     */
    var wifiByPolicy: Set<String>
        get() = prefs.getStringSet(KEY_WIFI_BY_POLICY, emptySet()) ?: emptySet()
        set(value) = prefs.edit { putStringSet(KEY_WIFI_BY_POLICY, value) }

    /**
     * User apps this agent suspended to enforce `allowed_packages`. Recorded, not
     * inferred from "everything currently suspended" — same reasoning as
     * [hiddenByPolicy]: another app may suspend a package for its own reasons.
     */
    var suspendedByPolicy: Set<String>
        get() = prefs.getStringSet(KEY_SUSPENDED_BY_POLICY, emptySet()) ?: emptySet()
        set(value) = prefs.edit { putStringSet(KEY_SUSPENDED_BY_POLICY, value) }

    // The network id WifiManager.addNetwork returned for an SSID. Stored because
    // getConfiguredNetworks() returns nothing for a normally-installed Device
    // Owner on One UI 8 even though addNetwork works — so the id we were handed at
    // add time is the only reliable handle for removeNetwork later.
    fun wifiNetworkId(ssid: String): Int =
        prefs.getInt("$KEY_WIFI_ID_PREFIX$ssid", -1)

    fun recordWifiNetworkId(ssid: String, id: Int) =
        prefs.edit { putInt("$KEY_WIFI_ID_PREFIX$ssid", id) }

    fun forgetWifiNetworkId(ssid: String) =
        prefs.edit { remove("$KEY_WIFI_ID_PREFIX$ssid") }

    /**
     * Packages this agent has pushed a managed configuration to (W49).
     *
     * `setApplicationRestrictions` latches, so an app dropped from the policy would
     * keep its configuration for good unless the agent remembers it set one.
     */
    var appConfigured: Set<String>
        get() = prefs.getStringSet(KEY_APP_CONFIGURED, emptySet()) ?: emptySet()
        set(value) = prefs.edit { putStringSet(KEY_APP_CONFIGURED, value) }

    /** Optional file ids the user chose in the marketplace (F4). */
    var selectedOptionalFiles: Set<String>
        get() = prefs.getStringSet(KEY_SELECTED_FILES, emptySet()) ?: emptySet()
        set(value) = prefs.edit { putStringSet(KEY_SELECTED_FILES, value) }

    /** sha256 of each file already placed, keyed by "fileId|destination". */
    fun appliedFileHash(key: String): String? = prefs.getString("$KEY_FILE_PREFIX$key", null)

    fun recordAppliedFile(key: String, sha256: String) {
        prefs.edit { putString("$KEY_FILE_PREFIX$key", sha256) }
    }

    fun forgetAppliedFile(key: String) {
        prefs.edit { remove("$KEY_FILE_PREFIX$key") }
    }

    /**
     * Data-usage thresholds already warned about (W44).
     *
     * Keyed by rule *and* accounting window (see `DataUsagePlan.notifiedKey`), so a
     * device sitting over its limit warns once rather than at every sync, and warns
     * again when the next period starts. Kept small by [forgetDataUsageWarningsExcept],
     * which drops keys from windows that have rolled over — otherwise this set grows
     * by one entry per threshold per month, forever.
     */
    var dataUsageWarned: Set<String>
        get() = prefs.getStringSet(KEY_DATA_USAGE_WARNED, emptySet()) ?: emptySet()
        set(value) = prefs.edit { putStringSet(KEY_DATA_USAGE_WARNED, value) }

    fun recordDataUsageWarning(key: String) {
        dataUsageWarned = dataUsageWarned + key
    }

    /** Drop remembered warnings that no longer belong to a live window. */
    fun forgetDataUsageWarningsExcept(live: Set<String>) {
        val kept = dataUsageWarned intersect live
        if (kept.size != dataUsageWarned.size) dataUsageWarned = kept
    }

    val isEnrolled: Boolean
        get() = deviceId != null

    fun seedFromProvisioning(extras: android.os.PersistableBundle?) {
        if (extras == null) return
        extras.getString(EXTRA_SERVER_URL)?.let { serverUrl = it }
        extras.getString(EXTRA_ENROLLMENT_TOKEN)?.let { enrollmentToken = it }
        extras.getString(EXTRA_SERVER_CA)?.let { serverCaPem = it }
    }

    companion object {
        private const val PREFS = "takmdm_agent"
        private const val KEY_SERVER_URL = "server_url"
        private const val KEY_ENROLL_TOKEN = "enrollment_token"
        private const val KEY_SERVER_CA = "server_ca_pem"
        private const val KEY_DEVICE_ID = "device_id"
        private const val KEY_DEVICE_NAME = "device_name"
        private const val KEY_POLICY_NAMES = "policy_names"
        private const val KEY_BUNDLE_KEY = "bundle_key"
        private const val KEY_RESET_PW_TOKEN = "reset_password_token"
        private const val KEY_STATE_VERSION = "state_version"
        private const val KEY_APPLIED_VERSION = "applied_state_version"
        private const val KEY_DESIRED_STATE = "desired_state"
        private const val KEY_SELECTED_FILES = "selected_optional_files"
        private const val KEY_FILE_PREFIX = "applied_file:"
        private const val KEY_LAST_ERROR = "last_error"
        private const val KEY_LAST_SYNC = "last_sync_at"
        private const val KEY_WALLPAPER_SHA = "applied_wallpaper_sha"
        private const val KEY_SAVED_SCREEN_TIMEOUT = "saved_screen_timeout_ms"
        private const val KEY_APPLY_ERRORS = "last_apply_errors"
        private const val KEY_APPLY_WARNINGS = "last_apply_warnings"
        private const val KEY_APP_CONFIGURED = "app_configured"
        private const val KEY_COMMAND_RESULTS = "pending_command_results"
        private const val KEY_HIDDEN_BY_POLICY = "hidden_by_policy"
        private const val KEY_SUSPENDED_BY_POLICY = "suspended_by_policy"
        private const val KEY_WIFI_BY_POLICY = "wifi_by_policy"
        private const val KEY_WIFI_ID_PREFIX = "wifi_id:"
        private const val KEY_DATA_USAGE_WARNED = "data_usage_warned"

        // Keys inside PROVISIONING_ADMIN_EXTRAS_BUNDLE, matching the server's
        // provisioning payload generator.
        const val EXTRA_SERVER_URL = "server_url"
        const val EXTRA_ENROLLMENT_TOKEN = "enrollment_token"
        const val EXTRA_SERVER_CA = "server_ca_pem"
    }
}
