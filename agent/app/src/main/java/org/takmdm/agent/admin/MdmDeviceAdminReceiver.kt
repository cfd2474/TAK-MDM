package org.takmdm.agent.admin

import android.app.admin.DeviceAdminReceiver
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.PersistableBundle
import android.util.Log
import org.takmdm.agent.core.AgentConfig
import org.takmdm.agent.sync.SyncScheduler

/**
 * Device Owner admin component.
 *
 * `PROFILE_PROVISIONING_COMPLETE` is where a QR or Knox Mobile Enrollment
 * provisioning run hands over the admin extras bundle carrying the server URL and
 * enrollment token — the only moment those values arrive, so they are persisted
 * immediately.
 */
class MdmDeviceAdminReceiver : DeviceAdminReceiver() {

    override fun onProfileProvisioningComplete(context: Context, intent: Intent) {
        super.onProfileProvisioningComplete(context, intent)

        val extras = intent.getParcelableExtra(
            DevicePolicyManager.EXTRA_PROVISIONING_ADMIN_EXTRAS_BUNDLE,
            PersistableBundle::class.java
        )
        AgentConfig(context).seedFromProvisioning(extras)
        Log.i(TAG, "provisioning complete; server=${AgentConfig(context).serverUrl}")

        SyncScheduler.startAll(context)
    }

    override fun onEnabled(context: Context, intent: Intent) {
        super.onEnabled(context, intent)
        Log.i(TAG, "device admin enabled; deviceOwner=${isDeviceOwner(context)}")
        SyncScheduler.startAll(context)
    }

    companion object {
        private const val TAG = "MdmAdminReceiver"

        fun componentName(context: Context): ComponentName =
            ComponentName(context.applicationContext, MdmDeviceAdminReceiver::class.java)

        fun isDeviceOwner(context: Context): Boolean {
            val dpm = context.getSystemService(DevicePolicyManager::class.java)
            return dpm?.isDeviceOwnerApp(context.packageName) == true
        }
    }
}
