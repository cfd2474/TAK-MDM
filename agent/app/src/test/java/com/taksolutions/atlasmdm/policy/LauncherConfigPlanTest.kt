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

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Half a wire format, whose other half ships in a different APK on a different
 * update schedule — so the tests are mostly about tolerating the other side
 * being a different version than this one.
 */
class LauncherConfigPlanTest {

    private fun plan(json: String) = LauncherConfigPlan.from(JSONObject(json))

    @Test
    fun `a kiosk with no app list is not a multi-app kiosk`() {
        assertTrue(plan("""{"kiosk_package": "com.atakmap.app.civ"}""").apps.isEmpty())
        assertTrue(plan("{}").apps.isEmpty())
    }

    @Test
    fun `defaults are usable when the policy says nothing`() {
        val p = plan("{}")
        assertEquals(LauncherConfigPlan.DEFAULT_COLUMNS, p.columns)
        assertTrue(p.showClock)
        assertTrue(p.clockZulu)
        assertEquals("auto", p.orientation)
    }

    @Test
    fun `objects carry the activity and the favourite flag`() {
        val p = plan(
            """{"multi_app_packages": [
                 {"package_name": "com.atakmap.app.civ", "activity": ".ATAKActivity",
                  "favorite": true},
                 {"package_name": "com.android.chrome"}
               ]}"""
        )
        assertEquals(listOf("com.atakmap.app.civ", "com.android.chrome"), p.packages)
        assertEquals("com.atakmap.app.civ.ATAKActivity", p.apps[0].activity)
        assertTrue(p.apps[0].favorite)
        assertFalse(p.apps[1].favorite)
    }

    /**
     * ⚠️ The compatibility case. A policy written before the console sent objects
     * sends plain strings; refusing those would turn a working kiosk into one
     * with no apps, which looks like the launcher is broken rather than like the
     * policy is old.
     */
    @Test
    fun `plain package names still work`() {
        val p = plan("""{"multi_app_packages": ["com.a", "com.b/.Main"]}""")
        assertEquals(listOf("com.a", "com.b"), p.packages)
        assertEquals("com.b.Main", p.apps[1].activity)
    }

    @Test
    fun `the two forms can be mixed`() {
        val p = plan(
            """{"multi_app_packages": ["com.a", {"package_name": "com.b", "favorite": true}]}"""
        )
        assertEquals(listOf("com.a", "com.b"), p.packages)
        assertTrue(p.apps[1].favorite)
    }

    @Test
    fun `the operator's order is preserved`() {
        val p = plan("""{"multi_app_packages": ["com.c", "com.a", "com.b"]}""")
        assertEquals(listOf("com.c", "com.a", "com.b"), p.packages)
    }

    @Test
    fun `entries that could never open anything are dropped`() {
        val p = plan(
            """{"multi_app_packages": ["", "  ", "/no.package", "has space", 42, null,
                                       {"activity": ".NoPackage"}, "good.pkg"]}"""
        )
        assertEquals(listOf("good.pkg"), p.packages)
    }

    @Test
    fun `the same app twice is one tile and the first wins`() {
        val p = plan(
            """{"multi_app_packages": [
                 {"package_name": "com.a", "favorite": true},
                 {"package_name": "com.a", "favorite": false}
               ]}"""
        )
        assertEquals(1, p.apps.size)
        assertTrue(p.apps.single().favorite)
    }

    @Test
    fun `a silly column count is clamped, not obeyed`() {
        assertEquals(LauncherConfigPlan.MIN_COLUMNS, plan("""{"launcher_columns": 0}""").columns)
        assertEquals(LauncherConfigPlan.MAX_COLUMNS, plan("""{"launcher_columns": 99}""").columns)
        assertEquals(6, plan("""{"launcher_columns": 6}""").columns)
    }

    @Test
    fun `an unknown orientation falls back rather than reaching the device`() {
        assertEquals("auto", plan("""{"launcher_orientation": "sideways"}""").orientation)
        assertEquals("portrait", plan("""{"launcher_orientation": " Portrait "}""").orientation)
    }

    @Test
    fun `switches are read as sent`() {
        val p = plan(
            """{"launcher_show_search": false, "launcher_show_clock": false,
                "launcher_clock_zulu": false}"""
        )
        assertFalse(p.showSearch)
        assertFalse(p.showClock)
        assertFalse(p.clockZulu)
    }

    /**
     * The list lock task has to permit. Getting this wrong means every tile opens
     * onto a refusal, which reads as a broken launcher rather than a broken
     * allowlist.
     */
    @Test
    fun `packages is exactly what lock task must permit`() {
        val p = plan(
            """{"multi_app_packages": [
                 {"package_name": "com.a", "activity": ".Main"}, "com.b"]}"""
        )
        assertEquals(listOf("com.a", "com.b"), p.packages)
    }

    // ----------------------------------------------------------------------- #
    // Taking the launcher off again (W69)
    // ----------------------------------------------------------------------- #

    private val LAUNCHER = LauncherConfigPlan.ATLAS_LAUNCHER

    @Test
    fun `a device with no multi-app kiosk gives the launcher up`() {
        assertTrue(
            LauncherConfigPlan.shouldRemoveLauncher(JSONObject("{}"), emptyList())
        )
    }

    @Test
    fun `a single-app kiosk is not a reason to keep the launcher`() {
        assertTrue(
            LauncherConfigPlan.shouldRemoveLauncher(
                JSONObject("""{"kiosk_package": "com.atakmap.app.civ"}"""), emptyList()
            )
        )
    }

    @Test
    fun `a live multi-app kiosk keeps it`() {
        assertFalse(
            LauncherConfigPlan.shouldRemoveLauncher(
                JSONObject("""{"multi_app_packages": ["com.a"]}"""), listOf(LAUNCHER)
            )
        )
    }

    /**
     * ⚠️ An operator who puts the launcher in required apps by hand means it, and
     * an agent that removed it every two minutes while the policy reinstalled it
     * would be a loop neither side could see the far end of.
     */
    @Test
    fun `a policy that asks for the launcher outright keeps it`() {
        assertFalse(
            LauncherConfigPlan.shouldRemoveLauncher(JSONObject("{}"), listOf(LAUNCHER))
        )
    }

    @Test
    fun `other required apps are not a reason to keep it`() {
        assertTrue(
            LauncherConfigPlan.shouldRemoveLauncher(
                JSONObject("{}"), listOf("com.atakmap.app.civ", "com.android.chrome")
            )
        )
    }
}
