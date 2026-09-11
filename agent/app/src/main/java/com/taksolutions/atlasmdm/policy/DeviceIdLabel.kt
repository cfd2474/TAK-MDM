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

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Typeface
import java.io.File

/**
 * Draws the device's operator-assigned name over the wallpaper (W129).
 *
 * ⚠️ **Composed here rather than on the server, and that is not an
 * optimisation.** Wallpapers live in a content-addressed store: one file, one
 * sha256, fetched by every device that needs it. Burning a per-device name into
 * the image would turn one shared artifact into one artifact per device, each
 * downloaded separately. The name is already on the device — the server echoes
 * it on every check-in — so the only thing that has to travel is a boolean.
 *
 * ⚠️ **The base is never the wallpaper currently on screen.** Reading the live
 * wallpaper and drawing on it would stack a label every reconcile, each pass
 * drawing over the last until the screen was a pile of names. The base is the
 * policy image, or a plain background when the policy names none.
 *
 * ⚠️ **Sized as a fraction of the image, not in fixed points.** A 26sp label is
 * legible on a phone held at arm's length and invisible on a tablet across a
 * store room, which is the job this exists for.
 */
object DeviceIdLabel {

    /** Cap height as a fraction of the shorter edge. Tuned to read across a room. */
    private const val TEXT_FRACTION = 0.085f

    /** Padding around the text inside its backing plate, as a fraction of the text. */
    private const val PAD_FRACTION = 0.45f

    /** How far down the image the plate sits, as a fraction of the height. */
    private const val TOP_FRACTION = 0.12f

    /** Fallback background when the policy names no image. */
    private const val BACKGROUND = 0xFF101418.toInt()

    /**
     * Render [name] onto [source], or onto a plain [width] x [height] background
     * when [source] is null. Returns the bitmap, or null if nothing could be
     * decoded — never a half-drawn image.
     */
    fun render(source: File?, name: String, width: Int, height: Int): Bitmap? {
        val base: Bitmap = when {
            source != null -> {
                // inMutable so the label can be drawn straight onto it; a decode
                // that fails returns null rather than throwing.
                val options = BitmapFactory.Options().apply { inMutable = true }
                BitmapFactory.decodeFile(source.absolutePath, options) ?: return null
            }
            width > 0 && height > 0 ->
                Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888).apply {
                    eraseColor(BACKGROUND)
                }
            else -> return null
        }

        // A decoded file may be immutable even with inMutable set — some formats
        // ignore it — so copy rather than risk an IllegalStateException on draw.
        val canvas = Bitmap.createBitmap(base.width, base.height, Bitmap.Config.ARGB_8888)
        Canvas(canvas).apply {
            drawBitmap(base, 0f, 0f, null)
            draw(this, name, base.width, base.height)
        }
        if (base !== canvas) base.recycle()
        return canvas
    }

    private fun draw(canvas: Canvas, name: String, width: Int, height: Int) {
        val shorter = minOf(width, height).toFloat()
        val text = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.WHITE
            typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
            textSize = shorter * TEXT_FRACTION
            textAlign = Paint.Align.CENTER
        }

        // ⚠️ Shrink to fit rather than truncate. A name clipped to "Field Tab…"
        // is a worse identifier than a smaller one that reads in full, and the
        // whole point is telling two tablets apart.
        val maxWidth = width * 0.9f
        while (text.measureText(name) > maxWidth && text.textSize > 8f) {
            text.textSize -= 2f
        }

        val metrics = text.fontMetrics
        val textHeight = metrics.descent - metrics.ascent
        val pad = textHeight * PAD_FRACTION
        val centreX = width / 2f
        val plateTop = height * TOP_FRACTION
        val plate = RectF(
            centreX - text.measureText(name) / 2f - pad,
            plateTop,
            centreX + text.measureText(name) / 2f + pad,
            plateTop + textHeight + pad,
        )

        // ⚠️ A backing plate, not a drop shadow. The image underneath is an
        // operator's photograph and may be white, busy, or both; a translucent
        // plate is the only treatment that reads on all of them.
        canvas.drawRoundRect(
            plate,
            pad * 0.6f,
            pad * 0.6f,
            Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xB3000000.toInt() },
        )
        canvas.drawText(name, centreX, plate.top + pad / 2f - metrics.ascent, text)
    }
}
