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

import com.taksolutions.atlasmdm.policy.KioskLaunchPlan.Action
import org.junit.Assert.assertEquals
import org.junit.Test

class KioskLaunchPlanTest {

    private val atak = "com.atakmap.app.civ"

    @Test
    fun `the first application of a kiosk starts the app`() {
        assertEquals(
            Action.RELAUNCH,
            KioskLaunchPlan.decide(atak, launched = null, launchedAtElapsed = 0, nowElapsed = 5_000),
        )
    }

    /**
     * The regression this was written for (W67). `applyKiosk` runs on every sync,
     * so before the fix a device sat in a two-minute cold-start loop: ATAK torn
     * down and started again, every relaunch reported as a success, the console
     * green throughout.
     */
    @Test
    fun `a sync two minutes later does not restart the app`() {
        var elapsed = 5_000L
        var launched: String? = null
        var launchedAt = 0L
        val actions = mutableListOf<Action>()

        repeat(10) {
            val action = KioskLaunchPlan.decide(atak, launched, launchedAt, elapsed)
            actions += action
            launched = atak
            launchedAt = elapsed
            elapsed += 120_000  // the sync interval
        }

        assertEquals(Action.RELAUNCH, actions.first())
        assertEquals(
            "every sync after the first must front the app, not restart it",
            List(9) { Action.BRING_TO_FRONT },
            actions.drop(1),
        )
    }

    @Test
    fun `changing which app is the kiosk starts the new one`() {
        assertEquals(
            Action.RELAUNCH,
            KioskLaunchPlan.decide(
                "com.example.other", launched = atak, launchedAtElapsed = 5_000, nowElapsed = 9_000,
            ),
        )
    }

    @Test
    fun `adding an activity to the same package starts it`() {
        assertEquals(
            Action.RELAUNCH,
            KioskLaunchPlan.decide(
                "$atak/.ATAKActivity", launched = atak, launchedAtElapsed = 5_000, nowElapsed = 9_000,
            ),
        )
    }

    /**
     * After a reboot nothing is in lock task, and elapsed time has restarted — so
     * the stored stamp is in the future. Fronting here would leave the device
     * unlocked while the agent believed it was a kiosk.
     */
    @Test
    fun `a reboot forces a real relaunch`() {
        assertEquals(
            Action.RELAUNCH,
            KioskLaunchPlan.decide(atak, launched = atak, launchedAtElapsed = 900_000, nowElapsed = 4_000),
        )
    }

    @Test
    fun `an exact tie is not a reboot`() {
        assertEquals(
            Action.BRING_TO_FRONT,
            KioskLaunchPlan.decide(atak, launched = atak, launchedAtElapsed = 4_000, nowElapsed = 4_000),
        )
    }
}
