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

import org.json.JSONObject

/** One Wi-Fi network a policy wants on the device. */
data class DesiredWifi(
    val ssid: String,
    val security: String,       // open | wep | wpa_psk | wpa3_sae
    val password: String?,
    val hidden: Boolean,
    val autoJoin: Boolean,
)

/**
 * The pure part of Wi-Fi policy application: parse the NETWORKS spec and work out
 * what to add and what to remove. Kept free of `WifiManager` so the diff logic is
 * unit-tested even though the platform calls in [PolicyApplier.applyNetworks] are
 * only exercised on hardware.
 */
object WifiPlan {

    fun desired(spec: JSONObject): List<DesiredWifi> {
        val array = spec.optJSONArray("wifi_networks") ?: return emptyList()
        val out = ArrayList<DesiredWifi>(array.length())
        for (i in 0 until array.length()) {
            val o = array.optJSONObject(i) ?: continue
            val ssid = o.optString("ssid").trim()
            if (ssid.isEmpty()) continue
            out += DesiredWifi(
                ssid = ssid,
                security = o.optString("security", "wpa_psk"),
                password = o.optString("password").takeIf { it.isNotEmpty() },
                hidden = o.optBoolean("hidden", false),
                autoJoin = o.optBoolean("auto_join", true),
            )
        }
        return out
    }

    /** SSIDs the agent previously configured that the policy no longer lists. */
    fun toRemove(previouslyManaged: Set<String>, desired: List<DesiredWifi>): Set<String> {
        val wanted = desired.mapTo(HashSet()) { it.ssid }
        return previouslyManaged.filterTo(HashSet()) { it !in wanted }
    }
}
