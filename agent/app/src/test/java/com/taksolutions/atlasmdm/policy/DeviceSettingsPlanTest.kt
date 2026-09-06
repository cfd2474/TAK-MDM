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
 * Who wins when the operator and the user both have an opinion (W71).
 *
 * The rule is the whole feature, and every failure here is silent on the device:
 * a switch that comes back on by itself, or a user's answer still in force on a
 * device where nobody can see or change it.
 */
class DeviceSettingsPlanTest {

    private fun kiosk(json: String) = JSONObject(json)

    private val offered = """{"device_setting_night_mode": true, "kiosk_night_mode": false}"""
    private val notOffered = """{"kiosk_night_mode": true, "kiosk_night_level": 70}"""

    @Test
    fun `nothing is offered by default`() {
        assertFalse(DeviceSettingsPlan.offersAnything(kiosk("{}")))
        assertFalse(
            DeviceSettingsPlan.offers(kiosk("{}"), DeviceSettingsPlan.OFFER_NIGHT_MODE)
        )
    }

    @Test
    fun `any single control is enough for the tile`() {
        assertTrue(
            DeviceSettingsPlan.offersAnything(kiosk("""{"device_setting_flashlight": true}"""))
        )
    }

    @Test
    fun `policy decides when the user has said nothing`() {
        val (on, level) = DeviceSettingsPlan
            .nightMode(kiosk(notOffered), userOn = null, userLevel = null).value
        assertTrue(on)
        assertEquals(70, level)
    }

    /**
     * ⚠️ The reason the override exists. The agent re-applies policy every two
     * minutes, so without this the user turns the tint off and watches it come
     * back — which is worse than never offering the control, because it looks
     * like the device is fighting them.
     */
    @Test
    fun `the user's answer beats policy while the control is offered`() {
        val (on, _) = DeviceSettingsPlan
            .nightMode(kiosk("""{"device_setting_night_mode": true, "kiosk_night_mode": true}"""),
                userOn = false, userLevel = null).value
        assertFalse(on)
    }

    @Test
    fun `the user's strength beats policy too`() {
        val (_, level) = DeviceSettingsPlan
            .nightMode(kiosk("""{"device_setting_night_mode": true, "kiosk_night_level": 20}"""),
                userOn = null, userLevel = 90).value
        assertEquals(90, level)
    }

    /**
     * ⚠️ The other half, and the one that would rot quietly: an operator who
     * withdraws the control must get policy back. Otherwise the user's old answer
     * goes on overriding it on a device where nobody can see or change it.
     */
    @Test
    fun `withdrawing the control returns the device to policy`() {
        val (on, level) = DeviceSettingsPlan
            .nightMode(kiosk(notOffered), userOn = false, userLevel = 5).value
        assertTrue("policy says on, and the user is no longer being asked", on)
        assertEquals(70, level)
        assertTrue(DeviceSettingsPlan.shouldForgetOverrides(kiosk(notOffered)))
    }

    @Test
    fun `an offered control keeps the overrides`() {
        assertFalse(DeviceSettingsPlan.shouldForgetOverrides(kiosk(offered)))
    }

    @Test
    fun `a silly stored strength is clamped rather than drawn`() {
        val (_, high) = DeviceSettingsPlan
            .nightMode(kiosk(offered), userOn = true, userLevel = 900).value
        assertEquals(100, high)
        val (_, low) = DeviceSettingsPlan
            .nightMode(kiosk(offered), userOn = true, userLevel = -5).value
        assertEquals(0, low)
    }

    @Test
    fun `a policy strength out of range is clamped too`() {
        val (_, level) = DeviceSettingsPlan
            .nightMode(kiosk("""{"kiosk_night_level": 400}"""), null, null).value
        assertEquals(100, level)
    }
}
