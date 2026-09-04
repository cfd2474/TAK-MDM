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
 * What to do with `SCREEN_OFF_TIMEOUT` for a given policy state.
 *
 * `setSystemSetting` **latches**: writing it changes the setting permanently, and
 * a policy going away writes nothing, so the value stays. Verified on `SM-X520`
 * (R19) — a policy drove the device from its default 30 minutes to 45 seconds, and
 * removing that policy left it at 45 seconds with the device compliant. Nothing in
 * the console could undo it.
 *
 * The password minimums latch the same way, and there the fix was to write a
 * permissive value (`0`) every reconcile. **That does not work here.** A screen
 * timeout has no permissive value: what "no policy" should mean is *the user's own
 * setting*, and Android will not hand it back once overwritten. Driving it to some
 * fixed default instead would silently replace a preference the operator never
 * asked to change — a quieter bug than the one being fixed.
 *
 * So the agent remembers the value it displaced, on the first write only, and puts
 * it back when the field disappears.
 */
object ScreenTimeoutPlan {

    sealed interface Action {
        /**
         * Write [millis]. [remember] carries the value to store as the original —
         * non-null only on the first write, so a policy changing 45s to 60s does
         * not overwrite the user's setting with 45s.
         */
        data class Apply(val millis: Int, val remember: Int?) : Action

        /** Put [millis] back and forget it: the policy no longer asks for one. */
        data class Restore(val millis: Int) : Action

        data object Nothing : Action
    }

    /**
     * @param desiredSeconds the policy's `screen_timeout_seconds`, or null if no
     *   policy sets one.
     * @param currentMillis what the device is on now, or null if it could not be
     *   read.
     * @param savedOriginalMillis what was displaced by an earlier write, or null if
     *   the agent has never written this setting.
     */
    fun decide(
        desiredSeconds: Int?,
        currentMillis: Int?,
        savedOriginalMillis: Int?
    ): Action {
        if (desiredSeconds == null) {
            // Never written by us: leave it alone. Restoring something we did not
            // displace would be the same overreach in the other direction.
            val original = savedOriginalMillis ?: return Action.Nothing
            return Action.Restore(original)
        }

        val target = desiredSeconds * 1000
        // Remember only on the first write, and only if the current value is
        // readable — an unreadable one is not worth guessing at, and recording a
        // wrong "original" is worse than recording none.
        val remember = if (savedOriginalMillis == null) currentMillis else null
        return Action.Apply(target, remember)
    }
}
