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
 * Turning a Wi-Fi scan into a list a person can choose from (W72).
 *
 * Pure, and separate from the scanning, because everything here is a rule that
 * goes subtly wrong rather than loudly: a security type read from a capabilities
 * string, one network appearing four times because it has four access points, an
 * ordering that buries the network you are standing next to.
 */
object WifiPickerPlan {

    enum class Security(val key: String) {
        OPEN("open"),
        WEP("wep"),
        WPA_PSK("wpa_psk"),
        WPA3_SAE("wpa3_sae"),
        /** 802.1x and anything else a password box cannot join. */
        ENTERPRISE("enterprise"),
        ;

        val needsPassword: Boolean get() = this != OPEN
    }

    data class Network(
        val ssid: String,
        val security: Security,
        /** 0-4, the bars a user sees. */
        val bars: Int,
        val level: Int,
        val connected: Boolean = false,
        val saved: Boolean = false,
    )

    /**
     * Read the security from a `ScanResult.capabilities` string.
     *
     * ⚠️ Order matters and is not alphabetical. A WPA3 transitional access point
     * advertises **both** `SAE` and `WPA2-PSK`, so testing for PSK first would
     * join it as WPA2 — which works, and silently gives up WPA3 on a network that
     * offered it. `EAP` is checked before everything because an enterprise network
     * matching on `WPA2` would be offered a password box it can never satisfy.
     */
    fun securityOf(capabilities: String?): Security {
        val caps = capabilities.orEmpty().uppercase()
        return when {
            "EAP" in caps -> Security.ENTERPRISE
            "SAE" in caps -> Security.WPA3_SAE
            "PSK" in caps -> Security.WPA_PSK
            "WEP" in caps -> Security.WEP
            else -> Security.OPEN
        }
    }

    /**
     * Signal strength as bars, the way Android's own Wi-Fi list does it.
     *
     * Raw dBm is meaningless to a user: -67 is good and -68 is good, but the
     * numbers invite comparison that the radio does not support.
     */
    fun barsFor(level: Int): Int = when {
        level >= -55 -> 4
        level >= -67 -> 3
        level >= -78 -> 2
        level >= -90 -> 1
        else -> 0
    }

    /**
     * One row per network, strongest access point winning, in the order to show.
     *
     * ⚠️ **De-duplicated by SSID.** A site with four access points on one network
     * scans as four results, and a list showing all four looks broken — the user
     * cannot tell which to pick, and the answer is that it does not matter.
     *
     * ⚠️ **A blank SSID is dropped, not shown blank.** Hidden networks scan with an
     * empty SSID, and a row with no name is untappable and unexplainable.
     *
     * Ordered: the connected network first, then saved ones, then by signal. The
     * network someone is standing next to should not be below one they cannot
     * reach.
     */
    fun rows(
        scanned: List<Network>,
        connectedSsid: String? = null,
        savedSsids: Set<String> = emptySet(),
    ): List<Network> {
        val best = LinkedHashMap<String, Network>()
        for (network in scanned) {
            val ssid = network.ssid.trim()
            if (ssid.isEmpty()) continue
            val marked = network.copy(
                ssid = ssid,
                connected = ssid == connectedSsid,
                saved = ssid in savedSsids,
                bars = barsFor(network.level),
            )
            val seen = best[ssid]
            if (seen == null || marked.level > seen.level) best[ssid] = marked
        }
        return best.values.sortedWith(
            compareByDescending<Network> { it.connected }
                .thenByDescending { it.saved }
                .thenByDescending { it.level }
        )
    }
}
