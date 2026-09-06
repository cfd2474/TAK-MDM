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
 * ⚠️ **What is deliberately absent.** Airplane mode cannot be set by any app at
 * all. Bluetooth on/off lost `BluetoothAdapter.enable()` in API 33 in favour of a
 * user-consent intent, which is not something to raise from a locked kiosk. Both
 * appear in the commercial consoles this was modelled on; neither is achievable
 * here, and a control that silently did nothing would be worse than its absence.
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
    // Wi-Fi
    // ----------------------------------------------------------------------- #

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
        if (!accepted) AgentLog.w(TAG, "the platform refused to turn Wi-Fi ${if (enabled) "on" else "off"}")
        return isWifiEnabled(context)
    }

    private const val TAG = "DeviceControls"
}
