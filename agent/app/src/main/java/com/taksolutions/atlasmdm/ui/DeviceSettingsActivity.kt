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

import android.os.Bundle
import android.provider.Settings
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.taksolutions.atlasmdm.R
import com.taksolutions.atlasmdm.core.AgentConfig
import com.taksolutions.atlasmdm.diag.AgentLog
import com.taksolutions.atlasmdm.policy.DeviceSettingsPlan
import com.taksolutions.atlasmdm.policy.PolicyApplier
import org.json.JSONObject

/**
 * The settings a kiosk user may change, reached from the launcher's Device
 * Settings tile (W71).
 *
 * ⚠️ **In the agent, not the launcher, because this is where the permissions
 * are.** The launcher holds none; the agent is Device Owner, which is what makes
 * `setSystemSetting` and the night overlay possible at all. The launcher opens
 * this as an ordinary `package/activity` tile — the agent is already lock-task
 * permitted, so there is no IPC and nothing to keep in sync.
 *
 * ⚠️ **Only what the policy offers is drawn.** Not drawn-and-disabled: a greyed
 * row invites a user to keep trying and tells them nothing about why. A control
 * that is not offered simply is not there.
 *
 * ⚠️ **Every control shows what the device actually holds**, read back after the
 * write rather than assumed from what was asked. The platform can refuse, and a
 * switch that stays where the user put it while the device ignored them is the
 * failure this screen exists to avoid.
 */
class DeviceSettingsActivity : AppCompatActivity() {

    private val config by lazy { AgentConfig(this) }
    private val applier by lazy { PolicyApplier(this) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setTitle(R.string.device_settings_title)

        val kiosk = kioskPolicy()
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val p = ConsoleViews.dp(this@DeviceSettingsActivity, 16)
            setPadding(p, p, p, p)
        }

        if (!DeviceSettingsPlan.offersAnything(kiosk)) {
            // Reachable: the tile is removed at the next check-in, and a user can
            // be standing here when the policy changes. A blank screen would read
            // as a crash.
            root.addView(
                SettingsViews.note(this, getString(R.string.device_settings_none))
            )
        }

        if (DeviceSettingsPlan.offers(kiosk, DeviceSettingsPlan.OFFER_NIGHT_MODE)) {
            root.addView(ConsoleViews.sectionTitle(this, getString(R.string.night_mode)))
            root.addView(nightModeCard(kiosk))
        }
        val brightness = DeviceSettingsPlan.offers(kiosk, DeviceSettingsPlan.OFFER_BRIGHTNESS)
        val timeout = DeviceSettingsPlan.offers(kiosk, DeviceSettingsPlan.OFFER_SCREEN_TIMEOUT)
        if (brightness || timeout) {
            // One Display card holding whichever of the two is offered. Two cards
            // each with a single row reads as a screen missing its other half.
            root.addView(ConsoleViews.sectionTitle(this, getString(R.string.display)))
            root.addView(displayCard(brightness, timeout))
        }

        val volume = DeviceSettingsPlan.offers(kiosk, DeviceSettingsPlan.OFFER_VOLUME)
        val flashlight = DeviceSettingsPlan.offers(kiosk, DeviceSettingsPlan.OFFER_FLASHLIGHT)
        if (volume || flashlight) {
            root.addView(ConsoleViews.sectionTitle(this, getString(R.string.device_section)))
            root.addView(deviceCard(volume, flashlight))
        }

        if (DeviceSettingsPlan.offers(kiosk, DeviceSettingsPlan.OFFER_WIFI)) {
            root.addView(ConsoleViews.sectionTitle(this, getString(R.string.network)))
            root.addView(wifiCard())
        }

