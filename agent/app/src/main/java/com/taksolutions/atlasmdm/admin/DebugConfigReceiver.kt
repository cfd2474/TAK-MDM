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

package com.taksolutions.atlasmdm.admin

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.taksolutions.atlasmdm.diag.AgentLog
import com.taksolutions.atlasmdm.BuildConfig
import com.taksolutions.atlasmdm.core.AgentConfig
import com.taksolutions.atlasmdm.diag.Redactor
import com.taksolutions.atlasmdm.sync.SyncScheduler

/**
 * Bench configuration over `adb`, for the `dpm set-device-owner` provisioning path.
 *
 * QR and Knox Mobile Enrollment deliver the server URL and enrollment token in the
 * provisioning extras bundle. Setting Device Owner over ADB has no such bundle, so
 * without this the agent installs and then sits idle with nothing to talk to — and
 * ADB is the only path that yields logs, which is exactly what is needed when
 * provisioning fails on-device with "something went wrong".
 *
 * **Debug builds only**, in two independent ways. A receiver that can repoint an
 * agent at an arbitrary management server is a fleet takeover primitive.
 *
 * 1. `src/release/AndroidManifest.xml` removes the declaration, so a release APK
 *    has no such component for anything to broadcast to (SEC_AUDIT.md M-4).
 * 2. The `BuildConfig.DEBUG` check below, which is the backstop.
 *
 * ⚠️ This comment used to claim the class was "compiled out of release builds".
 * It was not — the class shipped, the receiver was declared `exported="true"` in
 * every build type, and point 2 was the whole defence. The claim is true now
 * because point 1 exists; it was not true when it was written.
 *
 *     adb shell am broadcast -a com.taksolutions.atlasmdm.CONFIGURE \
 *       -n com.taksolutions.atlasmdm/.admin.DebugConfigReceiver \
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
            com.taksolutions.atlasmdm.net.DeviceIdentity.deleteIdentity()
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
            "identity: device key -> " + com.taksolutions.atlasmdm.net.DeviceIdentity.keySecurityLevel()
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
        val dir = java.io.File("/sdcard/Android/obb/com.taksolutions.testapp")
        val probe = java.io.File(dir, "atlas_obb_probe.txt")
        val result = runCatching {
            val made = dir.mkdirs() || dir.isDirectory
            probe.writeText("atlas obb probe")
            val readBack = probe.readText()
            probe.delete()
            "mkdirs=$made write+read=${readBack == "atlas obb probe"}"
        }.getOrElse { "FAILED: ${it.javaClass.simpleName}: ${it.message}" }
        AgentLog.i(TAG, "obb probe /sdcard/Android/obb/com.taksolutions.testapp -> $result")
    }

    companion object {
        private const val TAG = "DebugConfigReceiver"
        const val ACTION = "com.taksolutions.atlasmdm.CONFIGURE"
    }
}
