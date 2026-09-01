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

package org.takmdm.agent.admin

import android.app.admin.DeviceAdminReceiver
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.PersistableBundle
import org.takmdm.agent.diag.AgentLog
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
        AgentLog.i(TAG, "provisioning complete; server=${AgentConfig(context).serverUrl}")

        SyncScheduler.startAll(context)
    }

    override fun onEnabled(context: Context, intent: Intent) {
        super.onEnabled(context, intent)
        AgentLog.i(TAG, "device admin enabled; deviceOwner=${isDeviceOwner(context)}")
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
