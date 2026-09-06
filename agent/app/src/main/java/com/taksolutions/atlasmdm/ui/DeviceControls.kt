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

import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothManager
import android.content.Context
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.media.AudioManager
import android.net.wifi.WifiManager
import com.taksolutions.atlasmdm.diag.AgentLog

/**
 * The device controls the kiosk's Device Settings screen can actually work (W71).
 *
 * ⚠️ **Every one of these can be refused by the platform, and each says so by
 * returning what the device ended up at.** A control that reported success and
 * changed nothing is the failure this screen exists to avoid: the user reports a
 * broken tablet, and every log says the write succeeded.
 *
 * ⚠️ **Airplane mode is deliberately absent, and cannot be added.**
 * `Settings.Global.AIRPLANE_MODE_ON` needs `WRITE_SECURE_SETTINGS`, which a
 * Device Owner cannot self-grant, and it is not on the `setGlobalSetting`
 * allowlist. "Radios off" below is the honest substitute: it turns off the two
 * radios this app can actually reach, and does not pretend to touch the cellular
 * one.
 *
 * ⚠️ **Bluetooth *is* here, contrary to an earlier reading.** API 33 deprecated
 * `BluetoothAdapter.enable()` for **ordinary apps**; device owners and profile
 * owners are explicitly exempt, which is what makes this reachable from a DPC.
 */
object DeviceControls {

    // ----------------------------------------------------------------------- #
    // Volume
    // ----------------------------------------------------------------------- #

    /**
     * Media volume as a percentage, because the raw range differs by device and a
     * slider labelled 0–7 on one tablet and 0–15 on another is not a setting a
     * person can be told about over a radio.
     */
    fun volumePercent(context: Context): Int {
        val audio = context.getSystemService(AudioManager::class.java) ?: return 0
        val max = audio.getStreamMaxVolume(AudioManager.STREAM_MUSIC).coerceAtLeast(1)
        return audio.getStreamVolume(AudioManager.STREAM_MUSIC) * 100 / max
    }

    /** Set media volume, returning the percentage the device actually holds. */
    fun setVolumePercent(context: Context, percent: Int): Int {
        val audio = context.getSystemService(AudioManager::class.java) ?: return 0
        val max = audio.getStreamMaxVolume(AudioManager.STREAM_MUSIC).coerceAtLeast(1)
        val steps = (percent.coerceIn(0, 100) * max + 50) / 100
        runCatching {
            // No FLAG_SHOW_UI: the system volume panel over a kiosk is another
            // surface the user can reach that policy never allowed for.
            audio.setStreamVolume(AudioManager.STREAM_MUSIC, steps, 0)
        }.onFailure {
            // DISALLOW_ADJUST_VOLUME throws here. The console refuses that pairing,
            // so reaching this means an older policy or a hand-edited one.
            AgentLog.w(TAG, "could not set volume: ${it.message}")
        }
        return volumePercent(context)
    }

    // ----------------------------------------------------------------------- #
    // Flashlight
    // ----------------------------------------------------------------------- #

    /** True when this device has a torch at all — tablets often do not. */
    fun hasTorch(context: Context): Boolean = torchCameraId(context) != null

    /**
     * ⚠️ The torch is **not** readable on Android without registering a callback,
     * so the caller holds the state. Every entry to the screen therefore starts it
     * at off, which is honest: the screen cannot claim to know.
     */
    fun setTorch(context: Context, on: Boolean): Boolean {
        val manager = context.getSystemService(CameraManager::class.java) ?: return false
        val id = torchCameraId(context) ?: return false
        return runCatching {
            manager.setTorchMode(id, on)
            on
        }.getOrElse {
            // `setCameraDisabled` from a kiosk policy blocks this, and so does
            // another app holding the camera.
            AgentLog.w(TAG, "could not set the torch: ${it.message}")
            !on
        }
    }

    private fun torchCameraId(context: Context): String? = runCatching {
        val manager = context.getSystemService(CameraManager::class.java) ?: return null
        manager.cameraIdList.firstOrNull { id ->
            manager.getCameraCharacteristics(id)
                .get(CameraCharacteristics.FLASH_INFO_AVAILABLE) == true
        }
    }.getOrNull()

    // ----------------------------------------------------------------------- #
    // Bluetooth
    // ----------------------------------------------------------------------- #

    fun hasBluetooth(context: Context): Boolean = adapter(context) != null

    fun isBluetoothEnabled(context: Context): Boolean = adapter(context)?.isEnabled ?: false

