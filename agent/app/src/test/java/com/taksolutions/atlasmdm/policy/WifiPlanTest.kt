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
import org.junit.Assert.assertTrue
import org.junit.Test

class WifiPlanTest {

    @Test
    fun `parses a wifi entry with defaults`() {
        val spec = JSONObject("""{"wifi_networks":[{"ssid":"TAK-Field","security":"wpa_psk","password":"hunter22"}]}""")

        val list = WifiPlan.desired(spec)

        assertEquals(1, list.size)
        val n = list[0]
        assertEquals("TAK-Field", n.ssid)
        assertEquals("wpa_psk", n.security)
        assertEquals("hunter22", n.password)
        assertEquals(false, n.hidden) // default false
    }

    @Test
    fun `honours explicit hidden`() {
        val spec = JSONObject(
            """{"wifi_networks":[{"ssid":"Ops","security":"open","hidden":true}]}"""
        )
        val n = WifiPlan.desired(spec)[0]
        assertEquals(true, n.hidden)
        assertEquals(null, n.password)
    }

    @Test
    fun `skips blank and malformed entries`() {
        val spec = JSONObject("""{"wifi_networks":[{"ssid":""},{"no_ssid":1},{"ssid":"Real"}]}""")
        assertEquals(listOf("Real"), WifiPlan.desired(spec).map { it.ssid })
    }

    @Test
    fun `empty or absent spec yields nothing`() {
        assertEquals(emptyList<DesiredWifi>(), WifiPlan.desired(JSONObject()))
        assertEquals(emptyList<DesiredWifi>(), WifiPlan.desired(JSONObject("""{"wifi_networks":[]}""")))
    }

    @Test
    fun `toRemove is what we managed minus what is still wanted`() {
        val desired = WifiPlan.desired(JSONObject("""{"wifi_networks":[{"ssid":"Keep"}]}"""))

        val removed = WifiPlan.toRemove(setOf("Keep", "Drop", "AlsoDrop"), desired)

        assertEquals(setOf("Drop", "AlsoDrop"), removed)
    }

    @Test
    fun `toRemove is empty when everything is still wanted`() {
        val desired = WifiPlan.desired(JSONObject("""{"wifi_networks":[{"ssid":"A"},{"ssid":"B"}]}"""))
        assertTrue(WifiPlan.toRemove(setOf("A", "B"), desired).isEmpty())
    }
}
