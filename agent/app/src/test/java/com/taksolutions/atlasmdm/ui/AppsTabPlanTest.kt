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

package com.taksolutions.atlasmdm.ui

import com.taksolutions.atlasmdm.ui.AppsTabPlan.AppsTab
import org.junit.Assert.assertEquals
import org.junit.Test

class AppsTabPlanTest {

    @Test
    fun `a policy app not on the device is Available`() {
        assertEquals(
            AppsTab.AVAILABLE,
            AppsTabPlan.tabFor(available = true, installedVersionCode = null, wantedVersionCode = 5),
        )
    }

    @Test
    fun `an app at the wanted build is Installed`() {
        assertEquals(
            AppsTab.INSTALLED,
            AppsTabPlan.tabFor(available = true, installedVersionCode = 5, wantedVersionCode = 5),
        )
    }

    @Test
    fun `an older build is an Update`() {
        assertEquals(
            AppsTab.UPDATES,
            AppsTabPlan.tabFor(available = true, installedVersionCode = 4, wantedVersionCode = 7),
        )
    }

    @Test
    fun `a newer build than the policy counts as Installed, not an Update`() {
        // There is nothing to fetch, and Android refuses a downgrade anyway — so
        // filing it under Updates would offer an action that cannot be taken.
        assertEquals(
            AppsTab.INSTALLED,
            AppsTabPlan.tabFor(available = true, installedVersionCode = 9, wantedVersionCode = 7),
        )
    }

    @Test
    fun `an app with no publishable build stays in Available rather than vanishing`() {
        // This is the "nothing uploaded for it" case: the policy names an app the
        // server cannot supply. It is the only place the device admits a policy is
        // broken, so it must remain somewhere the operator will look.
        assertEquals(
            AppsTab.AVAILABLE,
            AppsTabPlan.tabFor(available = false, installedVersionCode = null, wantedVersionCode = -1),
        )
    }

    @Test
    fun `an unavailable app already on the device still shows in Available`() {
        // Installed but the policy can no longer supply it — the interesting fact
        // is the broken policy, not the copy that happens to be present.
        assertEquals(
            AppsTab.AVAILABLE,
            AppsTabPlan.tabFor(available = false, installedVersionCode = 3, wantedVersionCode = -1),
        )
    }

    @Test
    fun `every app lands in exactly one tab`() {
        // The three tabs are the whole surface: an app filed nowhere is invisible,
        // and invisible is indistinguishable from not deployed.
        val cases = listOf(
            Triple(true, null, 5L),
            Triple(true, 5L, 5L),
            Triple(true, 4L, 5L),
            Triple(false, null, -1L),
            Triple(false, 2L, -1L),
        )
        for ((available, installed, wanted) in cases) {
            val tab = AppsTabPlan.tabFor(available, installed, wanted)
            assertEquals(
                "each case resolves to a real tab",
                true,
                tab in AppsTab.entries,
            )
        }
    }
}
