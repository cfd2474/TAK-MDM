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
import android.graphics.drawable.GradientDrawable
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.Gravity
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.content.ContextCompat
import com.taksolutions.atlasmdm.R
import com.taksolutions.atlasmdm.diag.AgentLog

/**
 * A full-width alert drawn over whatever the device is doing (W45).
 *
 * For the messages a heads-up notification is too quiet to carry. The operator
 * saw v52's banner and called it *"very small"* — this is the escalation, and it
 * finally uses the `SYSTEM_ALERT_WINDOW` permission the setup wizard has been
 * asking for since W19 without ever spending it.
 *
 * ⚠️ **Deliberately dismissible.** One tap clears it. An overlay that could not be
 * cleared would sit on top of ATAK's map, and the moment that matters is exactly
 * the moment nobody wants to fight a data-usage notice. Demanding an
 * acknowledgement is the aggression that was asked for; trapping the user is not.
 *
 * ⚠️ **Never the only copy of a message.** `TYPE_APPLICATION_OVERLAY` comes with
 * the platform's own caveat — *"the system may change the position, size, or
 * visibility of these windows at anytime"* — so callers post a notification too.
 * The overlay grabs attention; the notification is the record.
 */
object AlertOverlay {

    private val main = Handler(Looper.getMainLooper())

    /** True when the overlay can actually be drawn — checked, never assumed. */
    fun isAvailable(context: Context): Boolean = Settings.canDrawOverlays(context)

    /**
     * Show [message] over everything, if permitted.
     *
     * @return true if the overlay was shown; false when the caller must rely on
     *   its notification alone.
     */
    fun show(context: Context, title: String, message: String): Boolean {
        if (!isAvailable(context)) {
            AgentLog.w(TAG, "overlay not permitted; falling back to the notification alone")
            return false
        }

        // The tracker runs on a sync worker; window manipulation is main-thread only.
        main.post { showOnMainThread(context.applicationContext, title, message) }
        return true
    }

    private fun showOnMainThread(context: Context, title: String, message: String) {
        val windows = context.getSystemService(WindowManager::class.java) ?: return

        val scrim = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setBackgroundColor(Color.argb(190, 0, 0, 0))
            setPadding(dp(context, 24), dp(context, 24), dp(context, 24), dp(context, 24))
        }

        val card = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            background = GradientDrawable().apply {
                setColor(ContextCompat.getColor(context, R.color.atlas_navy_panel))
                cornerRadius = dp(context, 16).toFloat()
                setStroke(dp(context, 2), ContextCompat.getColor(context, R.color.atlas_warn))
            }
            setPadding(dp(context, 28), dp(context, 28), dp(context, 28), dp(context, 20))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT,
            )
        }

        card.addView(TextView(context).apply {
            text = title
            textSize = 26f
            setTextColor(ContextCompat.getColor(context, R.color.atlas_warn))
            setTypeface(typeface, android.graphics.Typeface.BOLD)
        })

        card.addView(TextView(context).apply {
            text = message
            textSize = 19f
            setTextColor(ContextCompat.getColor(context, R.color.atlas_text))
            setPadding(0, dp(context, 16), 0, 0)
        })

        scrim.addView(card)

        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            // Not FLAG_NOT_TOUCHABLE: the whole point is that a person has to
            // acknowledge it. FLAG_NOT_FOCUSABLE is off too, so the dismiss button
            // reliably takes a tap.
            WindowManager.LayoutParams.FLAG_DIM_BEHIND,
            android.graphics.PixelFormat.TRANSLUCENT,
        ).apply {
            dimAmount = 0.55f
            gravity = Gravity.CENTER
        }

        // Added before the button so the click listener can capture it.
        val remove = {
            runCatching { windows.removeView(scrim) }
                .onFailure { AgentLog.w(TAG, "overlay already gone: ${it.message}") }
            Unit
        }

        card.addView(Button(context).apply {
            text = context.getString(R.string.alert_dismiss)
            textSize = 17f
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT,
            ).apply { topMargin = dp(context, 24) }
            setOnClickListener { remove() }
        })

        runCatching { windows.addView(scrim, params) }
            .onFailure {
                // Losing the overlay is survivable; the notification still carries
                // the message. Losing the sync to an exception would not be.
                AgentLog.w(TAG, "could not show overlay: ${it.message}")
                return
            }

        AgentLog.i(TAG, "alert overlay shown: $title")

        // A safety net, not a convenience: a device left face-down in a pouch
        // would otherwise keep the scrim up until someone found it.
        main.postDelayed({ remove() }, AUTO_DISMISS_MS)
    }

    private fun dp(context: Context, value: Int): Int =
        (value * context.resources.displayMetrics.density).toInt()

    private const val TAG = "AlertOverlay"

    /** Long enough to be read and acknowledged, short enough not to strand a device. */
    private const val AUTO_DISMISS_MS = 2 * 60 * 1000L
}
