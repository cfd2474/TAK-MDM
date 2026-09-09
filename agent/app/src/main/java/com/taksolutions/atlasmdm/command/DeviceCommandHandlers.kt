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

package com.taksolutions.atlasmdm.command

import android.Manifest
import android.app.admin.DevicePolicyManager
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationManager
import androidx.core.content.ContextCompat
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import org.json.JSONObject
import com.taksolutions.atlasmdm.admin.MdmDeviceAdminReceiver
import com.taksolutions.atlasmdm.diag.AgentLog
import com.taksolutions.atlasmdm.ui.DeviceAnnouncer

/** Shared plumbing for the handlers that drive [DevicePolicyManager]. */
abstract class DeviceOwnerCommandHandler(protected val context: Context) : CommandHandler {

    protected val dpm: DevicePolicyManager =
        context.getSystemService(DevicePolicyManager::class.java)

    protected val admin = MdmDeviceAdminReceiver.componentName(context)

    protected val isDeviceOwner: Boolean
        get() = dpm.isDeviceOwnerApp(context.packageName)

    /**
     * Every one of these needs Device Owner privilege, and the failure without it is
     * a `SecurityException` whose message does not say so. Checked once, here.
     */
    protected fun requireDeviceOwner(): String? =
        if (isDeviceOwner) null else "not device owner; cannot execute"
}

/** `lockNow` — immediate, idempotent, and safe to repeat. */
class LockCommandHandler(context: Context) : DeviceOwnerCommandHandler(context) {
    override val type = "lock"

    override fun execute(command: Command): CommandOutcome {
        requireDeviceOwner()?.let { return CommandOutcome.failed(it) }
        dpm.lockNow()
        return CommandOutcome.ok()
    }
}

/**
 * `ping` — make the device announce itself so a person can find it (W107).
 *
 * ⚠️ **Reports success immediately and keeps sounding.** The noise runs for
 * thirty seconds; holding the sync worker for that long would stall the very
 * check-in that reports this command finished, and an operator watching the
 * console would see nothing happen while the tablet was already ringing.
 *
 * ⚠️ **Not a Device Owner action.** Unlike its neighbours here it needs no
 * privilege at all — which matters, because a device that has somehow lost Device
 * Owner is exactly the one somebody is trying to find.
 */
class PingCommandHandler(private val appContext: Context) : CommandHandler {
    override val type = "ping"

    override fun execute(command: Command): CommandOutcome {
        DeviceAnnouncer.start(appContext)
        return CommandOutcome.ok(
            JSONObject().put("sounding_for_seconds", DeviceAnnouncer.DURATION_MS / 1000)
        )
    }
}

/**
 * `reboot` — deferred, because the reboot kills the process that would report it.
 *
 * Run inline, the result never reaches the server, the command is redelivered on
 * the next check-in, and the device reboots again — a loop that ends only when the
 * queue expires.
 */
class RebootCommandHandler(context: Context) : DeviceOwnerCommandHandler(context) {
    override val type = "reboot"

    override fun execute(command: Command): CommandOutcome {
        requireDeviceOwner()?.let { return CommandOutcome.failed(it) }
        return CommandOutcome.okAfterReporting {
            AgentLog.i(TAG, "rebooting on operator command")
            // Throws if a call is active. Nothing to recover to at that point — the
            // log entry above is the record, and the queue will redeliver.
            dpm.reboot(admin)
        }
    }

    private companion object {
        const val TAG = "RebootCommand"
    }
}

/**
 * `wipe` — deferred for the same reason as reboot, and more sharply: there is no
 * "next check-in" after a factory reset in which to report anything.
 */
class WipeCommandHandler(context: Context) : DeviceOwnerCommandHandler(context) {
    override val type = "wipe"

    override fun execute(command: Command): CommandOutcome {
        requireDeviceOwner()?.let { return CommandOutcome.failed(it) }

        // Samsung devices with an external card treat these as separate acts; a lost
        // device wipe that leaves the card readable is not a wipe.
        val wipeExternal = command.params.optBoolean("wipe_external_storage", false)
        val flags = if (wipeExternal) DevicePolicyManager.WIPE_EXTERNAL_STORAGE else 0

        return CommandOutcome.okAfterReporting {
            AgentLog.i(TAG, "wiping device on operator command (external=$wipeExternal)")
            // `wipeData(int, CharSequence)`, API 26 and current. Not `wipeData(int)`,
            // which is deprecated, and not `wipeDevice(int)` — that is **API 37**,
            // so against `compileSdk 36` it does not exist to call. A version branch
            // on it was written here from recollection and would not have compiled.
            dpm.wipeData(flags, WIPE_REASON)
        }
    }

