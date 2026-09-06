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
 * Matching a typed query against the tiles (W68, Chunk 2).
 *
 * Its own file, and pure, because search is the one part of the home screen with
 * a rule worth arguing about — and the argument is easier to settle with tests
 * than by typing on a tablet.
 */
object Filtering {

    /**
     * The one thing matching looks at.
     *
     * Narrower than [AppEntry] on purpose: a filter has no business touching an
     * icon or an `Intent`, and depending on only the label keeps the rule
     * testable without constructing Android objects.
     */
    interface Searchable {
        val label: String
    }

    /**
     * The tiles [query] should leave visible, in their configured order.
     *
     * ⚠️ Matches a **word prefix** of the label, not a substring. "map" finding
     * "Bloomap" is noise; "map" finding "Map Tools" is what the user meant.
     *
     * ⚠️ Package names are deliberately **not** searched. They read as a free
     * extra until you notice that `com.atakmap.app.civ` and
     * `com.example.bloomap` both contain "map", so every package match undoes the
     * word-prefix rule beside it. The person who searches by package is an
     * operator, and an operator is at the console, not at the kiosk.
     *
     * An empty or blank query is everything, not nothing: a search box the user
     * has tapped but not typed in must not empty the screen.
     */
    fun <T : Searchable> matching(entries: List<T>, query: String?): List<T> {
        val needle = query?.trim()?.lowercase().orEmpty()
        if (needle.isEmpty()) return entries
        return entries.filter { entry -> matches(entry.label, needle) }
    }

    private fun matches(label: String, needle: String): Boolean {
        val lower = label.lowercase()
        if (lower.startsWith(needle)) return true
        // Any word after a separator counts as a start, so "tools" finds
        // "Map-Tools" and "ATAK Tools" alike.
        var i = 0
        while (i < lower.length) {
            val c = lower[i]
            if (!c.isLetterOrDigit()) {
                if (lower.startsWith(needle, i + 1)) return true
            }
            i++
        }
        return false
    }
}
