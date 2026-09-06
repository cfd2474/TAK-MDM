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

import org.junit.Assert.assertEquals
import org.junit.Test

class FilteringTest {

    /** The one field matching looks at; no Android object needs constructing. */
    private data class Tile(override val label: String) : Filtering.Searchable

    private val apps = listOf(
        Tile("ATAK"), Tile("Map Tools"), Tile("Bloomap"), Tile("Field Notes"),
    )

    private fun search(q: String?) = Filtering.matching(apps, q).map { it.label }

    @Test
    fun `an empty query shows everything, not nothing`() {
        assertEquals(apps.map { it.label }, search(""))
        assertEquals(apps.map { it.label }, search("   "))
        assertEquals(apps.map { it.label }, search(null))
    }

    /**
     * The rule worth having a test for: "map" means the user is looking for
     * something *called* Map, not for anything with those letters buried in it.
     */
    @Test
    fun `matching is on word starts, not anywhere in the label`() {
        assertEquals(listOf("Map Tools"), search("map"))
    }

    @Test
    fun `a later word counts as a start`() {
        assertEquals(listOf("Map Tools"), search("tools"))
        assertEquals(listOf("Field Notes"), search("notes"))
    }

    @Test
    fun `case does not matter`() {
        assertEquals(listOf("ATAK"), search("atak"))
        assertEquals(listOf("ATAK"), search("AtAk"))
    }

    /**
     * The counter-example that removed package matching: both `com.atakmap` and
     * `com.example.bloomap` contain "map", so searching packages would have
     * undone the word-prefix rule above on the very first realistic query.
     */
    @Test
    fun `a package name is not searched`() {
        assertEquals(emptyList<String>(), search("com.example"))
        assertEquals(listOf("Map Tools"), search("map"))
    }

    @Test
    fun `no match is an empty list, not everything`() {
        assertEquals(emptyList<String>(), search("zzz"))
    }

    @Test
    fun `the configured order survives filtering`() {
        // Its own list: the shared one has no query matching two apps, and a test
        // about ordering needs at least two.
        val ordered = listOf(Tile("Map Tools"), Tile("ATAK"), Tile("Map Overlay"))
        assertEquals(
            listOf("Map Tools", "Map Overlay"),
            Filtering.matching(ordered, "map").map { it.label },
        )
    }
}
