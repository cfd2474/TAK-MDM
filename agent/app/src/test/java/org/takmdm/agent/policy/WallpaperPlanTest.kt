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
import org.takmdm.agent.policy.WallpaperPlan.Choice

class WallpaperPlanTest {

    private val phoneWidth = 411   // a typical handset
    private val tabletWidth = 800  // SM-X520 and friends

    @Test
    fun `both uploaded, the screen decides`() {
        assertEquals(Choice.TABLET, WallpaperPlan.choose(true, true, tabletWidth))
        assertEquals(Choice.PHONE, WallpaperPlan.choose(true, true, phoneWidth))
    }

    @Test
    fun `only a tablet image applies to a phone too`() {
        // The operator said what they wanted by uploading exactly one. Refusing to
        // apply it would leave a fleet with no wallpaper and no explanation.
        assertEquals(Choice.TABLET, WallpaperPlan.choose(true, false, phoneWidth))
    }

    @Test
    fun `only a phone image applies to a tablet too`() {
        assertEquals(Choice.PHONE, WallpaperPlan.choose(false, true, tabletWidth))
    }

    @Test
    fun `neither uploaded chooses nothing`() {
        assertEquals(Choice.NONE, WallpaperPlan.choose(false, false, tabletWidth))
    }

    @Test
    fun `the boundary is Android's own sw600dp line`() {
        // Exactly 600 is a tablet, matching the resource qualifier, so the split
        // agrees with the layout the user is already looking at.
        assertEquals(Choice.TABLET, WallpaperPlan.choose(true, true, 600))
        assertEquals(Choice.PHONE, WallpaperPlan.choose(true, true, 599))
    }

    @Test
    fun `removing the policy restores the device default`() {
        assertEquals(true, WallpaperPlan.shouldClear(policyNamesAnyImage = false, previouslyApplied = true))
    }

    @Test
    fun `a wallpaper the agent never set is left alone`() {
        // The same overreach R19 guards against, in the other direction: clearing
        // something we did not put there would replace a user's own choice.
        assertEquals(false, WallpaperPlan.shouldClear(policyNamesAnyImage = false, previouslyApplied = false))
    }

    @Test
    fun `a policy still naming an image never clears`() {
        assertEquals(false, WallpaperPlan.shouldClear(policyNamesAnyImage = true, previouslyApplied = true))
    }

    @Test
    fun `an unreadable width still applies a single uploaded image`() {
        // A width of 0 should not cost the device its wallpaper when there is only
        // one candidate and no decision to make.
        assertEquals(Choice.TABLET, WallpaperPlan.choose(true, false, 0))
        assertEquals(Choice.PHONE, WallpaperPlan.choose(false, true, 0))
    }
}
