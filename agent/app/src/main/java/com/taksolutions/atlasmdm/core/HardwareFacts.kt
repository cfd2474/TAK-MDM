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

package com.taksolutions.atlasmdm.core

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.BatteryManager
import android.telephony.TelephonyManager
import androidx.core.content.ContextCompat
import com.taksolutions.atlasmdm.diag.AgentLog
import org.json.JSONObject

/**
 * What this device is, physically: charge, IMEIs, line number (W108).
 *
 * ⚠️ **A missing value and an absent capability are different answers**, and this
 * is where the difference is decided. A Wi-Fi-only tablet has no IMEI and never
 * will; a cellular one whose IMEI could not be read has a problem worth chasing.
 * Reported as the same blank they are indistinguishable in the console, and an
 * operator goes hunting for a permission bug on a device with no modem — so
 * `has_telephony` is always reported, separately from the values.
 *
 * ✅ **No new permission.** `READ_PHONE_STATE` is already declared and
 * self-granted, and §6a-ii of the Android reference records the finding that an
 * ordinary `READ_PHONE_STATE` is enough for a Device Owner to read device
 * identifiers on Android 16 — verified on `SM-X520` against the widely repeated
 * claim that `READ_PRIVILEGED_PHONE_STATE` is required.
 */
object HardwareFacts {

    /**
     * Add what can be read to a check-in payload.
     *
     * Every field is omitted rather than sent as null when it cannot be read, so
     * the server's "absent means the agent said nothing" rule holds — except
     * `has_telephony`, which is always known and always sent.
     */
    fun addTo(payload: JSONObject, context: Context) {
        addBattery(payload, context)
        addTelephony(payload, context)
    }

    // ----------------------------------------------------------------- battery

    private fun addBattery(payload: JSONObject, context: Context) {
        runCatching {
            val manager = context.getSystemService(BatteryManager::class.java) ?: return
            val level = manager.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
            // ⚠️ The API returns Integer.MIN_VALUE, not -1, when it has nothing —
            // and a bare `level >= 0` check would pass a garbage value straight
            // through on a device that does not support the property.
            if (level in 0..100) payload.put("battery_level", level)

            payload.put("battery_charging", manager.isCharging)
        }.onFailure {
            AgentLog.w(TAG, "could not read the battery: ${it.message}")
        }
    }

    // --------------------------------------------------------------- telephony

    private fun addTelephony(payload: JSONObject, context: Context) {
        val hasRadio = context.packageManager
            .hasSystemFeature(PackageManager.FEATURE_TELEPHONY)
        // ⚠️ Always sent, whatever else fails below. This is the field that lets
        // the console say "no cellular radio" instead of leaving a blank that
        // means nothing in particular.
        payload.put("has_telephony", hasRadio)
        if (!hasRadio) return

        if (!granted(context, Manifest.permission.READ_PHONE_STATE)) {
            AgentLog.w(TAG, "READ_PHONE_STATE not granted; no IMEI reported")
            return
        }

        val telephony = context.getSystemService(TelephonyManager::class.java) ?: return

        // ⚠️ Each slot in its own runCatching. `getImei(slot)` throws for a slot
        // that does not exist, and one exception must not cost the other slot's
        // value — a dual-SIM read that gives up after slot 0 fails is how a
        // single-SIM device would report nothing at all.
        val slots = runCatching { telephony.activeModemCount }.getOrDefault(1).coerceIn(1, 2)
        for (slot in 0 until slots) {
            runCatching {
                @Suppress("MissingPermission")
                val imei = telephony.getImei(slot)
                if (!imei.isNullOrBlank()) {
                    payload.put(if (slot == 0) "imei" else "imei2", imei)
                }
            }.onFailure {
                AgentLog.w(TAG, "no IMEI for slot $slot: ${it.message}")
            }
        }

        addPhoneNumber(payload, context, telephony)
    }

    private fun addPhoneNumber(
        payload: JSONObject,
        context: Context,
        telephony: TelephonyManager,
    ) {
        // ⚠️ **Usually absent, and that is not a fault.** The line number lives on
        // the SIM only if the carrier provisioned it there, and many never do. It
        // is reported when present and simply omitted when not, rather than
        // reported as an empty string that the console would have to interpret.
        if (!granted(context, Manifest.permission.READ_PHONE_NUMBERS) &&
            !granted(context, Manifest.permission.READ_PHONE_STATE)
        ) {
            return
        }
        runCatching {
            @Suppress("MissingPermission", "DEPRECATION")
            val number = telephony.line1Number
            if (!number.isNullOrBlank()) payload.put("phone_number", number)
        }.onFailure {
            AgentLog.w(TAG, "could not read the line number: ${it.message}")
        }
    }

    private fun granted(context: Context, permission: String): Boolean =
        ContextCompat.checkSelfPermission(context, permission) ==
            PackageManager.PERMISSION_GRANTED

    private const val TAG = "HardwareFacts"
}
