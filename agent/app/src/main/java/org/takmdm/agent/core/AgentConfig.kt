package org.takmdm.agent.core

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

    /** Ed25519 public key, base64, pinned at enrollment to verify policy bundles. */
    var bundleKeyBase64: String?
        get() = prefs.getString(KEY_BUNDLE_KEY, null)
        set(value) = prefs.edit { putString(KEY_BUNDLE_KEY, value) }

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
        private const val KEY_BUNDLE_KEY = "bundle_key"
        private const val KEY_STATE_VERSION = "state_version"
        private const val KEY_APPLIED_VERSION = "applied_state_version"
        private const val KEY_DESIRED_STATE = "desired_state"
        private const val KEY_SELECTED_FILES = "selected_optional_files"
        private const val KEY_FILE_PREFIX = "applied_file:"

        // Keys inside PROVISIONING_ADMIN_EXTRAS_BUNDLE, matching the server's
        // provisioning payload generator.
        const val EXTRA_SERVER_URL = "server_url"
        const val EXTRA_ENROLLMENT_TOKEN = "enrollment_token"
        const val EXTRA_SERVER_CA = "server_ca_pem"
    }
}
