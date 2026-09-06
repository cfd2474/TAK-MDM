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

package com.taksolutions.atlasmdm.policy

/**
 * Whether entering lock task means *starting* the kiosk app or merely fronting it.
 *
 * ⚠️ This exists because getting it wrong is silent (W67). `applyKiosk` runs on
 * every sync, and it launched the kiosk app with `FLAG_ACTIVITY_CLEAR_TASK` every
 * time. That flag is exactly right once — it forces an app that was already
 * running when kiosk arrived *into* lock task, instead of leaving it up beside
 * one — and destructive on every sync after, because it tears the task down and
 * cold-starts the app.
 *
 * On a two-minute sync interval that is a heavy app (ATAK: maps, plugins, a long
 * startup) being killed and restarted forever. Each relaunch **succeeded**, so the
 * agent reported no failure and the console showed the device compliant while the
 * app was unusable. The only trace was `kiosk: launched … into lock task` repeating
 * in the agent's own log, which read as normal operation.
 *
 * Pure and separated from the applier so the decision can be tested without a
 * device: the bug was in *when* the launch happened, not in how it was performed.
 */
object KioskLaunchPlan {

    enum class Action {
        /**
         * Start it: `NEW_TASK or CLEAR_TASK`. Nothing is in lock task, or what is
         * there is not what policy now asks for.
         */
        RELAUNCH,

        /**
         * Bring it forward: `NEW_TASK or SINGLE_TOP`. A no-op when the app is
         * already in front, and it recovers the kiosk if something got on top of
         * it — the self-healing the unconditional relaunch provided by accident,
         * kept without the cost.
         */
        BRING_TO_FRONT,
    }

    /**
     * @param wanted the component policy asks for, as `package` or
     *   `package/activity`.
     * @param launched what this agent last launched, or null if it never has.
     * @param launchedAtElapsed [android.os.SystemClock.elapsedRealtime] at that
     *   launch.
     * @param nowElapsed elapsed time now.
     *
     * ⚠️ `launchedAtElapsed > nowElapsed` is the reboot test, and it has to be
     * elapsed time rather than the wall clock. Elapsed time restarts at zero when
     * the device does, so a stored value in the future can only mean a restart —
     * and after a restart nothing is in lock task, so fronting would leave the
     * device unlocked. The wall clock cannot see a reboot at all, and a user who
     * changes the date could fake one.
     */
    fun decide(
        wanted: String,
        launched: String?,
        launchedAtElapsed: Long,
        nowElapsed: Long,
    ): Action = when {
        launched != wanted -> Action.RELAUNCH
        launchedAtElapsed > nowElapsed -> Action.RELAUNCH
        else -> Action.BRING_TO_FRONT
    }
}
