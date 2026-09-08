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

package com.taksolutions.atlaslauncher

import android.graphics.Rect
import android.view.View
import androidx.recyclerview.widget.RecyclerView

/**
 * Vertical breathing room between rows of app tiles (W95).
 *
 * ⚠️ **A decoration rather than padding on the tile, because the tile is shared.**
 * The grid and the dock draw the same `item_app_tile`, so vertical padding added
 * there would also make each dock tile taller and grow the bar along the bottom of
 * the screen. A decoration is attached to one RecyclerView and affects nothing
 * else.
 *
 * Half above and half below each tile, so the space *between* two rows is [gapPx]
 * and the grid's outer edge gains only half of it — a full gap at the top would
 * read as the grid having drifted away from the clock.
 */
class RowSpacing(private val gapPx: Int) : RecyclerView.ItemDecoration() {

    override fun getItemOffsets(
        outRect: Rect,
        view: View,
        parent: RecyclerView,
        state: RecyclerView.State,
    ) {
        val half = gapPx / 2
        outRect.top = half
        outRect.bottom = half
    }

    companion object {

        /**
         * How much the decoration must add so that two rows end up [gapPx] apart.
         *
         * ⚠️ **The tile's own padding is part of the gap the eye sees.** Handing
         * the decoration the full figure would space the rows by the padding too
         * much, and the resource would then be a number that means nothing you
         * could measure on the screen.
         *
         * Never negative: a tile whose padding already exceeds the wanted gap
         * cannot be squeezed by a decoration, and asking for that should leave the
         * layout alone rather than overlap the rows.
         */
        fun extraFor(gapPx: Int, tilePaddingPx: Int): Int =
            (gapPx - 2 * tilePaddingPx).coerceAtLeast(0)
    }
}
