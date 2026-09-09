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
import android.media.AudioAttributes
import android.media.AudioManager
import android.media.Ringtone
import android.media.RingtoneManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import com.taksolutions.atlasmdm.R
import com.taksolutions.atlasmdm.diag.AgentLog

/**
 * Making a device announce itself so a person can find it (W107).
 *
 * ⚠️ **Two requirements that pull against each other, and both matter.**
 *
 * *Loud on a silent device.* The tablet someone is hunting for is, almost by
 * definition, the one that is silenced and in a bag. Played on the media stream
 * this would be inaudible in exactly the case it exists for — so it goes out on
 * `STREAM_ALARM`, which sounds through silent mode, with the alarm volume raised
 * for the duration.
 *
 * *Stoppable by whoever finds it.* A tablet that rings for ever in a drawer, with
 * no way to stop it short of the password, is worse than one that is merely lost.
 * So the noise is bounded by a timer **and** by an overlay with a Stop button, and
 * either one ends it.
 *
 * ⚠️ **The volume is put back.** Raising the alarm stream and leaving it raised
 * would mean an operator's ping silently reconfigured the device — the next alarm
 * the user set would go off at full volume, and nothing would connect the two.
 */
object DeviceAnnouncer {

    /**
     * How long the sound runs unattended.
     *
     * Long enough to search a room, short enough that a device pinged by mistake
     * in a meeting stops on its own before anyone has to go looking for it.
     */
    const val DURATION_MS = 30_000L

    private val main = Handler(Looper.getMainLooper())

    private var ringtone: Ringtone? = null
    private var vibrator: Vibrator? = null
    private var restoreVolume: Int? = null
    private var stopAt: Runnable? = null

    /** Is a ping sounding right now? */
    @Synchronized
    fun isAnnouncing(): Boolean = ringtone != null

    /**
     * Start the sound, the vibration and the overlay.
     *
     * Returns immediately: this is called from the sync worker, and holding that
     * thread for thirty seconds would stall the check-in that has to report the
     * command succeeded.
     */
    @Synchronized
    fun start(context: Context, durationMs: Long = DURATION_MS) {
        // ⚠️ Restart rather than stack. Two pings would otherwise leave two
        // ringtones playing, and stopping would silence only one of them.
        if (isAnnouncing()) {
            AgentLog.i(TAG, "ping already sounding; restarting its timer")
            main.removeCallbacks(stopAt ?: Runnable {})
        } else {
            raiseAlarmVolume(context)
            startSound(context)
            startVibration(context)
        }

        val stop = Runnable { stop(context) }
        stopAt = stop
        main.postDelayed(stop, durationMs)

        AlertOverlay.show(
            context,
            context.getString(R.string.ping_title),
            context.getString(R.string.ping_message),
            dismissLabel = context.getString(R.string.ping_stop),
            onDismiss = { stop(context) },
        )
    }

    /** Stop everything and put the volume back. Safe to call more than once. */
    @Synchronized
    fun stop(context: Context) {
        stopAt?.let { main.removeCallbacks(it) }
        stopAt = null

        ringtone?.let { tone ->
            runCatching { if (tone.isPlaying) tone.stop() }
                .onFailure { AgentLog.w(TAG, "could not stop the ping tone: ${it.message}") }
        }
        ringtone = null

        vibrator?.let { v -> runCatching { v.cancel() } }
        vibrator = null

        restoreVolume?.let { previous ->
            val audio = context.getSystemService(AudioManager::class.java)
            runCatching {
                audio?.setStreamVolume(AudioManager.STREAM_ALARM, previous, 0)
                AgentLog.i(TAG, "ping finished; alarm volume restored to $previous")
            }.onFailure { AgentLog.w(TAG, "could not restore alarm volume: ${it.message}") }
        }
        restoreVolume = null
    }

    private fun raiseAlarmVolume(context: Context) {
        val audio = context.getSystemService(AudioManager::class.java) ?: return
        runCatching {
            val current = audio.getStreamVolume(AudioManager.STREAM_ALARM)
            val max = audio.getStreamMaxVolume(AudioManager.STREAM_ALARM)
            // Remembered before it is changed, and only then — a failure to raise
            // must not leave a "restore" that lowers a volume nobody touched.
            restoreVolume = current
            audio.setStreamVolume(AudioManager.STREAM_ALARM, max, 0)
            AgentLog.i(TAG, "ping: alarm volume $current -> $max")
        }.onFailure {
            AgentLog.w(TAG, "could not raise the alarm volume: ${it.message}")
        }
    }

    private fun startSound(context: Context) {
        runCatching {
            // ⚠️ The alarm tone, not the notification tone. A notification is
            // exactly what a silenced device suppresses.
            val uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
                ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE)
                ?: return
            val tone = RingtoneManager.getRingtone(context, uri) ?: return
            tone.audioAttributes = AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_ALARM)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                .build()
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) tone.isLooping = true
            tone.play()
            ringtone = tone
            AgentLog.i(TAG, "ping sounding")
        }.onFailure {
            AgentLog.w(TAG, "could not sound the ping: ${it.message}")
        }
    }

    private fun startVibration(context: Context) {
        runCatching {
            val v = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                context.getSystemService(VibratorManager::class.java)?.defaultVibrator
            } else {
                @Suppress("DEPRECATION")
                context.getSystemService(Vibrator::class.java)
            } ?: return
            if (!v.hasVibrator()) return

            // Repeating pattern: a device face-down on carpet is found by feel as
            // often as by ear.
            val pattern = longArrayOf(0, 600, 400)
            v.vibrate(VibrationEffect.createWaveform(pattern, 0))
            vibrator = v
        }.onFailure {
            AgentLog.w(TAG, "could not vibrate: ${it.message}")
        }
    }

    private const val TAG = "DeviceAnnouncer"
}
