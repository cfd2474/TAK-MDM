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
import android.graphics.PixelFormat
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.View
import android.view.WindowManager
import com.taksolutions.atlasmdm.diag.AgentLog

/**
 * Night mode: a coloured wash over everything on screen (W68, Chunk 2).
 *
 * ⚠️ **In the agent, not the launcher, and that is the design.** Night mode exists
 * so a user can read the device without losing dark adaptation — and what they
 * are reading is ATAK's map, not the home screen. A tint drawn by the launcher
 * would stop at its own edges and vanish the moment they opened the app it was
 * for. Only a `SYSTEM_ALERT_WINDOW` overlay covers everything, and the agent is
 * the app that has that permission.
 *
 * ⚠️ **It must never take a touch.** `FLAG_NOT_TOUCHABLE` and
 * `FLAG_NOT_FOCUSABLE`: an overlay across the whole screen that swallowed input
 * would be a bricked device, recoverable only by removing the policy, and on a
 * red screen the user would not even be able to see what had gone wrong.
 *
 * ⚠️ **Red is not decoration.** Red light preserves scotopic vision in a way amber
 * and green do not; that is why it is the default and why the alpha is capped
 * well below opaque — a tint the user cannot see through is a screen that is off.
 */
object NightOverlay {

    private val main = Handler(Looper.getMainLooper())
    private var view: View? = null
    private var showing: Int? = null

    enum class Hue(val key: String, val rgb: Int) {
        RED("red", 0xFF0000),
        AMBER("amber", 0xFFBF00),
        GREEN("green", 0xFF00),
        ;

        companion object {
            fun from(value: String?): Hue =
                entries.firstOrNull { it.key.equals(value?.trim(), ignoreCase = true) } ?: RED
        }
    }

    /**
     * The strongest wash allowed, as an alpha out of 255.
     *
     * ⚠️ Not 255, and not close. At full opacity the tint *is* the screen and the
     * device looks broken; the operator's "100" has to mean "as dark as is still
     * usable", because a policy that can blank a field device is a policy someone
     * will set by accident.
     */
    private const val MAX_ALPHA = 190

    fun isAvailable(context: Context): Boolean = Settings.canDrawOverlays(context)

    /**
     * Show the wash, change it, or take it away.
     *
     * Idempotent, and called from every reconcile: an unchanged night mode must
     * not add a second overlay every two minutes.
     *
     * @param level 0–100 from policy. 0 removes the overlay entirely rather than
     *   drawing a fully transparent one, so "night mode on at zero" costs nothing.
     */
    fun set(context: Context, enabled: Boolean, hue: Hue, level: Int) {
        val alpha = if (!enabled) 0 else (level.coerceIn(0, 100) * MAX_ALPHA / 100)
        val color = if (alpha == 0) 0 else (alpha shl 24) or hue.rgb

        main.post {
            if (color == 0) {
                removeOnMainThread(context)
                return@post
            }
            if (!isAvailable(context)) {
                // Said once per change, and not a policy failure: the device is
                // usable, just not tinted, and the agent's own permissions screen
                // is where an operator fixes it.
                if (showing != color) {
                    AgentLog.w(TAG, "night mode needs the draw-over-apps permission")
                    showing = color
                }
                return@post
            }
            if (showing == color && view != null) return@post
            showOnMainThread(context.applicationContext, color)
        }
    }

    private fun showOnMainThread(context: Context, color: Int) {
        val windows = context.getSystemService(WindowManager::class.java) ?: return

        // Recolouring the existing view rather than replacing it: a remove/add
        // cycle flashes the untinted screen, which at night is the one thing this
        // feature exists to prevent.
        view?.let {
            it.setBackgroundColor(color)
            showing = color
            return
        }

        val wash = View(context).apply { setBackgroundColor(color) }
        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE or
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                // Covers the status and navigation bars too. A tint that stopped
                // at them would leave two bright strips at the top and bottom of
                // a screen someone is using to keep their night vision.
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT,
        )

        runCatching { windows.addView(wash, params) }
            .onSuccess {
                view = wash
                showing = color
                AgentLog.i(TAG, "night mode on (alpha ${color ushr 24})")
            }
            .onFailure { AgentLog.w(TAG, "could not draw the night overlay: ${it.message}") }
    }

    private fun removeOnMainThread(context: Context) {
        val windows = context.getSystemService(WindowManager::class.java)
        view?.let {
            runCatching { windows?.removeView(it) }
            AgentLog.i(TAG, "night mode off")
        }
        view = null
        showing = null
    }

    /** Take the wash away, whatever state it is in. Used when kiosk is released. */
    fun remove(context: Context) = main.post { removeOnMainThread(context) }

    private const val TAG = "NightOverlay"
}
