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

import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The tile layout, and the dock that took two goes to get right (W95).
 *
 * ⚠️ **This reads XML from disk, which is not how these tests usually work** —
 * and that is the point. Both dock faults were invisible to Kotlin: the tiles were
 * always in the config, always parsed, always handed to the adapter. First only
 * one could be seen, then all four could be seen bunched in a corner. Nothing was
 * lost either time, so nothing was logged either time.
 *
 * `match_parent` is correct here **because both RecyclerViews are grids**. It
 * means "fill one cell" to a `GridLayoutManager`. Under the horizontal
 * `LinearLayoutManager` the dock used to have, it meant the whole view — which is
 * what hid the other three tiles. The width and the layout manager are one
 * decision in two files, so this test names the pairing.
 */
class TileLayoutTest {

    private fun layout(name: String): String {
        val file = File("src/main/res/layout/$name.xml")
        assertTrue("expected to find $name.xml at ${file.absolutePath}", file.exists())
        return file.readText()
    }

    /** The width of the layout's **root** element, which is the one the manager reads. */
    private fun rootWidth(xml: String): String {
        val root = xml.indexOf("<LinearLayout")
        assertTrue("no root LinearLayout", root >= 0)
        val head = xml.substring(root, xml.indexOf('>', root))
        return Regex("""android:layout_width="([^"]+)"""").find(head)!!.groupValues[1]
    }

    @Test
    fun `the tile fills its cell`() {
        assertEquals(
            "match_parent is one cell under a grid — and the whole view under a " +
                "horizontal linear manager, which is how the dock lost three tiles",
            "match_parent",
            rootWidth(layout("item_app_tile")),
        )
    }

    @Test
    fun `the tile centres what it draws`() {
        // With one column per docked app, the centring is what makes the dock read
        // as evenly spaced rather than as icons stuck to the left of each cell.
        assertTrue(layout("item_app_tile").contains("""android:gravity="center""""))
    }

    @Test
    fun `the tile carries the views the adapter binds`() {
        val xml = layout("item_app_tile")
        assertTrue("no @+id/icon", xml.contains("@+id/icon"))
        assertTrue("no @+id/label", xml.contains("@+id/label"))
    }

    @Test
    fun `the dock is one column per app, so the tiles spread across the base`() {
        assertEquals(1, DockLayout.spanFor(1))
        assertEquals(4, DockLayout.spanFor(4))
    }

    @Test
    fun `an empty dock still asks for a column`() {
        // A GridLayoutManager throws on a span count of zero, and "no favourites"
        // is an ordinary policy rather than an error.
        assertEquals(1, DockLayout.spanFor(0))
    }

    private fun dimen(name: String): Int {
        val xml = File("src/main/res/values/dimens.xml").readText()
        val found = Regex("""<dimen name="$name">(\d+)dp</dimen>""").find(xml)
        assertTrue("$name is not declared", found != null)
        return found!!.groupValues[1].toInt()
    }

    @Test
    fun `the grid gets its extra row spacing from outside the tile`() {
        // ⚠️ The point of this test is *where* the spacing lives. The dock draws
        // the same tile, so vertical padding added to the tile would grow the
        // bottom bar as well — the decoration keeps the change to the grid.
        assertTrue("row gap should be a real gap", dimen("grid_row_gap") > 0)
        assertTrue(
            "the tile takes its padding from the dimension the gap is computed against",
            layout("item_app_tile").contains("""android:padding="@dimen/tile_padding""""),
        )
    }

    @Test
    fun `the row gap resource is the gap you would measure`() {
        // ⚠️ The resource means the space between two rows, not the number handed
        // to the decoration — the tile's own padding is already part of what the
        // eye sees, and double-counting it is the easy mistake here.
        val gap = dimen("grid_row_gap")
        val padding = dimen("tile_padding")

        assertEquals(gap, RowSpacing.extraFor(gap, padding) + 2 * padding)
    }

    @Test
    fun `a gap smaller than the padding cannot pull rows together`() {
        // A decoration can only add space. Asking for less than the tile already
        // carries should leave the layout alone, not overlap the rows.
        assertEquals(0, RowSpacing.extraFor(gapPx = 8, tilePaddingPx = 8))
    }

    @Test
    fun `a very full dock wraps instead of shrinking past the icon`() {
        // Beyond this the cell is narrower than the 64dp icon in it. The dock is
        // wrap_content tall, so a second row grows it; clipping would hide apps
        // exactly as the original bug did.
        assertEquals(DockLayout.MAX_SPAN, DockLayout.spanFor(DockLayout.MAX_SPAN + 3))
    }
}
