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
import android.os.Handler
import android.os.Looper
import android.text.InputType
import android.util.TypedValue
import android.view.View
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import com.taksolutions.atlasmdm.R
import com.taksolutions.atlasmdm.core.AgentConfig
import com.taksolutions.atlasmdm.policy.DeviceSettingsPlan
import com.taksolutions.atlasmdm.policy.PolicyApplier
import com.taksolutions.atlasmdm.policy.WifiPickerPlan
import org.json.JSONObject

/**
 * Choosing a Wi-Fi network from the kiosk (W72).
 *
 * ⚠️ **This lets a kiosk user attach the device to any network they can see,
 * including one they control.** That was the operator's choice over a list
 * limited to networks the NETWORKS policy had provisioned, and it is the reason
 * this screen exists rather than a read-only list. Recorded here because the
 * consequence is not obvious from the code.
 *
 * ⚠️ **It refuses to open unless the policy offers Wi-Fi.** The activity is
 * exported so the launcher can start it, and a settings screen that could be
 * launched into on a device whose operator never offered Wi-Fi would be a way
 * round the policy rather than an expression of it.
 */
class WifiPickerActivity : AppCompatActivity() {

    private val config by lazy { AgentConfig(this) }
    private val applier by lazy { PolicyApplier(this) }
    private val main = Handler(Looper.getMainLooper())

    private lateinit var list: LinearLayout

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setTitle(R.string.wifi_pick_title)

        if (!DeviceSettingsPlan.offers(kioskPolicy(), DeviceSettingsPlan.OFFER_WIFI)) {
            finish()
            return
        }

        list = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val p = ConsoleViews.dp(this@WifiPickerActivity, 16)
            setPadding(p, p, p, p)
        }
        setContentView(ScrollView(this).apply { addView(list) })
        draw()
    }

    override fun onResume() {
        super.onResume()
        // Scans arrive asynchronously, so the first draw shows the last scan and
        // this one shows the fresh results a moment later.
        main.postDelayed(::draw, SCAN_SETTLE_MILLIS)
    }

    override fun onPause() {
        main.removeCallbacksAndMessages(null)
        super.onPause()
    }

    private fun draw() {
        if (isFinishing || isDestroyed) return
        list.removeAllViews()

        val scan = WifiScanner.scan(this)
        val problem = when (scan.problem) {
            WifiScanner.Problem.WIFI_OFF -> R.string.wifi_pick_off
            // The one worth naming. Android returns an empty list with no reason,
            // which is indistinguishable from "no networks here" while standing in
            // a building full of them.
            WifiScanner.Problem.LOCATION_OFF -> R.string.wifi_pick_needs_location
            WifiScanner.Problem.NOTHING_FOUND -> R.string.wifi_pick_none
            WifiScanner.Problem.NONE -> null
        }
        if (problem != null) {
            list.addView(SettingsViews.note(this, getString(problem)))
            return
        }

        val card = ConsoleViews.card(this)
        val body = ConsoleViews.body(card)
        scan.networks.forEachIndexed { index, network ->
            if (index > 0) body.addView(ConsoleViews.divider(this))
            body.addView(row(network))
        }
        list.addView(card)
        list.addView(SettingsViews.note(this, getString(R.string.wifi_pick_refresh_hint)))
    }

    private fun row(network: WifiPickerPlan.Network): View {
        val summary = buildString {
            append(getString(bars(network.bars)))
            if (network.security != WifiPickerPlan.Security.OPEN) {
                append(getString(R.string.wifi_pick_secured))
            }
            if (network.connected) append(getString(R.string.wifi_pick_connected))
            else if (network.saved) append(getString(R.string.wifi_pick_saved))
        }
        return SettingsViews.actionRow(this, network.ssid, summary) { tapped(network) }
    }

    private fun tapped(network: WifiPickerPlan.Network) {
        if (network.connected) return
        when (network.security) {
            // ⚠️ Said plainly rather than offered a box. An enterprise network
            // needs an identity and a certificate, and a password prompt that can
            // never succeed invites the user to try their password repeatedly.
            WifiPickerPlan.Security.ENTERPRISE ->
                toast(getString(R.string.wifi_pick_enterprise))
            WifiPickerPlan.Security.OPEN -> join(network, null)
            else -> askForPassword(network)
        }
    }

    private fun askForPassword(network: WifiPickerPlan.Network) {
        val input = EditText(this).apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            setHint(R.string.wifi_pick_password)
        }
        val frame = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val p = ConsoleViews.dp(this@WifiPickerActivity, 20)
            setPadding(p, p / 2, p, 0)
            addView(input, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT))
        }

        AlertDialog.Builder(this)
            .setTitle(network.ssid)
            .setView(frame)
            .setPositiveButton(R.string.wifi_pick_join) { _, _ ->
                join(network, input.text.toString())
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    private fun join(network: WifiPickerPlan.Network, password: String?) {
        val failure = applier.joinWifi(network.ssid, network.security.key, password)
        if (failure != null) {
            toast(failure)
            return
        }
        toast(getString(R.string.wifi_pick_joining, network.ssid))
        // Association takes a few seconds, so the list is redrawn once it has had
        // time rather than immediately, where it would still show the old network
        // as connected and look like nothing happened.
        main.postDelayed(::draw, JOIN_SETTLE_MILLIS)
    }

    private fun toast(text: CharSequence) =
        Toast.makeText(this, text, Toast.LENGTH_SHORT).show()

    private fun bars(count: Int): Int = when (count) {
        4 -> R.string.wifi_bars_4
        3 -> R.string.wifi_bars_3
        2 -> R.string.wifi_bars_2
        1 -> R.string.wifi_bars_1
        else -> R.string.wifi_bars_0
    }

    private fun kioskPolicy(): JSONObject = runCatching {
        JSONObject(config.cachedDesiredState ?: "{}")
            .optJSONObject("policy")?.optJSONObject("KIOSK") ?: JSONObject()
    }.getOrElse { JSONObject() }

    private companion object {
        const val SCAN_SETTLE_MILLIS = 2_500L
        const val JOIN_SETTLE_MILLIS = 4_000L
    }
}
