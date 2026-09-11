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

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class CustomizationsPlanTest {

    @Test
    fun `a message comes back as written`() {
        val spec = JSONObject().put("lock_screen_message", "Property of 3rd Bde.")
        assertEquals("Property of 3rd Bde.", CustomizationsPlan.message(spec, "lock_screen_message"))
    }

    @Test
    fun `a missing key is null, so the applier clears the field`() {
        // The whole section is absent when no policy sets one, and these setters
        // latch — so "no key" has to mean "clear it", not "skip it".
        assertNull(CustomizationsPlan.message(JSONObject(), "lock_screen_message"))
    }

    @Test
    fun `an explicit JSON null does not become the literal word null`() {
        // JSONObject.optString returns the literal "null" here. Unguarded, that
        // paints the word null across the lock screen of every device it reaches.
        val spec = JSONObject().put("lock_screen_message", JSONObject.NULL)
        assertNull(CustomizationsPlan.message(spec, "lock_screen_message"))
    }

    @Test
    fun `empty and whitespace both collapse to null`() {
        // Android treats these two differently — empty hands the lock screen field
        // back to the user, whitespace holds it blank and keeps them locked out of
        // it. An operator who cleared a box means the former either way.
        assertNull(CustomizationsPlan.message(JSONObject().put("k", ""), "k"))
        assertNull(CustomizationsPlan.message(JSONObject().put("k", "   "), "k"))
        assertNull(CustomizationsPlan.message(JSONObject().put("k", "\n\t "), "k"))
    }

    @Test
    fun `internal whitespace and newlines are preserved`() {
        // Only wholly-blank collapses. A support message is prose and may be
        // multi-line; trimming it would silently rewrite what the operator typed.
        val spec = JSONObject().put("k", "Line one.\nLine two.")
        assertEquals("Line one.\nLine two.", CustomizationsPlan.message(spec, "k"))
    }

    // ----------------------------------------------------------------------- //
    // {device} substitution (W134)
    // ----------------------------------------------------------------------- //

    @Test
    fun `the device token is replaced with the name`() {
        val spec = JSONObject().put("lock_screen_message", "Property of 3rd Bde — {device}")
        assertEquals(
            "Property of 3rd Bde — TEST TAB",
            CustomizationsPlan.message(spec, "lock_screen_message", "TEST TAB"),
        )
    }

    @Test
    fun `the token can appear more than once`() {
        val spec = JSONObject().put("lock_screen_message", "{device} — return to depot — {device}")
        assertEquals(
            "R5GL40MMHRN — return to depot — R5GL40MMHRN",
            CustomizationsPlan.message(spec, "lock_screen_message", "R5GL40MMHRN"),
        )
    }

    @Test
    fun `a message without the token is untouched`() {
        val spec = JSONObject().put("lock_screen_message", "Property of 3rd Bde.")
        assertEquals(
            "Property of 3rd Bde.",
            CustomizationsPlan.message(spec, "lock_screen_message", "TEST TAB"),
        )
    }

    @Test
    fun `an unknown identity leaves the token alone rather than blanking it`() {
        // ⚠️ Substituting an empty string would turn "Property of {device}" into
        // "Property of ", which reads as a bug on the lock screen of a device
        // nobody has named yet. The unresolved token at least says what it is.
        val spec = JSONObject().put("lock_screen_message", "Property of {device}")
        assertEquals(
            "Property of {device}",
            CustomizationsPlan.message(spec, "lock_screen_message", null),
        )
        assertEquals(
            "Property of {device}",
            CustomizationsPlan.message(spec, "lock_screen_message", "  "),
        )
    }

    @Test
    fun `a token-only message still clears when the field is emptied`() {
        // The blank rule still governs: an operator who deletes the box has not
        // asked for a lock screen reading "{device}".
        assertNull(CustomizationsPlan.message(JSONObject().put("lock_screen_message", "  "),
            "lock_screen_message", "TEST TAB"))
    }
}
