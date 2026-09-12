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
import android.graphics.drawable.GradientDrawable
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.util.TypedValue
import android.view.Gravity
import android.view.WindowManager
import android.widget.TextView
import com.taksolutions.atlasmdm.diag.AgentLog

/**
 * The device's name, as a window rather than as paint (W132).
 *
 * ⚠️ **The wallpaper was the wrong surface and two attempts at geometry proved
 * it.** The system owns a wallpaper's placement — crop, pan and parallax, per
 * orientation, per launcher, and OEM shells differ again. The agent supplies
 * pixels and has no say in where they land, so the label drifted on every
 * rotation no matter how the bitmap was built. W131's square canvas made the
 * two orientations agree with *each other*, which is not the same as putting
 * the label somewhere.
 *
 * The clock does not have this problem because it is not painted into the
 * wallpaper: it is a view, and the window manager re-lays it out on every
 * rotation. This is that.
 *
 * ⚠️ **It must never take a touch.** `FLAG_NOT_TOUCHABLE` and
 * `FLAG_NOT_FOCUSABLE`, for the same reason `NightOverlay` carries them and
 * worse: a label that swallowed input would be a bricked tablet, recoverable
 * only by removing the policy.
 *
 * ⚠️ **It cannot appear on the lock screen.** `TYPE_APPLICATION_OVERLAY` sits
 * below the keyguard, and showing above it needs a system-signature window type
 * the agent cannot have. A locked tablet is identified by the `{device}` token
 * in the lock-screen message instead (W134) — a different mechanism for a
 * surface this one cannot reach.
 *
 * ⚠️ **This object decides nothing.** It shows the text it is handed and hides
 * when handed null. *When* that should happen — only over a launcher — belongs
 * to [DeviceIdLabelController], because the window has no way to know what is
 * in front of it and no business asking.
 */
object DeviceIdOverlay {

    private val main = Handler(Looper.getMainLooper())
    private var view: TextView? = null
    private var showing: String? = null

    /** Text size in sp. Large enough to read across a room, small enough to ignore. */
    private const val TEXT_SP = 22f

    fun isAvailable(context: Context): Boolean = Settings.canDrawOverlays(context)

    /**
     * Show [name], change it, or take the label away when [name] is null.
     *
     * Idempotent, and called from every reconcile: an unchanged name must not
     * add a second window every two minutes.
     */
    fun set(context: Context, name: String?) {
        val app = context.applicationContext
        main.post {
            if (name.isNullOrBlank()) {
                removeOnMainThread(app)
                return@post
            }
            if (!isAvailable(app)) {
                // Said once per change, and not a policy failure: the device
                // works, it just is not labelled, and the agent's own
                // permissions screen is where an operator fixes it.
                if (showing != name) {
                    AgentLog.w(TAG, "the device ID label needs the draw-over-apps permission")
                    showing = name
                }
                return@post
            }
            if (showing == name && view != null) return@post
            showOnMainThread(app, name)
        }
    }

    private fun showOnMainThread(context: Context, name: String) {
        val windows = context.getSystemService(WindowManager::class.java) ?: return

        // Retexting the existing view rather than replacing it: a remove/add
        // cycle flickers, and a rename is the common case this has to handle.
        view?.let {
            it.text = name
            showing = name
            return
        }

        val label = TextView(context).apply {
            text = name
            setTextColor(Color.WHITE)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, TEXT_SP)
            val pad = (TEXT_SP * 0.6f * resources.displayMetrics.scaledDensity).toInt()
            setPadding(pad, pad / 2, pad, pad / 2)
            // A plate rather than plain text: this sits over a launcher, a map
            // and whatever else, and unbacked white text is unreadable on about
            // half of them.
            background = GradientDrawable().apply {
                setColor(0xB3000000.toInt())
                cornerRadius = pad.toFloat()
            }
        }

        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE or
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT,
        ).apply {
            // ⚠️ Gravity, not coordinates. The window manager re-applies this on
            // every rotation, which is the entire reason this exists — a pixel
            // offset would drift exactly the way the wallpaper did.
            gravity = Gravity.TOP or Gravity.CENTER_HORIZONTAL
            y = (24 * context.resources.displayMetrics.density).toInt()
        }

        runCatching { windows.addView(label, params) }
            .onSuccess {
                view = label
                showing = name
                AgentLog.i(TAG, "device ID label shown: $name")
            }
            .onFailure {
                AgentLog.w(TAG, "could not draw the device ID label: ${it.message}")
            }
    }

    private fun removeOnMainThread(context: Context) {
        val windows = context.getSystemService(WindowManager::class.java)
        view?.let {
            runCatching { windows?.removeView(it) }
            AgentLog.i(TAG, "device ID label removed")
        }
        view = null
        showing = null
    }

    /** Take the label away, whatever state it is in. */
    fun remove(context: Context) = main.post { removeOnMainThread(context.applicationContext) }

    private const val TAG = "DeviceIdOverlay"
}
