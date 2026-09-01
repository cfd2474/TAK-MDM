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

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import org.takmdm.agent.diag.AgentLog
import org.takmdm.agent.BuildConfig
import org.takmdm.agent.core.AgentConfig
import org.takmdm.agent.sync.SyncScheduler

/**
 * Bench configuration over `adb`, for the `dpm set-device-owner` provisioning path.
 *
 * QR and Knox Mobile Enrollment deliver the server URL and enrollment token in the
 * provisioning extras bundle. Setting Device Owner over ADB has no such bundle, so
 * without this the agent installs and then sits idle with nothing to talk to — and
 * ADB is the only path that yields logs, which is exactly what is needed when
 * provisioning fails on-device with "something went wrong".
 *
 * **Debug builds only.** A receiver that can repoint an agent at an arbitrary
 * server is a fleet takeover primitive; it is compiled out of release builds and
 * refuses to act even if one were somehow shipped.
 *
 *     adb shell am broadcast -a org.takmdm.agent.CONFIGURE \
 *       -n org.takmdm.agent/.admin.DebugConfigReceiver \
 *       --es server_url https://192.168.68.89:8443 \
 *       --es enrollment_token <token>
 */
class DebugConfigReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (!BuildConfig.DEBUG) {
            AgentLog.w(TAG, "ignored: configuration over broadcast is debug-only")
            return
        }
        if (intent.action != ACTION) return

        val config = AgentConfig(context)
        intent.getStringExtra("server_url")?.let {
            config.serverUrl = it.trimEnd('/')
            AgentLog.i(TAG, "server_url set to ${config.serverUrl}")
        }
        intent.getStringExtra("enrollment_token")?.let {
            config.enrollmentToken = it
            AgentLog.i(TAG, "enrollment token set (${it.take(8)}…)")
        }
        intent.getStringExtra("server_ca_pem")?.let {
            // Newlines do not survive `am broadcast` cleanly, so accept a
            // single-line PEM with \n written literally.
            config.serverCaPem = it.replace("\\n", "\n")
            AgentLog.i(TAG, "server CA set (${config.serverCaPem?.length} chars)")
        }
        if (intent.getBooleanExtra("reset_identity", false)) {
            // Lets a bench device re-enrol without a factory reset.
            org.takmdm.agent.net.DeviceIdentity.deleteIdentity()
            config.deviceId = null
            AgentLog.i(TAG, "device identity cleared")
        }

        AgentLog.i(
            TAG,
            "configured: server=${config.serverUrl} enrolled=${config.isEnrolled} " +
                "deviceOwner=${MdmDeviceAdminReceiver.isDeviceOwner(context)}"
        )
        SyncScheduler.startAll(context)
    }

    companion object {
        private const val TAG = "DebugConfigReceiver"
        const val ACTION = "org.takmdm.agent.CONFIGURE"
    }
}
