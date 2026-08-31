package org.takmdm.agent.policy

import android.content.Context
import android.os.Build
import android.util.Log
import org.json.JSONObject

/**
 * OEM-specific policy application.
 *
 * Everything Samsung sits behind this interface with a working AOSP no-op on the
 * other side. That matters for two reasons: the agent must stay functional on
 * non-Samsung hardware, and the Knox licence is still pending — so Knox has to be
 * additive rather than load-bearing.
 */
interface OemPolicyApplier {

    val name: String

    /** Whether this implementation can actually do anything on this device. */
    fun isAvailable(context: Context): Boolean

    /**
     * Grant an app-op-backed permission a Device Owner cannot grant itself.
     *
     * Returns false when unsupported, which is the honest answer on AOSP: the
     * caller then falls back to asking the user once.
     */
    fun grantAllFilesAccess(context: Context, packageName: String): Boolean

    fun applyRestrictions(context: Context, restrictions: JSONObject): List<String>

    companion object {
        private const val TAG = "OemPolicyApplier"

        fun forDevice(context: Context): OemPolicyApplier {
            val candidates = listOf(KnoxPolicyApplier(), AospPolicyApplier())
            val chosen = candidates.first { it.isAvailable(context) }
            Log.i(TAG, "OEM policy applier: ${chosen.name} (device=${Build.MANUFACTURER})")
            return chosen
        }
    }
}

/** Fallback that does nothing OEM-specific, and says so rather than pretending. */
class AospPolicyApplier : OemPolicyApplier {

    override val name = "aosp"

    override fun isAvailable(context: Context) = true

    override fun grantAllFilesAccess(context: Context, packageName: String): Boolean {
        // MANAGE_EXTERNAL_STORAGE is an app-op, not a runtime permission, so
        // setPermissionGrantState cannot grant it and there is no AOSP path that
        // can. Reporting false sends the caller to the one-time user grant.
        return false
    }

    override fun applyRestrictions(context: Context, restrictions: JSONObject) = emptyList<String>()
}

/**
 * Samsung Knox.
 *
 * Deliberately inert until the Knox partner account and KPE licence land (R3). It
 * reports unavailable rather than half-working, so the agent takes the AOSP path
 * and the fallback is exercised in testing instead of lying dormant until the day
 * Knox fails in the field.
 */
class KnoxPolicyApplier : OemPolicyApplier {

    override val name = "knox"

    override fun isAvailable(context: Context): Boolean {
        if (!Build.MANUFACTURER.equals("samsung", ignoreCase = true)) return false

        // Knox SDK classes are not on the classpath yet. When the licence arrives,
        // the KSP path is preferred over the SDK: managed configuration delivered by
        // setApplicationRestrictions works without managed Google Play (D11).
        return try {
            Class.forName("com.samsung.android.knox.EnterpriseDeviceManager")
            true
        } catch (e: ClassNotFoundException) {
            Log.i("KnoxPolicyApplier", "Knox SDK absent; using AOSP behaviour")
            false
        }
    }

    override fun grantAllFilesAccess(context: Context, packageName: String): Boolean = false

    override fun applyRestrictions(context: Context, restrictions: JSONObject) = emptyList<String>()
}
