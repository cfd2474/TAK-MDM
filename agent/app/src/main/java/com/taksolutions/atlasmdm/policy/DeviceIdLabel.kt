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
 * ⚠️ **The canvas is square, and that is the whole of the rotation fix (W131).**
 * A first version drew onto a bitmap the size of the *current* display. One
 * wallpaper bitmap serves both orientations — the system re-crops it — so a
 * label placed against portrait pixels was off-centre in landscape and, in the
 * other direction, cropped off the screen entirely. Observed on `SM-X828U`.
 *
 * 📖 `WallpaperManager.getDesiredMinimumWidth`:
 *
 * > Callers of `setBitmap` or `setStream` **should check this value beforehand**
 * > to make sure the supplied wallpaper respects the desired minimum width. If
 * > the returned value is <= 0, the caller should use the width of the default
 * > display instead.
 *
 * That minimum is routinely *wider than the screen*, so that a launcher can pan.
 * A screen-sized bitmap is therefore positioned rather than centred, which is
 * where the sideways shift came from. A square whose side satisfies every
 * minimum is symmetric: whatever the system does to it, it does the same thing
 * in both orientations.
 *
 * ⚠️ **Only the middle of that square is guaranteed to be on screen.** Filling a
 * W×H screen from an S×S bitmap crops the long axis, leaving the central
 * `min(W,H) / max(W,H)` of it visible — about 56% on a 16:9 phone. The label
 * sits inside that band, which is why it is near the middle of the picture
 * rather than at the top where it would read better and vanish on rotation.
 *
 * ⚠️ **Sized as a fraction of the image, not in fixed points.** A 26sp label is
 * legible on a phone held at arm's length and invisible on a tablet across a
 * store room, which is the job this exists for.
 */
object DeviceIdLabel {

    /** Cap height as a fraction of the square's side. Tuned to read across a room. */
    private const val TEXT_FRACTION = 0.06f

    /** Padding around the text inside its backing plate, as a fraction of the text. */
    private const val PAD_FRACTION = 0.45f

    /**
     * Where the label sits inside the guaranteed-visible band, 0 being its top
     * edge and 1 its bottom. Above the middle so it clears the dock and the
     * lock-screen clock, without leaving the band.
     */
    private const val BAND_POSITION = 0.28f

    /** Fallback background when the policy names no image. */
    private const val BACKGROUND = 0xFF101418.toInt()

    /**
     * Render [name] over [source], or over a plain background when [source] is
     * null, onto a square canvas that works in both orientations.
     *
     * [screenWidth] and [screenHeight] are the display; [desiredWidth] and
     * [desiredHeight] are what `WallpaperManager` asked for, or 0 when it
     * stated nothing. Returns null if nothing could be decoded — never a
     * half-drawn image.
     */
    fun render(
        source: File?,
        name: String,
        screenWidth: Int,
        screenHeight: Int,
        desiredWidth: Int = 0,
        desiredHeight: Int = 0,
    ): Bitmap? {
        // Square, and large enough for every minimum the system stated. Using
        // the largest of them means neither orientation has to upscale.
        val side = maxOf(screenWidth, screenHeight, desiredWidth, desiredHeight)
        if (side <= 0) return null

        val canvasBitmap = Bitmap.createBitmap(side, side, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(canvasBitmap)
        canvas.drawColor(BACKGROUND)

        if (source != null) {
            val decoded = BitmapFactory.decodeFile(source.absolutePath)
                ?: run { canvasBitmap.recycle(); return null }
            // Cover, not fit: letterboxing an operator's photograph behind bars
            // of flat colour looks like a fault rather than a choice.
            val scale = maxOf(side.toFloat() / decoded.width, side.toFloat() / decoded.height)
            val drawWidth = decoded.width * scale
            val drawHeight = decoded.height * scale
            canvas.drawBitmap(
                decoded,
                null,
                RectF(
                    (side - drawWidth) / 2f,
                    (side - drawHeight) / 2f,
                    (side + drawWidth) / 2f,
                    (side + drawHeight) / 2f,
                ),
                Paint(Paint.FILTER_BITMAP_FLAG),
            )
            decoded.recycle()
        }

        draw(canvas, name, side, visibleFraction(screenWidth, screenHeight))
        return canvasBitmap
    }

    /**
     * How much of the square survives the crop, along whichever axis is cropped.
     *
     * Filling a W×H screen from an S×S bitmap scales by `max(W,H)/S` and throws
     * away the rest, leaving `min(W,H)/max(W,H)` of the square on screen.
     */
    internal fun visibleFraction(screenWidth: Int, screenHeight: Int): Float {
        val longer = maxOf(screenWidth, screenHeight)
        if (longer <= 0) return 1f
        return minOf(screenWidth, screenHeight).toFloat() / longer
    }

    private fun draw(canvas: Canvas, name: String, side: Int, visible: Float) {
        val text = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.WHITE
            typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
            textSize = side * TEXT_FRACTION
            textAlign = Paint.Align.CENTER
        }

        // ⚠️ Shrink to fit rather than truncate. A name clipped to "Field Tab…"
        // is a worse identifier than a smaller one that reads in full, and the
        // whole point is telling two tablets apart. Measured against the band,
        // not the square, or a long name would run off the sides in the
        // narrower orientation.
        val maxWidth = side * visible * 0.9f
        while (text.measureText(name) > maxWidth && text.textSize > 8f) {
            text.textSize -= 2f
        }

        val metrics = text.fontMetrics
        val textHeight = metrics.descent - metrics.ascent
        val pad = textHeight * PAD_FRACTION
        val centreX = side / 2f

        // The band both orientations can see, and a position inside it.
        val bandTop = side * (1f - visible) / 2f
        val bandHeight = side * visible
        val plateTop = bandTop + bandHeight * BAND_POSITION

        val halfText = text.measureText(name) / 2f
        val plate = RectF(
            centreX - halfText - pad,
            plateTop,
            centreX + halfText + pad,
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
