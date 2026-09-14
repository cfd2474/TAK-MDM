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

import android.app.admin.DevicePolicyManager
import android.content.Context
import android.os.Build
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import org.json.JSONObject
import com.taksolutions.atlasmdm.admin.MdmDeviceAdminReceiver
import com.taksolutions.atlasmdm.diag.AgentLog
import com.taksolutions.atlasmdm.policy.CurrentFix
import com.taksolutions.atlasmdm.policy.LocationFixPlan
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
 *
 * ⚠️ **`wipeData` cannot do this job and never could.** Its javadoc:
 *
 * > Calling this method from the primary user will only work if the calling app is
 * > targeting SDK level `TIRAMISU` or below … If an app targeting SDK level
 * > `UPSIDE_DOWN_CAKE` and above is calling this method from the primary user or
 * > last full user, `IllegalStateException` will be thrown.
 * >
 * > If an app wants to wipe the entire device irrespective of which user they are
 * > from, they should use `wipeDevice` instead.
 *
 * We are a Device Owner on the primary user at `targetSdk 36`, so that is
 * *every* wipe on *every* device. W104 disenroll had never once worked, and it
 * failed in the least visible way available: the throw landed in `runCatching`
 * inside a deferred effect, on a device whose certificate the server had already
 * revoked on receipt of the acknowledgement — so nothing could report it. The
 * console said "disenrolled"; the tablet sat there owned, unmanaged, and
 * showing *"sync failed, certificate is not known"* (2026-09-09, `SM-X828U`).
 *
 * ⚠️ **`wipeDevice` is API 34, not API 37.** The comment this replaces asserted
 * the latter from recollection and settled on the call that throws. Verified by
 * `javap` against the real stubs: absent in android-33, present in android-34,
 * -35 and -36. That is why `minSdk 33` still needs the branch below — the
 * platform rule keys off *this app's* `targetSdk`, but the replacement API keys
 * off the *device's* level.
 */
class WipeCommandHandler(context: Context) : DeviceOwnerCommandHandler(context) {
    override val type = "wipe"

    override fun execute(command: Command): CommandOutcome {
        requireDeviceOwner()?.let { return CommandOutcome.failed(it) }

        // Samsung devices with an external card treat these as separate acts; a lost
        // device wipe that leaves the card readable is not a wipe.
        val wipeExternal = command.params.optBoolean("wipe_external_storage", false)
        // ⚠️ **Read from params, not inferred from the disenroll marker.** The
        // agent has no business knowing what "disenroll" means; the server decides
        // whether Factory Reset Protection should survive and says so in a flag,
        // exactly as it already does for external storage. An older agent that
        // does not know this key simply leaves FRP armed, which is the safe
        // direction to fail.
        val clearFrp = command.params.optBoolean("wipe_reset_protection", false)
        var flags = 0
        if (wipeExternal) flags = flags or DevicePolicyManager.WIPE_EXTERNAL_STORAGE
        // Device-owner only: "if it is set by other admins a SecurityException
        // will be thrown". We are one, and requireDeviceOwner() above proved it.
        if (clearFrp) flags = flags or DevicePolicyManager.WIPE_RESET_PROTECTION_DATA

        return CommandOutcome.okAfterReporting {
            AgentLog.i(
                TAG,
                "wiping device on operator command " +
                    "(external=$wipeExternal, clearFrp=$clearFrp)"
            )
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                // The only call that works for a Device Owner on the primary user
                // at targetSdk >= 34. Takes no reason string — the platform stopped
                // offering one on this path, so WIPE_REASON is unused here.
                dpm.wipeDevice(flags)
            } else {
                // API 33: wipeDevice does not exist yet, and the targetSdk rule that
                // makes wipeData throw is not enforced by this platform version.
                dpm.wipeData(flags, WIPE_REASON)
            }
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
 * `locate` — **a live fix**, falling back to the cache only when one cannot be had.
 *
 * ⚠️ **This used to read `getLastKnownLocation` and nothing else** (W162), which
 * starts no GPS session and returns whatever fix some other app happened to leave
 * behind. Pressing Locate on a tablet that had not run a mapping app all day
 * answered with where it was that morning, presented as its position. The age was
 * reported honestly, but an operator asking "where is this device" is not helped by
 * a correct answer to a different question.
 *
 * The old comment defended this as a battery decision, and the cost it names is
 * real — so the request is bounded rather than abandoned: one single-shot fix,
 * capped at [CurrentFix.LOCATE_TIMEOUT_MS], cancelled on the way out. That is a
 * burst, not a session.
 */
class LocateCommandHandler(context: Context) : DeviceOwnerCommandHandler(context) {
    override val type = "locate"

    override fun execute(command: Command): CommandOutcome {
        val outcome = CurrentFix(context).request(CurrentFix.LOCATE_TIMEOUT_MS)
        val fix = outcome.candidate
            ?: return CommandOutcome.failed(outcome.failure ?: "no position available")

        val age = LocationFixPlan.ageSeconds(fix, System.currentTimeMillis())
        AgentLog.i(
            TAG,
            "locate answered with a ${if (outcome.live) "live" else "cached"} " +
                "fix from ${fix.provider}, ${age}s old",
        )
        return CommandOutcome.ok(fix.toJson(age, outcome.live))
    }

    /**
     * ⚠️ The field names are the *server's*, and it is the server that translates
     * them (`from_locate_result`). `accuracy_metres` and `fixed_at_millis` are not
     * what a check-in calls the same two things; renaming either would break a
     * released agent or a stored command result.
     */
    private fun LocationFixPlan.Candidate.toJson(age: Long, live: Boolean): JSONObject =
        JSONObject()
            .put("latitude", latitude)
            .put("longitude", longitude)
            // ⚠️ Omitted when the fix does not carry one. It used to send
            // `accuracy.toDouble()` unconditionally, so a fix with no accuracy was
            // reported as accurate to zero metres — the device not saying is not
            // the device claiming perfection.
            .apply { accuracyMetres?.let { put("accuracy_metres", it.toDouble()) } }
            .put("provider", provider)
            .put("fixed_at_millis", timeMillis)
            // The operator needs to know they may be looking at a point from
            // yesterday, and whether the GPS was actually consulted this time.
            .put("age_seconds", age)
            .put("live", live)

    private companion object {
        const val TAG = "LocateCommandHandler"
    }
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
