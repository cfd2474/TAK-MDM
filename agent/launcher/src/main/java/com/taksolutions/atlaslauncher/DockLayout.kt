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

/**
 * How wide the dock's grid is (W95).
 *
 * ⚠️ **One column per docked app is what spreads them across the base.** A
 * horizontal `LinearLayoutManager` lays tiles out from the start and stops, so
 * four icons sat bunched in the bottom-left corner with the rest of the screen
 * empty. A `GridLayoutManager` whose span count equals the number of tiles gives
 * each an equal share of the width, and the tile centres its icon inside that
 * share — so the dock reads as evenly spaced whether it holds two apps or five.
 *
 * Pure and separate from the activity because it is a rule, and rules are worth
 * testing without a device.
 */
object DockLayout {

    /**
     * Above this the grid wraps to a second row instead of narrowing further. The
     * dock is `wrap_content` tall and grows; clipping the overflow would hide
     * apps exactly as the old bug did.
     *
     * Five rather than the six this started at: the operator's call, and it
     * leaves each tile wider than the icon it holds with room for a label, which
     * six only just managed on the narrowest supported screen.
     */
    const val MAX_SPAN = 5

    /** Columns for [count] docked apps. Never zero — a grid cannot have no spans. */
    fun spanFor(count: Int): Int = count.coerceIn(1, MAX_SPAN)
}