    /**
     * Turn Bluetooth on or off, returning what the device ended up at.
     *
     * ⚠️ `enable()` and `disable()` are deprecated and return **false** rather than
     * throwing when refused — the same shape as Wi-Fi, and the same reason to read
     * the state back rather than trust the call.
     *
     * ⚠️ The radio does not settle synchronously. `isEnabled` immediately after a
     * successful call still reports the old value, so the caller is told what it
     * asked for when the call was accepted; the switch corrects itself when the
     * screen is next drawn. Reporting the stale value instead would make every
     * successful toggle look like a refusal.
     */
    @Suppress("DEPRECATION", "MissingPermission")
    fun setBluetoothEnabled(context: Context, enabled: Boolean): Boolean {
        val adapter = adapter(context) ?: return false
        val accepted = runCatching {
            if (enabled) adapter.enable() else adapter.disable()
        }.getOrElse {
            AgentLog.w(TAG, "could not set Bluetooth: ${it.message}")
            false
        }
        if (accepted) {
            AgentLog.i(TAG, "Bluetooth turned ${if (enabled) "on" else "off"} from Device Settings")
        } else {
            AgentLog.w(
                TAG,
                "the platform refused to turn Bluetooth ${if (enabled) "on" else "off"}",
            )
        }
        return if (accepted) enabled else isBluetoothEnabled(context)
    }

    private fun adapter(context: Context): BluetoothAdapter? =
        context.getSystemService(BluetoothManager::class.java)?.adapter

    // ----------------------------------------------------------------------- #
    // Radios off
    // ----------------------------------------------------------------------- #

    /**
     * Turn off every radio this app can reach (W72).
     *
     * ⚠️ **Not airplane mode, and it does not claim to be.** No app can set
     * airplane mode, and the cellular radio is untouched. This does what airplane
     * mode is usually wanted for on a TAK device — go quiet on Wi-Fi and
     * Bluetooth — and the field description says exactly that, because a control
     * an operator believes silences a device that is still on cellular would be
     * worse than no control.
     *
     * @return true when everything it can reach is now off.
     */
    fun setRadiosOff(context: Context): Boolean {
        val wifi = !setWifiEnabled(context, false)
        val bluetooth = if (hasBluetooth(context)) !setBluetoothEnabled(context, false) else true
        return wifi && bluetooth
    }

    // ----------------------------------------------------------------------- #
    // Wi-Fi
    // ----------------------------------------------------------------------- #

    /**
     * The network the device is on, or null.
     *
     * ⚠️ Android reports `<unknown ssid>` rather than null when it will not say —
     * which happens while associating, and without location permission. Showing
     * that string to a user would be worse than showing nothing.
     */
    @Suppress("DEPRECATION", "MissingPermission")
    fun connectedSsid(context: Context): String? = runCatching {
        context.getSystemService(WifiManager::class.java)
            ?.connectionInfo?.ssid?.trim('"')
            ?.takeIf { it.isNotBlank() && it != "<unknown ssid>" }
    }.getOrNull()

    fun isWifiEnabled(context: Context): Boolean =
        context.getSystemService(WifiManager::class.java)?.isWifiEnabled ?: false

    /**
     * Turn Wi-Fi on or off, returning what the device ended up at.
     *
     * ⚠️ `setWifiEnabled` returns **false** rather than throwing when it is not
     * permitted, and it has been blocked for ordinary apps since Android 10.
     * A Device Owner is supposed to be exempt; that is the part unverified on our
     * hardware, and the reason this reads the state back instead of trusting the
     * call.
     */
    fun setWifiEnabled(context: Context, enabled: Boolean): Boolean {
        val wifi = context.getSystemService(WifiManager::class.java) ?: return false
        val accepted = runCatching { wifi.setWifiEnabled(enabled) }.getOrElse {
            AgentLog.w(TAG, "could not set Wi-Fi: ${it.message}")
            false
        }
        val actual = isWifiEnabled(context)
        // ⚠️ Logged either way, on purpose. Logging only refusals made this
        // unanswerable from a device: a successful toggle said nothing, so
        // silence in the log meant either "it worked" or "nobody tried it", and
        // this is the one control whose Device-Owner permission is unverified.
        if (!accepted || actual != enabled) {
            AgentLog.w(TAG, "the platform refused to turn Wi-Fi ${if (enabled) "on" else "off"}")
        } else {
            AgentLog.i(TAG, "Wi-Fi turned ${if (enabled) "on" else "off"} from Device Settings")
        }
        return actual
    }

    private const val TAG = "DeviceControls"
}
