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

import com.taksolutions.atlaslauncher.LauncherConfig.AppRef
import com.taksolutions.atlaslauncher.LauncherConfig.Orientation
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The salvage rules. Every one of these is a config a device could really
 * receive, and the launcher has to draw a working screen from all of them —
 * there is nowhere for the user to go if it does not.
 */
class LauncherConfigTest {

    /** A map-backed [LauncherConfig.Companion.Source]; the device uses a Bundle. */
    private class Fake(private val values: Map<String, Any?>) :
        LauncherConfig.Companion.Source {
        override val isEmpty: Boolean get() = values.isEmpty()
        override fun int(key: String, fallback: Int): Int = values[key] as? Int ?: fallback
        override fun bool(key: String, fallback: Boolean): Boolean =
            values[key] as? Boolean ?: fallback
        override fun string(key: String): String? = values[key] as? String
        @Suppress("UNCHECKED_CAST")
        override fun bundles(key: String): List<LauncherConfig.Companion.Source>? =
            (values[key] as? List<Map<String, Any?>>)?.map(::Fake)
    }

    private fun config(vararg pairs: Pair<String, Any?>) =
        LauncherConfig.from(Fake(mapOf(*pairs)))

    /** One `bundle_array` record, as the agent will send it. */
    private fun app(pkg: String, activity: String? = null, favorite: Boolean = false) =
        mapOf("package" to pkg, "activity" to activity, "favorite" to favorite)

    @Test
    fun `no configuration at all is a working default, not a failure`() {
        val c = LauncherConfig.from(null)
        assertEquals(LauncherConfig.DEFAULT_COLUMNS, c.columns)
        assertTrue(c.apps.isEmpty())
        assertEquals(Orientation.AUTO, c.orientation)
    }

    @Test
    fun `an empty bundle is the same as none`() {
        assertEquals(LauncherConfig.from(null), config())
    }

    @Test
    fun `the operator's order is the grid's order`() {
        val c = config("apps" to listOf(app("c.pkg"), app("a.pkg"), app("b.pkg")))
        assertEquals(listOf("c.pkg", "a.pkg", "b.pkg"), c.apps.map { it.packageName })
    }

    @Test
    fun `an activity may be named, and a leading dot is expanded`() {
        val c = config("apps" to listOf(app("com.atakmap.app.civ", ".ATAKActivity")))
        assertEquals("com.atakmap.app.civ.ATAKActivity", c.apps.single().activity)
    }

    @Test
    fun `a fully qualified activity is left alone`() {
        val c = config("apps" to listOf(app("a.pkg", "com.other.Screen")))
        assertEquals("com.other.Screen", c.apps.single().activity)
    }

    @Test
    fun `records that cannot be a tile are dropped rather than drawn`() {
        val c = config(
            "apps" to listOf(
                app(""), app("   "), app("has space"), app("has/slash"), app("good.pkg"),
            ),
        )
        assertEquals(listOf("good.pkg"), c.apps.map { it.packageName })
    }

    @Test
    fun `the same component twice is one tile`() {
        val c = config("apps" to listOf(app("a.pkg"), app("a.pkg")))
        assertEquals(1, c.apps.size)
        // First wins, so the operator's first placement is the one that stands.
        assertEquals(AppRef("a.pkg"), c.apps.single())
    }

    /**
     * ⚠️ Two tiles, not one. De-duplicating on the package alone was right while
     * one app meant one tile, and wrong the moment the ATLAS agent needed two —
     * its console and its Device Settings screen are the same package, and the
     * package-level key dropped whichever came second with nothing said (W71).
     */
    @Test
    fun `two activities of one app are two tiles`() {
        val c = config("apps" to listOf(app("a.pkg"), app("a.pkg", ".Settings")))
        assertEquals(2, c.apps.size)
        assertEquals(listOf(null, "a.pkg.Settings"), c.apps.map { it.activity })
    }

    /**
     * The point of putting `favorite` on the record: there is no second list to
     * disagree with the first, so a dock tile lock task would refuse to open
     * cannot be expressed at all.
     */
    @Test
    fun `favourites are the pinned apps, in the same order`() {
        val c = config(
            "apps" to listOf(
                app("a.pkg", favorite = true),
                app("b.pkg"),
                app("c.pkg", favorite = true),
            ),
        )
        assertEquals(listOf("a.pkg", "c.pkg"), c.favorites.map { it.packageName })
    }

    @Test
    fun `a silly column count is clamped, not obeyed`() {
        assertEquals(LauncherConfig.MIN_COLUMNS, config("columns" to 0).columns)
        assertEquals(LauncherConfig.MIN_COLUMNS, config("columns" to -3).columns)
        assertEquals(LauncherConfig.MAX_COLUMNS, config("columns" to 40).columns)
        assertEquals(5, config("columns" to 5).columns)
    }

    @Test
    fun `an unknown orientation falls back rather than throwing`() {
        assertEquals(Orientation.AUTO, config("orientation" to "sideways").orientation)
    }

    @Test
    fun `orientation is read case-insensitively`() {
        assertEquals(Orientation.PORTRAIT, config("orientation" to "Portrait").orientation)
    }

}