        setContentView(ScrollView(this).apply { addView(root) })
    }

    // ----------------------------------------------------------------------- #
    // Night mode
    // ----------------------------------------------------------------------- #

    private fun nightModeCard(kiosk: JSONObject) = ConsoleViews.card(this).also { card ->
        val body = ConsoleViews.body(card)
        val state = DeviceSettingsPlan.nightMode(
            kiosk, config.nightModeUserChoice, config.nightLevelUserChoice,
        )
        val (on, level) = state.value

        body.addView(
            SettingsViews.switchRow(
                this, getString(R.string.night_mode),
                getString(R.string.night_mode_summary), on,
            ) { wanted ->
                config.nightModeUserChoice = wanted
                applyNight(wanted, config.nightLevelUserChoice ?: level)
                wanted
            }
        )
        body.addView(
            SettingsViews.sliderRow(
                this, getString(R.string.night_strength), 0, 100, level, { "$it%" },
            ) { wanted ->
                config.nightLevelUserChoice = wanted
                // Only bites while the tint is on; storing it either way means the
                // strength the user chose is there when they switch it back on.
                applyNight(config.nightModeUserChoice ?: on, wanted)
            }
        )
    }

    private fun applyNight(on: Boolean, level: Int) {
        val kiosk = kioskPolicy()
        NightOverlay.set(
            this,
            enabled = on,
            hue = NightOverlay.Hue.from(kiosk.optString(DeviceSettingsPlan.KEY_NIGHT_HUE)),
            level = level,
        )
    }

    // ----------------------------------------------------------------------- #
    // Brightness
    // ----------------------------------------------------------------------- #

    private fun displayCard(brightness: Boolean, timeout: Boolean) =
        ConsoleViews.card(this).also { card ->
            val body = ConsoleViews.body(card)
            if (brightness) addBrightness(body)
            // A rule between them, not just spacing. Drawn without one, the
            // brightness note sat between the two sliders and read as if it might
            // belong to either - and a note about adaptive brightness attached to
            // the screen timeout is worse than no note at all.
            if (brightness && timeout) body.addView(ConsoleViews.divider(this))
            if (timeout) addScreenTimeout(body)
        }

    private fun addScreenTimeout(body: LinearLayout) {
        val current = runCatching {
            Settings.System.getInt(contentResolver, Settings.System.SCREEN_OFF_TIMEOUT)
        }.getOrDefault(TIMEOUTS_MILLIS[2])
        // Nearest offered step, so a device sitting on a value the operator set
        // does not jump the moment this screen is opened.
        val index = TIMEOUTS_MILLIS.indices.minByOrNull {
            kotlin.math.abs(TIMEOUTS_MILLIS[it] - current)
        } ?: 2

        body.addView(
            SettingsViews.sliderRow(
                this, getString(R.string.screen_timeout), 0, TIMEOUTS_MILLIS.lastIndex, index,
                { getString(TIMEOUT_LABELS[it]) },
            ) { step ->
                val millis = TIMEOUTS_MILLIS[step]
                // Stored first: its presence is what stops the policy driving the
                // value back at the next reconcile.
                config.screenTimeoutUserChoiceMillis = millis
                applier.setScreenTimeout(millis)
            }
        )
    }

    private fun addBrightness(body: LinearLayout) {
        body.addView(
            SettingsViews.switchRow(
                this, getString(R.string.brightness_auto),
                getString(R.string.brightness_auto_summary), isAutoBrightness(),
            ) { wanted ->
                applier.setBrightnessMode(wanted)
                // Read back rather than trusting the write: this is one of the
                // three keys a Device Owner may set, and it can still fail.
                isAutoBrightness()
            }
        )
        body.addView(
            SettingsViews.sliderRow(
                this, getString(R.string.brightness), MIN_BRIGHTNESS, MAX_BRIGHTNESS,
                currentBrightness(), { "${it * 100 / MAX_BRIGHTNESS}%" },
            ) { wanted -> applier.setBrightness(wanted) }
        )
        body.addView(
            SettingsViews.note(this, getString(R.string.brightness_note))
        )
    }

    // ----------------------------------------------------------------------- #
    // Volume, flashlight, Wi-Fi
    // ----------------------------------------------------------------------- #

    private fun deviceCard(volume: Boolean, flashlight: Boolean) =
        ConsoleViews.card(this).also { card ->
            val body = ConsoleViews.body(card)

            if (volume) {
                body.addView(
                    SettingsViews.sliderRow(
                        this, getString(R.string.volume), 0, 100,
                        DeviceControls.volumePercent(this), { pct -> "${'$'}pct%" },
                    ) { wanted -> DeviceControls.setVolumePercent(this, wanted) }
                )
            }
            if (volume && flashlight) body.addView(ConsoleViews.divider(this))

            if (flashlight) {
                if (DeviceControls.hasTorch(this)) {
                    body.addView(
                        // Starts off every time, because Android gives no way to
                        // read the torch without registering a callback. Claiming
                        // a state this screen cannot know would be worse than the
                        // small oddity of a switch that resets.
                        SettingsViews.switchRow(
                            this, getString(R.string.flashlight),
                            getString(R.string.flashlight_summary), false,
                        ) { wanted -> DeviceControls.setTorch(this, wanted) }
                    )
                } else {
                    // Said, not hidden. The operator offered it, and silence would
                    // leave them wondering whether the policy reached the device.
                    body.addView(SettingsViews.note(this, getString(R.string.no_torch)))
                }
            }
        }

    private fun wifiCard() = ConsoleViews.card(this).also { card ->
        ConsoleViews.body(card).addView(
            SettingsViews.switchRow(
                this, getString(R.string.wifi), getString(R.string.wifi_summary),
                DeviceControls.isWifiEnabled(this),
            ) { wanted ->
                // Reads the state back: setWifiEnabled returns false rather than
                // throwing when refused, and a switch that stayed where the user
                // put it while Wi-Fi did not move is the lie this screen avoids.
                DeviceControls.setWifiEnabled(this, wanted)
            }
        )
    }

    private fun isAutoBrightness(): Boolean = runCatching {
        Settings.System.getInt(contentResolver, Settings.System.SCREEN_BRIGHTNESS_MODE) ==
            Settings.System.SCREEN_BRIGHTNESS_MODE_AUTOMATIC
    }.getOrDefault(false)

    private fun currentBrightness(): Int = runCatching {
        Settings.System.getInt(contentResolver, Settings.System.SCREEN_BRIGHTNESS)
    }.getOrDefault(MAX_BRIGHTNESS / 2)

    // ----------------------------------------------------------------------- #

    /**
     * The KIOSK section of the policy this device last received.
     *
     * Read from stored state rather than fetched: this screen opens on a device
     * that may be offline, and a settings screen that needs the network to draw
     * itself is a settings screen that fails when it is most needed.
     */
    private fun kioskPolicy(): JSONObject = runCatching {
        JSONObject(config.cachedDesiredState ?: "{}")
            .optJSONObject("policy")?.optJSONObject("KIOSK") ?: JSONObject()
    }.getOrElse {
        AgentLog.w(TAG, "could not read the stored policy: ${it.message}")
        JSONObject()
    }

    private companion object {
        const val TAG = "DeviceSettings"

        /** Android's own range for `SCREEN_BRIGHTNESS`. 0 is not black, it is dimmest. */
        const val MIN_BRIGHTNESS = 1
        const val MAX_BRIGHTNESS = 255

        /**
         * Fixed steps rather than a free slider: these are the values Android's
         * own display settings offer, and a kiosk timeout of "37 seconds" helps
         * nobody. 15 s is the floor because anything shorter makes a mounted
         * device unusable.
         */
        val TIMEOUTS_MILLIS = intArrayOf(
            15_000, 30_000, 60_000, 120_000, 300_000, 600_000, 1_800_000,
        )
        val TIMEOUT_LABELS = intArrayOf(
            R.string.timeout_15s, R.string.timeout_30s, R.string.timeout_1m,
            R.string.timeout_2m, R.string.timeout_5m, R.string.timeout_10m,
            R.string.timeout_30m,
        )
    }
}
