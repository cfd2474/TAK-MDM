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

import android.content.Context
import android.location.LocationManager
import android.net.wifi.WifiManager
import com.taksolutions.atlasmdm.diag.AgentLog
import com.taksolutions.atlasmdm.policy.WifiPickerPlan

/**
 * Finding the Wi-Fi networks around the device (W72).
 *
 * ⚠️ **Scan results are empty without location services**, and Android says
 * nothing about why — `getScanResults()` simply returns an empty list. That is
 * indistinguishable from "no networks here", so this reports the reason instead
 * of leaving the user staring at an empty list in a building full of Wi-Fi.
 *
 * ⚠️ **`startScan` is throttled to four calls per two minutes** for ordinary apps
 * since Android 9. A Device Owner is exempt, which is the only reason a refresh
 * button is worth having here at all.
 */
object WifiScanner {

    /** Why the list is empty, when it is. */
    enum class Problem { NONE, WIFI_OFF, LOCATION_OFF, NOTHING_FOUND }

    data class Scan(val networks: List<WifiPickerPlan.Network>, val problem: Problem)

    @Suppress("DEPRECATION", "MissingPermission")
    fun scan(context: Context): Scan {
        val wifi = context.getSystemService(WifiManager::class.java)
            ?: return Scan(emptyList(), Problem.WIFI_OFF)
        if (!wifi.isWifiEnabled) return Scan(emptyList(), Problem.WIFI_OFF)
        if (!locationEnabled(context)) return Scan(emptyList(), Problem.LOCATION_OFF)

        // Deprecated since API 28 and still the only way for an app to ask. The
        // result arrives asynchronously, so this kicks off a refresh and reads
        // whatever the last scan left — which is why the screen shows a list
        // immediately and a fresher one a moment later.
        runCatching { wifi.startScan() }
            .onFailure { AgentLog.w(TAG, "startScan refused: ${it.message}") }

        val results = runCatching { wifi.scanResults }.getOrElse {
            AgentLog.w(TAG, "could not read scan results: ${it.message}")
            emptyList()
        }

        val connected = runCatching {
            wifi.connectionInfo?.ssid?.trim('"')?.takeIf { it.isNotBlank() && it != "<unknown ssid>" }
        }.getOrNull()

        val saved = runCatching {
            // A Device Owner sees the networks it configured; an ordinary app gets
            // an empty list here rather than an error.
            wifi.configuredNetworks.mapNotNull { it.SSID?.trim('"') }.toSet()
        }.getOrDefault(emptySet())

        val networks = results.map {
            WifiPickerPlan.Network(
                ssid = it.SSID.orEmpty(),
                security = WifiPickerPlan.securityOf(it.capabilities),
                bars = 0,
                level = it.level,
            )
        }

        val rows = WifiPickerPlan.rows(networks, connected, saved)
        return Scan(rows, if (rows.isEmpty()) Problem.NOTHING_FOUND else Problem.NONE)
    }

    /**
     * ⚠️ Both providers, not just GPS. A device indoors often has network location
     * on and GPS off, and checking only GPS would tell the user to enable
     * something that is already on in the way that matters.
     */
    private fun locationEnabled(context: Context): Boolean = runCatching {
        context.getSystemService(LocationManager::class.java)?.isLocationEnabled == true
    }.getOrDefault(false)

    private const val TAG = "WifiScanner"
}
