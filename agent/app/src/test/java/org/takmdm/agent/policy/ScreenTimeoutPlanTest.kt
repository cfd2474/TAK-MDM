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

package org.takmdm.agent.policy

import org.junit.Assert.assertEquals
import org.junit.Test
import org.takmdm.agent.policy.ScreenTimeoutPlan.Action

/**
 * R19: `setSystemSetting(SCREEN_OFF_TIMEOUT)` latches, and unlike the password
 * minimums it has no permissive value to push instead. The agent has to remember
 * what it displaced, so most of what matters here is *when* it remembers and when
 * it must not.
 */
class ScreenTimeoutPlanTest {

    @Test
    fun `no policy and nothing displaced leaves the setting alone`() {
        // Restoring something the agent never overwrote would be the same overreach
        // in the other direction.
        assertEquals(
            Action.Nothing,
            ScreenTimeoutPlan.decide(desiredSeconds = null, currentMillis = 1_800_000, savedOriginalMillis = null)
        )
    }

    @Test
    fun `the first write remembers what it displaced`() {
        assertEquals(
            Action.Apply(millis = 45_000, remember = 1_800_000),
            ScreenTimeoutPlan.decide(desiredSeconds = 45, currentMillis = 1_800_000, savedOriginalMillis = null)
        )
    }

    @Test
    fun `a later write does not overwrite the remembered value`() {
        // The bug this guards: a policy changing 45s to 60s would otherwise record
        // 45s as "the user's setting", and the device could never get back to 30
        // minutes.
        assertEquals(
            Action.Apply(millis = 60_000, remember = null),
            ScreenTimeoutPlan.decide(desiredSeconds = 60, currentMillis = 45_000, savedOriginalMillis = 1_800_000)
        )
    }

    @Test
    fun `re-applying the same value still does not re-remember`() {
        assertEquals(
            Action.Apply(millis = 45_000, remember = null),
            ScreenTimeoutPlan.decide(desiredSeconds = 45, currentMillis = 45_000, savedOriginalMillis = 1_800_000)
        )
    }

    @Test
    fun `removing the policy restores what was displaced`() {
        assertEquals(
            Action.Restore(1_800_000),
            ScreenTimeoutPlan.decide(desiredSeconds = null, currentMillis = 45_000, savedOriginalMillis = 1_800_000)
        )
    }

    @Test
    fun `an unreadable current value is not guessed at`() {
        // Recording a wrong "original" is worse than recording none: the device
        // would later be driven to a value nobody chose.
        assertEquals(
            Action.Apply(millis = 45_000, remember = null),
            ScreenTimeoutPlan.decide(desiredSeconds = 45, currentMillis = null, savedOriginalMillis = null)
        )
    }

    @Test
    fun `a policy matching the value already set still records it`() {
        // Ambiguous on the face of it — the user may simply have had 45s — but it
        // *is* the pre-policy value, and it is the only chance to record one.
        assertEquals(
            Action.Apply(millis = 45_000, remember = 45_000),
            ScreenTimeoutPlan.decide(desiredSeconds = 45, currentMillis = 45_000, savedOriginalMillis = null)
        )
    }

    @Test
    fun `seconds become milliseconds`() {
        val action = ScreenTimeoutPlan.decide(15, 1_800_000, 1_800_000) as Action.Apply
        assertEquals(15_000, action.millis)
    }

    @Test
    fun `the whole lifecycle returns the device to where it started`() {
        var saved: Int? = null
        val start = 1_800_000

        val applied = ScreenTimeoutPlan.decide(45, start, saved) as Action.Apply
        applied.remember?.let { saved = it }

        // A second reconcile while the policy still applies.
        val again = ScreenTimeoutPlan.decide(45, applied.millis, saved) as Action.Apply
        again.remember?.let { saved = it }

        // And the policy goes away.
        val restored = ScreenTimeoutPlan.decide(null, again.millis, saved) as Action.Restore

        assertEquals(start, restored.millis)
    }
}
