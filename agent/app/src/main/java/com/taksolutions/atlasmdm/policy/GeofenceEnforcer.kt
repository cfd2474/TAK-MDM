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

import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import com.taksolutions.atlasmdm.admin.MdmDeviceAdminReceiver
import com.taksolutions.atlasmdm.core.AgentConfig
import com.taksolutions.atlasmdm.diag.AgentLog
import com.taksolutions.atlasmdm.ui.DeviceControls

/**
 * Carrying out what the active fences add up to (W106 C4).
 *
 * ⚠️ **The release path is the one that matters, and it is the one nobody sees.**
 * An apply that fails is visible — the radio is still on, the operator notices. A
 * release that never happens is invisible: the device sits with Wi-Fi off, outside
 * the fence, for ever, and the console shows a policy that no longer applies.
 *
 * So a radio this class turns off is *recorded* as ours, together with what it was
 * before, and put back when no fence asks any more. That is the same rule
 * `hiddenByPolicy` follows and for the same reason: "everything currently off" is
 * not the same set as "everything we turned off", and undoing the former would be
 * this agent reversing a decision that was never its own.
 *
 * ⚠️ **Password enforcement is not done here.** It is folded into the PASSWORD
 * spec (see `GeofencePlan.passwordSpecWithFence`) so that the existing single
 * writer applies and releases it. A second writer would be undone by the next
 * reconcile, minutes later, without a word.
 */
class GeofenceEnforcer(private val context: Context) {

    private val config: AgentConfig by lazy { AgentConfig(context) }

    /**
     * Apply [actions], and release anything no longer asked for.
     *
     * Returns notes for the check-in's apply warnings — a fence that could not do
     * what it said should be visible in the console, not only in a device log
     * nobody thinks to collect.
     */
    fun enforce(actions: GeofencePlan.Actions): List<String> {
        val notes = mutableListOf<String>()

        notes += enforceRadio(
            label = "wifi",
            desired = actions.wifi,
            savedKey = config::geofenceWifiRestore,
            isEnabled = { DeviceControls.isWifiEnabled(context) },
            setEnabled = { DeviceControls.setWifiEnabled(context, it) },
            present = { true },
        )
        notes += enforceRadio(
            label = "bluetooth",
            desired = actions.bluetooth,
            savedKey = config::geofenceBluetoothRestore,
            isEnabled = { DeviceControls.isBluetoothEnabled(context) },
            setEnabled = { DeviceControls.setBluetoothEnabled(context, it) },
            present = { DeviceControls.hasBluetooth(context) },
        )

        lockIfNewlyEnforced(actions.passwordEnforced)

        val signature = actions.activeFences.sorted().joinToString(",")
        if (signature != config.activeGeofences) {
            AgentLog.i(
                TAG,
                if (signature.isEmpty()) "no geofence applies now"
                else "geofences now active: $signature",
            )
            config.activeGeofences = signature
        }
        return notes
    }

    /**
     * Lock the device when a password requirement *starts* applying.
     *
     * ⚠️ **On the transition, never on every evaluation.** The operator asked for
     * "require and lock now" so the rule takes effect at once rather than at the
     * next lock. Re-locking on each evaluation would relock the tablet every
     * couple of minutes for as long as it stayed inside the fence, which is not
     * enforcement — it is an unusable device.
     */
    private fun lockIfNewlyEnforced(enforced: Boolean) {
        if (enforced == config.geofencePasswordEnforced) return
        config.geofencePasswordEnforced = enforced

        if (!enforced) {
            AgentLog.i(TAG, "geofence password requirement released")
            return
        }

        val dpm = context.getSystemService(DevicePolicyManager::class.java) ?: return
        if (!dpm.isDeviceOwnerApp(context.packageName)) return
        runCatching {
            dpm.lockNow()
            AgentLog.i(TAG, "geofence requires a password: device locked")
        }.onFailure { AgentLog.w(TAG, "could not lock the device: ${it.message}") }
    }

    private inline fun enforceRadio(
        label: String,
        desired: GeofencePlan.Radio,
        savedKey: kotlin.reflect.KMutableProperty0<String?>,
        isEnabled: () -> Boolean,
        setEnabled: (Boolean) -> Boolean,
        present: () -> Boolean,
    ): List<String> {
        val saved = savedKey.get()

        if (desired == GeofencePlan.Radio.UNMANAGED) {
            // Nothing asks any more. Put back only what we changed.
            if (saved == null) return emptyList()
            savedKey.set(null)
            if (!present()) return emptyList()
            val restoreTo = saved == "on"
            val reached = setEnabled(restoreTo)
            AgentLog.i(TAG, "$label restored to ${if (restoreTo) "on" else "off"} (was ours)")
            return if (reached == restoreTo) emptyList()
            else listOf("geofence: could not restore $label")
        }

        if (!present()) return listOf("geofence: this device has no $label radio")

        val want = desired == GeofencePlan.Radio.ON
        if (saved == null) {
            // First time a fence takes this radio: remember where it started, so
            // leaving the fence returns it there rather than to a guess.
            savedKey.set(if (isEnabled()) "on" else "off")
        }

        if (isEnabled() == want) return emptyList()

        val reached = setEnabled(want)
        AgentLog.i(TAG, "geofence set $label ${if (want) "on" else "off"}")
        return if (reached == want) emptyList()
        else listOf("geofence: the platform refused to turn $label ${if (want) "on" else "off"}")
    }

    companion object {
        private const val TAG = "GeofenceEnforcer"
    }
}
