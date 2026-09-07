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

import android.app.Activity
import android.os.Bundle
import android.widget.Toast
import com.taksolutions.atlasmdm.R
import com.taksolutions.atlasmdm.core.AgentConfig
import com.taksolutions.atlasmdm.policy.DeviceSettingsPlan
import org.json.JSONObject

/**
 * The Power tile on the kiosk home screen (W74).
 *
 * ⚠️ **It draws nothing.** The tile's whole job is to raise Android's power menu,
 * so this activity is transparent, does its one thing, and finishes — a screen
 * that appeared behind the menu would still be there when the user dismissed it,
 * and they would have to get out of it.
 *
 * ⚠️ **It checks the policy, like every other route in.** The activity is exported
 * so the launcher can start it; without the check, anything on the device could
 * raise the power menu on a kiosk whose operator never offered it.
 *
 * ⚠️ **`Activity`, not `AppCompatActivity`.** AppCompat inflates a decor view even
 * for a transparent theme, and that is a visible flicker on a screen whose only
 * purpose is to not be seen.
 */
class PowerTileActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        if (!DeviceSettingsPlan.offers(kioskPolicy(), DeviceSettingsPlan.OFFER_POWER)) {
            finish()
            return
        }

        if (!PowerMenuService.show()) {
            // Said out loud rather than failing silently. From a tile there is no
            // other surface to explain on, and a tile that does nothing when
            // tapped is the failure this whole screen exists to avoid.
            Toast.makeText(this, R.string.power_unavailable, Toast.LENGTH_LONG).show()
        }
        finish()
    }

    /**
     * ⚠️ No transition. The default fade would show this activity's empty window
     * for a frame between the tap and the menu.
     */
    override fun finish() {
        super.finish()
        overridePendingTransition(0, 0)
    }

    private fun kioskPolicy(): JSONObject = runCatching {
        JSONObject(AgentConfig(this).cachedDesiredState ?: "{}")
            .optJSONObject("policy")?.optJSONObject("KIOSK") ?: JSONObject()
    }.getOrElse { JSONObject() }
}
