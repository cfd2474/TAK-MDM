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

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DeviceIdLabelPlanTest {

    private val launchers = setOf(
        "com.sec.android.app.launcher",       // the stock Samsung home
        "com.taksolutions.atlaslauncher",     // ours
    )

    // ----------------------------------------------------------------------- //
    // Which app is in front

    @Test
    fun `the stock launcher counts as home`() {
        assertTrue(
            DeviceIdLabelPlan.onHome("com.sec.android.app.launcher", launchers, previously = false)
        )
    }

    @Test
    fun `the ATLAS launcher counts as home`() {
        assertTrue(
            DeviceIdLabelPlan.onHome("com.taksolutions.atlaslauncher", launchers, previously = false)
        )
    }

    @Test
    fun `ATAK does not`() {
        assertFalse(DeviceIdLabelPlan.onHome("com.atakmap.app.civ", launchers, previously = true))
    }

    /**
     * The case that decides whether the feature is usable. A tablet nobody is
     * touching produces no usage events, so the query comes back empty — and an
     * empty answer must not be read as "an app is in front".
     */
    @Test
    fun `no answer holds the last verdict rather than hiding`() {
        assertTrue(DeviceIdLabelPlan.onHome(null, launchers, previously = true))
        assertFalse(DeviceIdLabelPlan.onHome(null, launchers, previously = false))
    }

    @Test
    fun `a device with no launcher resolved never reports home`() {
        assertFalse(DeviceIdLabelPlan.onHome("com.sec.android.app.launcher", emptySet(), false))
    }

    // ----------------------------------------------------------------------- //
    // Whether to draw it

    @Test
    fun `shown on the home screen`() {
        assertTrue(DeviceIdLabelPlan.visible("TAB-07", onHome = true, gated = true))
    }

    @Test
    fun `hidden over an app`() {
        assertFalse(DeviceIdLabelPlan.visible("TAB-07", onHome = false, gated = true))
    }

    /**
     * Without usage access there is no way to know what is in front, and the
     * label is worth more in the wrong place than absent. Inverting this is a
     * one-character change, which is why it is pinned.
     */
    @Test
    fun `without usage access it shows everywhere`() {
        assertTrue(DeviceIdLabelPlan.visible("TAB-07", onHome = false, gated = false))
    }

    @Test
    fun `no label means nothing is drawn, gated or not`() {
        assertFalse(DeviceIdLabelPlan.visible(null, onHome = true, gated = true))
        assertFalse(DeviceIdLabelPlan.visible(null, onHome = false, gated = false))
        assertFalse(DeviceIdLabelPlan.visible("  ", onHome = true, gated = false))
    }
}
