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

/**
 * Who wins when the operator and the user both have an opinion (W71).
 *
 * ⚠️ **Offering a control is a promise that the answer sticks.** The agent
 * re-applies policy every two minutes, so without this the user would turn night
 * mode off and watch it come back on — which is worse than never offering the
 * control, because it looks like the device is fighting them.
 *
 * ⚠️ **Withdrawing the control takes the override with it.** If the operator stops
 * offering a setting, the user's old answer must not go on quietly overriding
 * policy on a device where nobody can see or change it any more.
 *
 * Pure, because the rule is the whole feature and none of it needs a device.
 */
object DeviceSettingsPlan {

    /** One control's state: what applies now, and whether the user may change it. */
    data class Control<T>(val value: T, val offered: Boolean)

    const val KEY_NIGHT_MODE = "kiosk_night_mode"
    const val KEY_NIGHT_LEVEL = "kiosk_night_level"
    const val KEY_NIGHT_HUE = "kiosk_night_hue"

    const val OFFER_NIGHT_MODE = "device_setting_night_mode"
    const val OFFER_BRIGHTNESS = "device_setting_brightness"
    const val OFFER_SCREEN_TIMEOUT = "device_setting_screen_timeout"
    const val OFFER_VOLUME = "device_setting_volume"
    const val OFFER_FLASHLIGHT = "device_setting_flashlight"
    const val OFFER_WIFI = "device_setting_wifi"

    const val DEFAULT_NIGHT_LEVEL = 50

    /** True when the policy lets the user change [offer] from Device Settings. */
    fun offers(kiosk: JSONObject, offer: String): Boolean = kiosk.optBoolean(offer, false)

    /** Any control at all — which is what decides whether the tile appears. */
    fun offersAnything(kiosk: JSONObject): Boolean = OFFERS.any { offers(kiosk, it) }

    private val OFFERS = listOf(
        OFFER_NIGHT_MODE, OFFER_BRIGHTNESS, OFFER_SCREEN_TIMEOUT,
        OFFER_VOLUME, OFFER_FLASHLIGHT, OFFER_WIFI,
    )

    /**
     * Whether the night tint is on, and how strong.
     *
     * @param userOn the user's own answer, or null if they have not given one.
     * @param userLevel likewise.
     */
    fun nightMode(
        kiosk: JSONObject,
        userOn: Boolean?,
        userLevel: Int?,
    ): Control<Pair<Boolean, Int>> {
        val offered = offers(kiosk, OFFER_NIGHT_MODE)
        val policyOn = kiosk.optBoolean(KEY_NIGHT_MODE, false)
        val policyLevel = kiosk.optInt(KEY_NIGHT_LEVEL, DEFAULT_NIGHT_LEVEL).coerceIn(0, 100)

        // The user's answer counts only while they are being offered the control.
        val on = if (offered && userOn != null) userOn else policyOn
        val level = if (offered && userLevel != null) userLevel.coerceIn(0, 100) else policyLevel
        return Control(on to level, offered)
    }

    /**
     * True when the user's stored override for [offer] should be forgotten.
     *
     * ⚠️ Called on every reconcile. A device whose operator withdrew a control
     * must go back to what policy says, and keeping the override would leave a
     * setting nobody on the device can reach and nobody in the console can see.
     */
    fun shouldForget(kiosk: JSONObject, offer: String): Boolean = !offers(kiosk, offer)

    /** The night-mode override specifically, kept for readability at the call site. */
    fun shouldForgetOverrides(kiosk: JSONObject): Boolean =
        shouldForget(kiosk, OFFER_NIGHT_MODE)
}
