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
import android.graphics.Color
import android.graphics.PixelFormat
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import com.taksolutions.atlasmdm.diag.AgentLog

/**
 * The deliberate way out of kiosk, for someone standing at the device (W65).
 *
 * A small invisible target in one corner counts taps; enough of them in quick
 * succession raises a passcode prompt, and the right passcode releases the lock.
 *
 * ⚠️ **The passcode is a gate, not a secret.** It arrives in the policy the device
 * already holds, so anyone with USB debugging can read it. It exists to stop a
 * user idly tapping their way out of a wall-mounted tablet — not to withstand
 * someone determined. The console says so on the field; this says so here, so the
 * next person to touch this code does not mistake it for security.
 *
 * ⚠️ **The target is deliberately tiny and in a corner.** It sits over whatever
 * the kiosk app is showing, and a larger one would eat taps the app needed —
 * turning an escape hatch into a fault in the very app the device exists to run.
 */
object KioskExitGate {

    private val main = Handler(Looper.getMainLooper())

    private var target: View? = null
    private var prompt: View? = null
    private var taps = 0
    private var lastTapAt = 0L

    /** How long a run of taps may take before the count starts again. */
    private const val TAP_WINDOW_MILLIS = 3_000L

    /** Corner target size. Big enough to hit on purpose, small enough to miss. */
    private const val TARGET_DP = 56

    fun isAvailable(context: Context): Boolean = Settings.canDrawOverlays(context)

    /**
     * Put the tap target on screen, or take it away.
     *
     * Idempotent, because it is called from every reconcile: a kiosk that is still
     * a kiosk must not stack a new overlay every two minutes.
     */
    fun set(context: Context, enabled: Boolean, tapCount: Int, passcode: String, onExit: () -> Unit) {
        main.post {
            if (!enabled || passcode.isBlank()) {
                remove(context)
                return@post
            }
            if (target != null) return@post
            if (!isAvailable(context)) {
                // Said once, and not treated as a policy failure: the device is
                // still locked, which is the safe direction to fail in.
                AgentLog.w(TAG, "kiosk exit gate needs the draw-over-apps permission")
                return@post
            }
            show(context, tapCount.coerceAtLeast(3), passcode, onExit)
        }
    }

    private fun show(context: Context, tapCount: Int, passcode: String, onExit: () -> Unit) {
        val wm = context.getSystemService(WindowManager::class.java) ?: return
        val size = (TARGET_DP * context.resources.displayMetrics.density).toInt()

        val view = View(context).apply {
            setBackgroundColor(Color.TRANSPARENT)
            setOnClickListener {
                val now = System.currentTimeMillis()
                taps = if (now - lastTapAt > TAP_WINDOW_MILLIS) 1 else taps + 1
                lastTapAt = now
                if (taps >= tapCount) {
                    taps = 0
                    askForPasscode(context, passcode, onExit)
                }
            }
        }

        val params = WindowManager.LayoutParams(
            size,
            size,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            // NOT_FOCUSABLE keeps the kiosk app's keyboard and focus intact; the
            // target only needs touches, and stealing focus from the app the
            // device exists to run would be a poor trade for an escape hatch.
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT,
        ).apply { gravity = Gravity.TOP or Gravity.START }

        runCatching { wm.addView(view, params) }
            .onSuccess { target = view; AgentLog.i(TAG, "kiosk exit gate armed ($tapCount taps)") }
            .onFailure { AgentLog.w(TAG, "could not arm the kiosk exit gate: ${it.message}") }
    }

    private fun askForPasscode(context: Context, passcode: String, onExit: () -> Unit) {
        if (prompt != null) return
        val wm = context.getSystemService(WindowManager::class.java) ?: return

        val input = EditText(context).apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            hint = "Exit passcode"
        }
        val card = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#FF0B1E37"))
            setPadding(48, 48, 48, 48)
            addView(TextView(context).apply {
                text = "Leave kiosk mode"
                textSize = 18f
                setTextColor(Color.parseColor("#FFE7EDF4"))
            })
            addView(input)
        }

        val scrim = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setBackgroundColor(Color.parseColor("#CC000000"))
            addView(card)
        }

        fun dismiss() {
            prompt?.let { runCatching { wm.removeView(it) } }
            prompt = null
        }

        card.addView(Button(context).apply {
            text = "Unlock"
            setOnClickListener {
                if (input.text.toString() == passcode) {
                    dismiss()
                    onExit()
                } else {
                    // Says nothing about how wrong it was, and does not lock out:
                    // this gate cannot be hardened into a real one, so pretending
                    // otherwise with attempt limits would only strand an operator.
                    Toast.makeText(context, "Wrong passcode", Toast.LENGTH_SHORT).show()
                    input.setText("")
                }
            }
        })
        card.addView(Button(context).apply {
            text = "Cancel"
            setOnClickListener { dismiss() }
        })

        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            // Focusable, unlike the target: this one has a text field, and a
            // passcode box that cannot take a keyboard is not a passcode box.
            0,
            PixelFormat.TRANSLUCENT,
        )

        runCatching { wm.addView(scrim, params) }
            .onSuccess { prompt = scrim }
            .onFailure { AgentLog.w(TAG, "could not show the exit prompt: ${it.message}") }
    }

    fun remove(context: Context) {
        val wm = context.getSystemService(WindowManager::class.java)
        target?.let { runCatching { wm?.removeView(it) } }
        prompt?.let { runCatching { wm?.removeView(it) } }
        target = null
        prompt = null
        taps = 0
    }

    private const val TAG = "KioskExitGate"
}
