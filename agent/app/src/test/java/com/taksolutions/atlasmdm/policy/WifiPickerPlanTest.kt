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

import com.taksolutions.atlasmdm.policy.WifiPickerPlan.Security
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class WifiPickerPlanTest {

    private fun net(ssid: String, level: Int, security: Security = Security.WPA_PSK) =
        WifiPickerPlan.Network(ssid, security, bars = 0, level = level)

    // ----------------------------------------------------------------------- #
    // Reading the capabilities string
    // ----------------------------------------------------------------------- #

    @Test
    fun `an open network needs no password`() {
        assertEquals(Security.OPEN, WifiPickerPlan.securityOf("[ESS]"))
        assertFalse(Security.OPEN.needsPassword)
    }

    @Test
    fun `wpa2 personal is read as psk`() {
        assertEquals(Security.WPA_PSK, WifiPickerPlan.securityOf("[WPA2-PSK-CCMP][ESS]"))
    }

    /**
     * ⚠️ The reason the order in `securityOf` is not alphabetical. A WPA3
     * transitional access point advertises **both** SAE and WPA2-PSK; testing PSK
     * first joins it as WPA2, which works and silently gives up the WPA3 the
     * network was offering.
     */
    @Test
    fun `a wpa3 transitional network is read as wpa3, not wpa2`() {
        val caps = "[WPA2-PSK-CCMP][RSN-SAE+FT/SAE-CCMP][ESS]"
        assertEquals(Security.WPA3_SAE, WifiPickerPlan.securityOf(caps))
    }

    /**
     * ⚠️ An enterprise network matching on WPA2 would be offered a password box it
     * can never satisfy, and the user would try the password repeatedly.
     */
    @Test
    fun `an enterprise network is not mistaken for a password network`() {
        val caps = "[WPA2-EAP-CCMP][ESS]"
        assertEquals(Security.ENTERPRISE, WifiPickerPlan.securityOf(caps))
    }

    @Test
    fun `wep is recognised rather than treated as open`() {
        assertEquals(Security.WEP, WifiPickerPlan.securityOf("[WEP][ESS]"))
    }

    @Test
    fun `a missing capabilities string is open, not a crash`() {
        assertEquals(Security.OPEN, WifiPickerPlan.securityOf(null))
    }

    // ----------------------------------------------------------------------- #
    // Bars
    // ----------------------------------------------------------------------- #

    @Test
    fun `signal becomes bars, strongest to weakest`() {
        assertEquals(4, WifiPickerPlan.barsFor(-40))
        assertEquals(3, WifiPickerPlan.barsFor(-60))
        assertEquals(2, WifiPickerPlan.barsFor(-70))
        assertEquals(1, WifiPickerPlan.barsFor(-85))
        assertEquals(0, WifiPickerPlan.barsFor(-99))
    }

    // ----------------------------------------------------------------------- #
    // The list
    // ----------------------------------------------------------------------- #

    /**
     * ⚠️ A site with four access points on one network scans as four results, and
     * a list showing all four looks broken: the user cannot tell which to pick,
     * and the answer is that it does not matter.
     */
    @Test
    fun `one network with several access points is one row`() {
        val rows = WifiPickerPlan.rows(
            listOf(net("TAK-FIELD", -70), net("TAK-FIELD", -45), net("TAK-FIELD", -80))
        )
        assertEquals(1, rows.size)
        assertEquals(-45, rows.single().level, )
        assertEquals("the strongest access point decides the bars", 4, rows.single().bars)
    }

    @Test
    fun `a hidden network with no name is dropped rather than shown blank`() {
        val rows = WifiPickerPlan.rows(listOf(net("", -50), net("  ", -50), net("REAL", -60)))
        assertEquals(listOf("REAL"), rows.map { it.ssid })
    }

    @Test
    fun `the connected network is first, whatever its signal`() {
        val rows = WifiPickerPlan.rows(
            listOf(net("STRONG", -40), net("WEAK-BUT-MINE", -85)),
            connectedSsid = "WEAK-BUT-MINE",
        )
        assertEquals("WEAK-BUT-MINE", rows.first().ssid)
        assertTrue(rows.first().connected)
    }

    @Test
    fun `saved networks come before unknown ones`() {
        val rows = WifiPickerPlan.rows(
            listOf(net("UNKNOWN-STRONG", -40), net("SAVED-WEAK", -80)),
            savedSsids = setOf("SAVED-WEAK"),
        )
        assertEquals(listOf("SAVED-WEAK", "UNKNOWN-STRONG"), rows.map { it.ssid })
    }

    @Test
    fun `otherwise the strongest signal wins`() {
        val rows = WifiPickerPlan.rows(listOf(net("C", -80), net("A", -40), net("B", -60)))
        assertEquals(listOf("A", "B", "C"), rows.map { it.ssid })
    }

    @Test
    fun `an empty scan is an empty list, not a crash`() {
        assertEquals(emptyList<WifiPickerPlan.Network>(), WifiPickerPlan.rows(emptyList()))
    }
}