    private companion object {
        const val TAG = "WipeCommand"

        /** Shown to whoever is holding the device as it resets. */
        const val WIPE_REASON = "Wiped remotely by your organisation's administrator."
    }
}

/**
 * `clear_app_data` — asynchronous, so the result is awaited rather than assumed.
 *
 * Reporting success the moment the call returns would report success for a package
 * that is not installed, which is exactly the case an operator is checking.
 */
class ClearAppDataCommandHandler(context: Context) : DeviceOwnerCommandHandler(context) {
    override val type = "clear_app_data"

    override fun execute(command: Command): CommandOutcome {
        requireDeviceOwner()?.let { return CommandOutcome.failed(it) }

        val packageName = command.params.optString("package_name")
        if (packageName.isBlank()) return CommandOutcome.failed("package_name is required")

        val latch = CountDownLatch(1)
        var succeeded = false

        dpm.clearApplicationUserData(
            admin,
            packageName,
            { runnable -> runnable.run() }
        ) { _, result ->
            succeeded = result
            latch.countDown()
        }

        if (!latch.await(TIMEOUT_SECONDS, TimeUnit.SECONDS)) {
            return CommandOutcome.failed("timed out clearing data for $packageName")
        }
        return if (succeeded) CommandOutcome.ok(JSONObject().put("package_name", packageName))
        else CommandOutcome.failed("system refused to clear data for $packageName")
    }

    private companion object {
        const val TIMEOUT_SECONDS = 60L
    }
}

/**
 * `locate` — last known position from GPS or network.
 *
 * Deliberately does not request a *fresh* fix. A live fix can take minutes indoors
 * and would hold the sync loop open the whole time; the answer to "where is this
 * tablet" is served well enough by the last known position plus its age, which is
 * reported so the operator can judge it rather than trust a stale point.
 */
class LocateCommandHandler(context: Context) : DeviceOwnerCommandHandler(context) {
    override val type = "locate"

    override fun execute(command: Command): CommandOutcome {
        val granted = ContextCompat.checkSelfPermission(
            context, Manifest.permission.ACCESS_FINE_LOCATION
        ) == PackageManager.PERMISSION_GRANTED

        if (!granted) return CommandOutcome.failed("location permission not granted")

        val manager = context.getSystemService(LocationManager::class.java)
            ?: return CommandOutcome.failed("no location service")

        val best = listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER)
            .mapNotNull { provider ->
                runCatching {
                    @Suppress("MissingPermission")
                    manager.getLastKnownLocation(provider)
                }.getOrNull()
            }
            .maxByOrNull { it.time }
            ?: return CommandOutcome.failed("no last known location available")

        return CommandOutcome.ok(best.toJson())
    }

    private fun Location.toJson(): JSONObject = JSONObject()
        .put("latitude", latitude)
        .put("longitude", longitude)
        .put("accuracy_metres", accuracy.toDouble())
        .put("provider", provider)
        .put("fixed_at_millis", time)
        // The operator needs to know they may be looking at a point from yesterday.
        .put("age_seconds", (System.currentTimeMillis() - time) / 1000)
}

/**
 * `screenshot` — **reported as unsupported, deliberately.**
 *
 * There is no `DevicePolicyManager` call that captures the screen. `MediaProjection`
 * is the only route and it requires an interactive user to approve the capture,
 * which defeats the point of a remote command on an unattended device. Registering
 * a handler that says so is better than leaving the type unregistered: the operator
 * gets "this agent cannot do that" on the first attempt instead of watching it
 * retry and expire (D89).
 */
class ScreenshotCommandHandler : CommandHandler {
    override val type = "screenshot"

    override fun execute(command: Command) = CommandOutcome.failed(
        "screenshot is not available to a Device Owner: capture requires " +
            "MediaProjection, which needs interactive user consent"
    )
}
