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
import android.util.Base64
import androidx.core.content.edit
import org.json.JSONArray

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
     * sha256 of the agent APK a self-update is part-way through installing (W88).
     *
     * ⚠️ **A message to the next process, not state this one uses.** Installing
     * the agent kills the agent, so nothing after `PackageInstaller.install`
     * runs — including any cleanup of the 21 MB APK it was handed. This is written
     * before that call so the build that starts next knows which file to discard.
     * Cleared by `Reconciler.discardFinishedSelfUpdate` once the update has landed.
     */
    val pendingSelfUpdateSha: String?
        get() = prefs.getString(KEY_SELF_UPDATE_SHA, null)

    /**
     * The versionCode [pendingSelfUpdateSha] was fetching, or 0.
     *
     * Recorded alongside the sha so the next process can tell an update that
     * landed from one that failed: below this number, the download is kept for the
     * retry rather than thrown away.
     */
    val pendingSelfUpdateVersionCode: Long
        get() = prefs.getLong(KEY_SELF_UPDATE_VERSION, 0L)

    /** Written together — a sha without its version could not be judged. */
    fun recordPendingSelfUpdate(sha: String, versionCode: Long) = prefs.edit {
        putString(KEY_SELF_UPDATE_SHA, sha)
        putLong(KEY_SELF_UPDATE_VERSION, versionCode)
    }

    /** Forget the pending update, once its APK has been discarded. */
    fun clearPendingSelfUpdate() = prefs.edit {
        remove(KEY_SELF_UPDATE_SHA)
        remove(KEY_SELF_UPDATE_VERSION)
    }

    /**
     * Set when someone left kiosk with the exit passcode (W65).
     *
     * ⚠️ The one place the **device** overrides policy until told otherwise. The
     * server still says "this device is a kiosk", and it is right — but a person
     * standing at it has just said otherwise with a passcode, and re-locking them
     * out at the next check-in two minutes later would make the exit useless.
     *
     * Cleared on reboot, because it is `elapsedRealtime`-based: a restart is the
     * natural end of "I am working on this device", and it is also the recovery
     * path if the exit is ever used to strand one.
     */
    var kioskExitedAtElapsed: Long
        get() = prefs.getLong(KEY_KIOSK_EXITED, 0L)
        set(value) = prefs.edit { putLong(KEY_KIOSK_EXITED, value) }

    /**
     * The kiosk component this agent has already launched into lock task (W67).
     *
     * ⚠️ Exists to stop the applier **cold-starting the kiosk app on every sync**.
     * `launchIntoLockTask` uses `FLAG_ACTIVITY_CLEAR_TASK`, which is right the
     * first time — an app already running when kiosk arrives would otherwise stay
     * up *outside* lock task — and destructive every time after, because it tears
     * the task down and starts the app again. On a two-minute sync that is a heavy
     * app restarting forever, which reads as the app crashing.
     *
     * Stored as "package/activity" so a change of either counts as new.
     */
    var kioskLaunched: String?
        get() = prefs.getString(KEY_KIOSK_LAUNCHED, null)
        set(value) = prefs.edit { putString(KEY_KIOSK_LAUNCHED, value) }

    /**
     * The user's own answer for night mode, or null if they have not given one
     * (W71).
     *
     * ⚠️ Stored, because policy is re-applied every two minutes. Without it the
     * user would turn the tint off and watch it come back — which is worse than
     * never offering the control, because it looks like the device is fighting
     * them. Forgotten when the operator stops offering the control, so an old
     * answer cannot go on overriding policy where nobody can see it.
     */
    var nightModeUserChoice: Boolean?
        get() = if (prefs.contains(KEY_NIGHT_USER)) prefs.getBoolean(KEY_NIGHT_USER, false)
                else null
        set(value) = prefs.edit {
            if (value == null) remove(KEY_NIGHT_USER) else putBoolean(KEY_NIGHT_USER, value)
        }

    /**
     * The user's own screen timeout in milliseconds, or null (W71).
     *
     * ⚠️ Read by `applyScreenTimeout`, which otherwise drives the setting back to
     * the policy value on every reconcile. Its mere presence is what suspends
     * that — so it exists only while the operator offers the control, and the
     * kiosk applier clears it when they stop.
     */
    var screenTimeoutUserChoiceMillis: Int?
        get() = prefs.getInt(KEY_TIMEOUT_USER, -1).takeIf { it > 0 }
        set(value) = prefs.edit {
            if (value == null) remove(KEY_TIMEOUT_USER) else putInt(KEY_TIMEOUT_USER, value)
        }

    /** The user's own night-mode strength, 0-100, or null. */
    var nightLevelUserChoice: Int?
        get() = prefs.getInt(KEY_NIGHT_LEVEL_USER, -1).takeIf { it >= 0 }
        set(value) = prefs.edit {
            if (value == null) remove(KEY_NIGHT_LEVEL_USER) else putInt(KEY_NIGHT_LEVEL_USER, value)
        }

    /**
     * The package HOME was pointed at, so the takeover can actually be undone
     * (W69).
     *
     * ⚠️ Without this the undo was aimed at the wrong package and did nothing.
     * `clearPackagePersistentPreferredActivities(admin, packageName)` matches on
     * the **target component's** package — AOSP compares
     * `pa.mComponent.getPackageName()` — and the agent was passing *its own*
     * package while the preference pointed at the kiosk app. Nothing was ever
     * cleared, so a device kept the kiosk app (or the ATLAS launcher) as its home
     * screen after the policy that set it was removed.
     */
    var kioskHomePackage: String?
        get() = prefs.getString(KEY_KIOSK_HOME, null)
        set(value) = prefs.edit { putString(KEY_KIOSK_HOME, value) }

    /**
     * `elapsedRealtime` when that launch happened, which is how a reboot is seen.
     *
     * A stored value **greater than the current** elapsed time can only mean the
     * clock restarted, so the device has rebooted and nothing is in lock task any
     * more — the next apply must force a real relaunch rather than a re-front.
     */
    var kioskLaunchedAtElapsed: Long
        get() = prefs.getLong(KEY_KIOSK_LAUNCHED_AT, 0L)
        set(value) = prefs.edit { putLong(KEY_KIOSK_LAUNCHED_AT, value) }

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
     * Builds that failed to install for a reason retrying cannot change (W96).
     *
     * ⚠️ Keyed on package **and artifact digest**, so a policy that moves to a
     * different build is tried afresh. Remembering "this package cannot install"
     * would make the operator's fix invisible — they would upload a working APK
     * and the device would go on refusing it.
     *
     * Kept small: this is a cache of a decision, and losing it costs one wasted
     * install attempt, not correctness.
     */
    var unusableBuilds: Set<String>
        get() = prefs.getStringSet(KEY_UNUSABLE_BUILDS, emptySet()) ?: emptySet()
        set(value) = prefs.edit { putStringSet(KEY_UNUSABLE_BUILDS, value.take(50).toSet()) }

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
    /**
     * The radio state a geofence found before it took a radio, or null if no
     * fence has taken it (W106 C4).
     *
     * ⚠️ **Recorded, never inferred.** "Everything currently off" is not the same
     * set as "everything we turned off", and restoring the former would be this
     * agent reversing a decision that was never its own — the rule
     * `hiddenByPolicy` already follows. Without this, leaving a fence would either
     * strand the radio off or switch on one the user had deliberately turned off.
     */
    var geofenceWifiRestore: String?
        get() = prefs.getString(KEY_FENCE_WIFI_RESTORE, null)
        set(value) = prefs.edit { putString(KEY_FENCE_WIFI_RESTORE, value) }

    var geofenceBluetoothRestore: String?
        get() = prefs.getString(KEY_FENCE_BT_RESTORE, null)
        set(value) = prefs.edit { putString(KEY_FENCE_BT_RESTORE, value) }

    /**
     * What the active fences ask of the screen lock: `none`, `off` or `on`.
     *
     * Held so the device is locked on the *transition* into that state rather than
     * on every evaluation — relocking every couple of minutes for as long as a
     * tablet sat inside a fence would not be enforcement, it would be an unusable
     * device.
     */
    var geofenceLock: String
        get() = prefs.getString(KEY_FENCE_PASSWORD, "none") ?: "none"
        set(value) = prefs.edit { putString(KEY_FENCE_PASSWORD, value) }

    /**
     * sha256 of every CA certificate **this agent** installed (W112).
     *
     * ⚠️ Recorded, never inferred. `uninstallAllUserCaCerts` would remove every
     * user-installed anchor including ones a person added themselves, and
     * "everything currently trusted" is not the same set as "everything we
     * trusted" — the rule `hiddenByPolicy` already follows for packages.
     */
    var caCertsInstalled: Set<String>
        get() = prefs.getStringSet(KEY_CA_INSTALLED, emptySet()) ?: emptySet()
        set(value) = prefs.edit { putStringSet(KEY_CA_INSTALLED, value) }

    /**
     * The bytes of an anchor we installed, kept so it can be removed again.
     *
     * ⚠️ `uninstallCaCert` names the certificate **by its content**, so without
     * the original bytes there is no way to remove one specific anchor — only the
     * API that removes everybody's. A few kilobytes per certificate is the price
     * of being able to undo exactly what was done.
     */
    fun rememberCaCert(sha256: String, bytes: ByteArray) = prefs.edit {
        putString(KEY_CA_BYTES_PREFIX + sha256, Base64.encodeToString(bytes, Base64.NO_WRAP))
    }

    fun rememberedCaCert(sha256: String): ByteArray? =
        prefs.getString(KEY_CA_BYTES_PREFIX + sha256, null)
            ?.let { runCatching { Base64.decode(it, Base64.NO_WRAP) }.getOrNull() }

    fun forgetCaCert(sha256: String) = prefs.edit { remove(KEY_CA_BYTES_PREFIX + sha256) }

    /**
     * The geofence list as the policy delivered it, so fences can be evaluated on
     * sync iterations where no bundle was fetched — including every iteration of
     * an outage, which is when a fence most needs to still work.
     */
    var geofencesJson: String?
        get() = prefs.getString(KEY_FENCES, null)
        set(value) = prefs.edit { putString(KEY_FENCES, value) }

    /** Sampling interval a fence override is asking for, or 0. */
    var geofenceIntervalOverride: Int
        get() = prefs.getInt(KEY_FENCE_INTERVAL, 0)
        set(value) = prefs.edit { putInt(KEY_FENCE_INTERVAL, value.coerceAtLeast(0)) }

    /** Names of the fences that applied last time, for the log and for change detection. */
    var activeGeofences: String
        get() = prefs.getString(KEY_FENCE_ACTIVE, "") ?: ""
        set(value) = prefs.edit { putString(KEY_FENCE_ACTIVE, value) }

    /**
     * Minutes between location samples, or 0 for off (W106).
     *
     * Persisted rather than read from the cached bundle each time, because the
     * sampler runs on sync iterations where no bundle was fetched — including
     * every iteration of an outage, which is exactly when the track matters.
     */
    var locationIntervalMinutes: Int
        get() = prefs.getInt(KEY_LOCATION_INTERVAL, 0)
        set(value) = prefs.edit { putInt(KEY_LOCATION_INTERVAL, value.coerceAtLeast(0)) }

    /** Wall-clock time of the last sample attempt. 0 means "never". */
    var lastLocationSampleAt: Long
        get() = prefs.getLong(KEY_LAST_LOCATION_SAMPLE, 0L)
        set(value) = prefs.edit { putLong(KEY_LAST_LOCATION_SAMPLE, value) }

    /**
     * Positions recorded but not yet accepted by the server, oldest first.
     *
     * ⚠️ **A JSON array in one string, not a `StringSet`.** The other buffers here
     * use `putStringSet`, which is fine for them and wrong for this: a set has no
     * order, and a track delivered out of order is not a track. A set would also
     * silently merge two genuinely distinct fixes that happened to serialise
     * identically.
     */
    var pendingLocations: List<String>
        get() = runCatching {
            val raw = prefs.getString(KEY_PENDING_LOCATIONS, null) ?: return emptyList()
            val array = JSONArray(raw)
            (0 until array.length()).map { array.getString(it) }
        }.getOrElse {
            // Unreadable means a partial write or a format change. Losing the
            // buffer is bad; refusing to ever record again because of one bad
            // string is worse, and it would be permanent.
            emptyList()
        }
        set(value) = prefs.edit {
            putString(KEY_PENDING_LOCATIONS, JSONArray(value).toString())
        }

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
        private const val KEY_KIOSK_EXITED = "kiosk_exited_at_elapsed"
        private const val KEY_TIMEOUT_USER = "screen_timeout_user_choice"
        private const val KEY_NIGHT_USER = "night_mode_user_choice"
        private const val KEY_NIGHT_LEVEL_USER = "night_level_user_choice"
        private const val KEY_KIOSK_HOME = "kiosk_home_package"
        private const val KEY_KIOSK_LAUNCHED = "kiosk_launched_component"
        private const val KEY_KIOSK_LAUNCHED_AT = "kiosk_launched_at_elapsed"
        private const val KEY_WALLPAPER_SHA = "applied_wallpaper_sha"
        private const val KEY_SELF_UPDATE_SHA = "pending_self_update_sha"
        private const val KEY_SELF_UPDATE_VERSION = "pending_self_update_version"
        private const val KEY_SAVED_SCREEN_TIMEOUT = "saved_screen_timeout_ms"
        private const val KEY_APPLY_ERRORS = "last_apply_errors"
        private const val KEY_APPLY_WARNINGS = "last_apply_warnings"
        private const val KEY_APP_CONFIGURED = "app_configured"
        private const val KEY_COMMAND_RESULTS = "pending_command_results"
        private const val KEY_HIDDEN_BY_POLICY = "hidden_by_policy"
        private const val KEY_UNUSABLE_BUILDS = "unusable_builds"
        private const val KEY_SUSPENDED_BY_POLICY = "suspended_by_policy"
        private const val KEY_WIFI_BY_POLICY = "wifi_by_policy"
        private const val KEY_WIFI_ID_PREFIX = "wifi_id:"
        private const val KEY_DATA_USAGE_WARNED = "data_usage_warned"
        private const val KEY_LOCATION_INTERVAL = "location_interval_minutes"
        private const val KEY_LAST_LOCATION_SAMPLE = "last_location_sample_at"
        private const val KEY_PENDING_LOCATIONS = "pending_locations"
        private const val KEY_FENCE_WIFI_RESTORE = "geofence_wifi_restore"
        private const val KEY_FENCE_BT_RESTORE = "geofence_bluetooth_restore"
        private const val KEY_FENCE_PASSWORD = "geofence_password_enforced"
        private const val KEY_FENCE_ACTIVE = "geofence_active"
        private const val KEY_CA_INSTALLED = "ca_certs_installed"
        private const val KEY_CA_BYTES_PREFIX = "ca_cert_bytes:"
        private const val KEY_FENCES = "geofences_json"
        private const val KEY_FENCE_INTERVAL = "geofence_interval_override"

        // Keys inside PROVISIONING_ADMIN_EXTRAS_BUNDLE, matching the server's
        // provisioning payload generator.
        const val EXTRA_SERVER_URL = "server_url"
        const val EXTRA_ENROLLMENT_TOKEN = "enrollment_token"
        const val EXTRA_SERVER_CA = "server_ca_pem"
    }
}
