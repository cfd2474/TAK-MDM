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

package org.takmdm.agent.install

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageInstaller
import android.content.pm.PackageManager
import org.takmdm.agent.diag.AgentLog
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/** Result of an install attempt, carrying the reason when it failed. */
data class InstallResult(val success: Boolean, val message: String)

/**
 * Silent app installation via [PackageInstaller].
 *
 * As Device Owner this needs no user interaction. Split APKs are written into a
 * single session — the server has already separated base and splits into
 * content-addressed parts (D13), so the device writes files whose hashes it has
 * already verified rather than unpacking an archive with a second copy on disk.
 */
class AppInstaller(private val context: Context) {

    /**
     * @param parts base APK first, then splits. All must belong to one package.
     */
    fun install(packageName: String, parts: List<File>): InstallResult {
        if (parts.isEmpty()) return InstallResult(false, "no APK parts supplied")
        val missing = parts.filterNot { it.exists() }
        if (missing.isNotEmpty()) {
            return InstallResult(false, "missing parts: ${missing.joinToString { it.name }}")
        }

        val installer = context.packageManager.packageInstaller
        val params = PackageInstaller.SessionParams(
            PackageInstaller.SessionParams.MODE_FULL_INSTALL
        ).apply {
            setAppPackageName(packageName)
            runCatching { setInstallReason(PackageManager.INSTALL_REASON_POLICY) }
        }

        var sessionId = -1
        return try {
            sessionId = installer.createSession(params)
            installer.openSession(sessionId).use { session ->
                parts.forEachIndexed { index, part ->
                    // Distinct names per part; the base must be written too, not
                    // just the splits.
                    val name = if (index == 0) "base.apk" else "split_$index.apk"
                    session.openWrite(name, 0, part.length()).use { output ->
                        part.inputStream().use { input -> input.copyTo(output) }
                        session.fsync(output)
                    }
                }
                commitAndAwait(session, sessionId)
            }
        } catch (e: Exception) {
            AgentLog.e(TAG, "install of $packageName failed", e)
            if (sessionId >= 0) runCatching { installer.abandonSession(sessionId) }
            InstallResult(false, e.message ?: e.javaClass.simpleName)
        }
    }

    private fun commitAndAwait(
        session: PackageInstaller.Session,
        sessionId: Int
    ): InstallResult {
        val latch = CountDownLatch(1)
        var result = InstallResult(false, "install timed out")

        val receiver = object : BroadcastReceiver() {
            override fun onReceive(context: Context, intent: Intent) {
                if (intent.getIntExtra(PackageInstaller.EXTRA_SESSION_ID, -1) != sessionId) return
                val status = intent.getIntExtra(
                    PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE
                )
                val message = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE).orEmpty()
                result = when (status) {
                    PackageInstaller.STATUS_SUCCESS -> InstallResult(true, "installed")
                    PackageInstaller.STATUS_PENDING_USER_ACTION ->
                        // Should not happen as Device Owner. Reported rather than
                        // silently prompting, because a prompt on an unattended
                        // device would hang forever.
                        InstallResult(false, "install requires user action; not device owner?")
                    else -> InstallResult(false, "status $status: $message")
                }
                latch.countDown()
            }
        }

        context.registerReceiver(receiver, IntentFilter(ACTION_INSTALL_RESULT), Context.RECEIVER_NOT_EXPORTED)
        try {
            val intent = Intent(ACTION_INSTALL_RESULT).setPackage(context.packageName)
            val pending = PendingIntent.getBroadcast(
                context, sessionId, intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE
            )
            session.commit(pending.intentSender)
            latch.await(INSTALL_TIMEOUT_SECONDS, TimeUnit.SECONDS)
        } finally {
            runCatching { context.unregisterReceiver(receiver) }
        }
        return result
    }

    fun installedVersionCode(packageName: String): Long? = runCatching {
        context.packageManager.getPackageInfo(packageName, 0).longVersionCode
    }.getOrNull()

    companion object {
        private const val TAG = "AppInstaller"
        private const val ACTION_INSTALL_RESULT = "org.takmdm.agent.INSTALL_RESULT"
        private const val INSTALL_TIMEOUT_SECONDS = 180L
    }
}

/** Declared in the manifest so the install callback has a resolvable target. */
class InstallResultReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) = Unit
}
