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
import org.takmdm.agent.diag.Redactor
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
            Redactor.protect(it)
            // Length, not a prefix. The old form logged the first eight characters,
            // which was harmless while logs stayed on the device and is not now that
            // an operator can collect them off it.
            AgentLog.i(TAG, "enrollment token set (${it.length} chars)")
        }
        intent.getStringExtra("server_ca_pem")?.let {
            // Newlines do not survive `am broadcast` cleanly, so accept a
            // single-line PEM with \n written literally.
            config.serverCaPem = it.replace("\\n", "\n")
            AgentLog.i(TAG, "server CA set (${config.serverCaPem?.length} chars)")
        }
        if (intent.getBooleanExtra("diagnose_identity", false)) {
            reportIdentitySources(context)
        }
        if (intent.getBooleanExtra("probe_obb", false)) {
            probeObbWrite()
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

    /**
     * Report what each candidate device identity actually yields, on this hardware.
     *
     * `Reconciler.serialNumber()` prefers `Build.getSerial()` and silently falls back
     * to `ANDROID_ID` — and the fallback is what this fleet's one enrolled tablet is
     * living on, which breaks D24's re-enrolment matching. Whether that is a missing
     * permission or a platform refusal cannot be told apart from the outside: both
     * end at the same fallback. This says which.
     */
    private fun reportIdentitySources(context: Context) {
        val serial = runCatching { android.os.Build.getSerial() }
        AgentLog.i(
            TAG,
            "identity: Build.getSerial() -> " + when {
                serial.isFailure ->
                    "threw ${serial.exceptionOrNull()?.javaClass?.simpleName}: " +
                        "${serial.exceptionOrNull()?.message}"
                serial.getOrNull() == android.os.Build.UNKNOWN -> "UNKNOWN (refused, no throw)"
                else -> "'${serial.getOrNull()}'"
            }
        )
        AgentLog.i(
            TAG,
            "identity: READ_PHONE_STATE granted=" +
                (androidx.core.content.ContextCompat.checkSelfPermission(
                    context, android.Manifest.permission.READ_PHONE_STATE
                ) == android.content.pm.PackageManager.PERMISSION_GRANTED)
        )
        AgentLog.i(
            TAG,
            "identity: device key -> " + org.takmdm.agent.net.DeviceIdentity.keySecurityLevel()
        )
        AgentLog.i(
            TAG,
            "identity: StrongBox present on this device = " + context.packageManager
                .hasSystemFeature("android.hardware.strongbox_keystore")
        )
        @Suppress("HardwareIds")
        val androidId = android.provider.Settings.Secure.getString(
            context.contentResolver, android.provider.Settings.Secure.ANDROID_ID
        )
        AgentLog.i(TAG, "identity: ANDROID_ID fallback -> '${android.os.Build.MODEL}-$androidId'")
    }

    /**
     * Can this agent — a normally-installed Device Owner with all-files access —
     * write into another app's `Android/obb/<pkg>/` directory? The official docs
     * exclude "most subdirectories of /sdcard/Android" from MANAGE_EXTERNAL_STORAGE
     * but do not name `Android/obb` explicitly, and it has flip-flopped across
     * releases. This settles it for this OEM (R2).
     */
    private fun probeObbWrite() {
        val dir = java.io.File("/sdcard/Android/obb/org.takmdm.testapp")
        val probe = java.io.File(dir, "atlas_obb_probe.txt")
        val result = runCatching {
            val made = dir.mkdirs() || dir.isDirectory
            probe.writeText("atlas obb probe")
            val readBack = probe.readText()
            probe.delete()
            "mkdirs=$made write+read=${readBack == "atlas obb probe"}"
        }.getOrElse { "FAILED: ${it.javaClass.simpleName}: ${it.message}" }
        AgentLog.i(TAG, "obb probe /sdcard/Android/obb/org.takmdm.testapp -> $result")
    }

    companion object {
        private const val TAG = "DebugConfigReceiver"
        const val ACTION = "org.takmdm.agent.CONFIGURE"
    }
}
