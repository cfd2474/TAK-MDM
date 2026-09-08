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
 * The dock showed one app when the policy asked for four (W95).
 *
 * ⚠️ **This reads XML from disk, which is not how these tests usually work** —
 * and that is the point. The fault was a single attribute in a layout file: the
 * dock and the grid shared `item_app_tile.xml`, whose `match_parent` width means
 * "one column" to a `GridLayoutManager` and "the whole RecyclerView" to the
 * horizontal `LinearLayoutManager` the dock uses. So the first favourite filled
 * the dock and the rest were laid out off-screen.
 *
 * Every existing test passed throughout. Nothing was lost: all four tiles were in
 * the managed configuration, parsed by `LauncherConfig`, and handed to the
 * adapter. Only the pixels were wrong, and no Kotlin-level test can see pixels.
 * Inspecting the file is the cheapest thing that could have caught it — the
 * alternative is Robolectric or an instrumented device for one attribute.
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
    fun `the dock tile is sized to its content`() {
        assertEquals(
            "a match_parent dock tile fills the dock and hides every tile after the first",
            "wrap_content",
            rootWidth(layout("item_dock_tile")),
        )
    }

    @Test
    fun `the grid tile still fills its column`() {
        // Not a copy of the dock: under a GridLayoutManager match_parent is
        // exactly one column, and wrap_content here would leave the grid ragged.
        assertEquals("match_parent", rootWidth(layout("item_app_tile")))
    }

    @Test
    fun `both tiles carry the views the adapter binds`() {
        // The adapter now inflates one of two files and calls findViewById on the
        // result, so a missing id in either is a crash at bind time.
        for (name in listOf("item_app_tile", "item_dock_tile")) {
            val xml = layout(name)
            assertTrue("$name has no @+id/icon", xml.contains("@+id/icon"))
            assertTrue("$name has no @+id/label", xml.contains("@+id/label"))
        }
    }
}
