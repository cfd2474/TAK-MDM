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
import android.content.pm.ApplicationInfo
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
            AgentLog.d(TAG, "session $sessionId opened for $packageName (${parts.size} part(s))")
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

    /**
     * Remove an installed package.
     *
     * Silent as Device Owner — no confirmation dialog — which is the whole point:
     * an operator reclaiming storage or handing a device on cannot be there to tap.
     *
     * Two things it will not do. Android refuses to remove a package holding an
     * active device admin, so the agent cannot delete itself; and the guard in the
     * reconciler refuses before it ever gets here, so the reason is legible rather
     * than an opaque platform failure.
     */
    fun uninstall(packageName: String): InstallResult {
        if (installedVersionCode(packageName) == null) {
            // Already absent. Reported as success because the desired state is
            // "not installed", and that is satisfied — treating it as a failure
            // would leave a device permanently degraded over an app it never had.
            return InstallResult(true, "not installed")
        }

        val latch = CountDownLatch(1)
        var result = InstallResult(false, "uninstall timed out")

        val receiver = object : BroadcastReceiver() {
            override fun onReceive(context: Context, intent: Intent) {
                val status = intent.getIntExtra(
                    PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE
                )
                val message = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE).orEmpty()
                result = when (status) {
                    PackageInstaller.STATUS_SUCCESS -> InstallResult(true, "uninstalled")
                    PackageInstaller.STATUS_PENDING_USER_ACTION ->
                        InstallResult(false, "uninstall requires user action; not device owner?")
                    else -> InstallResult(false, "status $status: $message")
                }
                latch.countDown()
            }
        }

        context.registerReceiver(
            receiver, IntentFilter(ACTION_UNINSTALL_RESULT), Context.RECEIVER_NOT_EXPORTED
        )
        try {
            val intent = Intent(ACTION_UNINSTALL_RESULT).setPackage(context.packageName)
            val pending = PendingIntent.getBroadcast(
                context, packageName.hashCode(), intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE
            )
            AgentLog.d(TAG, "uninstalling $packageName")
            context.packageManager.packageInstaller.uninstall(packageName, pending.intentSender)
            latch.await(UNINSTALL_TIMEOUT_SECONDS, TimeUnit.SECONDS)

            // Trust the outcome, not the status code. PackageInstaller reports
            // success for a system-app "uninstall" that only removed the update, so
            // a caller acting on the status alone believes an app is gone while it
            // is still installed and usable.
            if (result.success && installedVersionCode(packageName) != null) {
                result = InstallResult(
                    false,
                    "still installed after uninstall reported success; " +
                        "system apps can only be hidden"
                )
            }
        } catch (e: Exception) {
            AgentLog.e(TAG, "uninstall of $packageName failed", e)
            result = InstallResult(false, e.message ?: e.javaClass.simpleName)
        } finally {
            runCatching { context.unregisterReceiver(receiver) }
        }
        return result
    }

    /**
     * True when the package ships with the device.
     *
     * Load-bearing, because uninstalling a system app **does not remove it**. It
     * strips the update and reverts to the factory build — and `PackageInstaller`
     * reports `STATUS_SUCCESS` for that. Observed on `SM-X520` with Gmail:
     * `codePath` moved from `/data/app/...` to `/product/app/Gmail2`, the version
     * went backwards, and the agent cheerfully logged "removed" for an app that was
     * still installed and still working.
     *
     * So a system app is hidden rather than uninstalled, and the pointless
     * downgrade is skipped along with the misleading success.
     */
    fun isSystemApp(packageName: String): Boolean = runCatching {
        // MATCH_UNINSTALLED_PACKAGES for the same reason as isPresent: a hidden app
        // is invisible to a plain lookup, and this is asked about hidden apps.
        val flags = context.packageManager.getApplicationInfo(
            packageName, PackageManager.MATCH_UNINSTALLED_PACKAGES
        ).flags
        (flags and ApplicationInfo.FLAG_SYSTEM) != 0 ||
            (flags and ApplicationInfo.FLAG_UPDATED_SYSTEM_APP) != 0
    }.getOrDefault(false)

    /**
     * True when the package is on the device at all, **including while hidden**.
     *
     * A hidden package answers a normal `getPackageInfo` with
     * `NameNotFoundException` — it is deliberately made to look uninstalled. That is
     * fine for deciding whether to install something and wrong for deciding whether
     * to suppress it: without `MATCH_UNINSTALLED_PACKAGES` the agent cannot see the
     * app it hid, so it could never record it and could never unhide it again.
     * Observed exactly that: Gmail stayed hidden after being taken off the
     * blocklist, with nothing logged, because the loop could not find it.
     */
    fun isPresent(packageName: String): Boolean = runCatching {
        context.packageManager.getPackageInfo(
            packageName, PackageManager.MATCH_UNINSTALLED_PACKAGES
        )
        true
    }.getOrDefault(false)

    fun installedVersionCode(packageName: String): Long? = runCatching {
        context.packageManager.getPackageInfo(packageName, 0).longVersionCode
    }.getOrNull()

    /**
     * The installed ATAK, as (packageName, versionName), or null if none is.
     *
     * Reported at check-in so the console can tell an operator that a plugin they
     * assigned was built for a different ATAK. That mismatch is silent on the
     * device — the plugin installs and simply never appears in ATAK — so the
     * server is the only place it can surface.
     *
     * Matched by prefix because the flavour is part of the package name
     * (`com.atakmap.app.civ`, `.mil`), and the *first* match is taken: two ATAK
     * flavours side by side is not a supported arrangement, and picking one
     * arbitrarily is better than reporting nothing.
     */
    fun installedAtak(): Pair<String, String>? = runCatching {
        context.packageManager.getInstalledPackages(0)
            .asSequence()
            .filter { it.packageName.startsWith(ATAK_PACKAGE_PREFIX) }
            .mapNotNull { info -> info.versionName?.let { info.packageName to it } }
            .firstOrNull()
    }.getOrNull()

    /**
     * Package names of non-system, currently-enabled user apps, excluding the
     * agent. This is the universe the `allowed_packages` allowlist acts on —
     * system apps (launcher, dialer, settings) are deliberately out of scope.
     */
    fun userInstalledPackages(): Set<String> = runCatching {
        context.packageManager.getInstalledApplications(0)
            .asSequence()
            .filter {
                it.flags and ApplicationInfo.FLAG_SYSTEM == 0 &&
                    it.flags and ApplicationInfo.FLAG_UPDATED_SYSTEM_APP == 0
            }
            .map { it.packageName }
            .filter { it != context.packageName }
            .toHashSet()
    }.getOrDefault(emptySet())

    companion object {
        private const val TAG = "AppInstaller"
        private const val ACTION_INSTALL_RESULT = "org.takmdm.agent.INSTALL_RESULT"
        private const val ACTION_UNINSTALL_RESULT = "org.takmdm.agent.UNINSTALL_RESULT"
        private const val INSTALL_TIMEOUT_SECONDS = 180L
        // Removal is far quicker than an install: no download, no session.
        private const val UNINSTALL_TIMEOUT_SECONDS = 60L
        // ATAK ships under a flavour-suffixed package: com.atakmap.app.civ, .mil.
        private const val ATAK_PACKAGE_PREFIX = "com.atakmap.app"
    }
}

/** Declared in the manifest so the install callback has a resolvable target. */
class InstallResultReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) = Unit
}
