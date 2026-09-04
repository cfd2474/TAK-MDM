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

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AllowlistPlanTest {

    private val apps = setOf("com.a", "com.b", "com.c", "com.atakmap.app.civ")
    private val agent = "com.taksolutions.atlasmdm"

    @Test
    fun `no allowlist suspends nothing and releases what we held`() {
        val d = AllowlistPlan.decide(apps, allowed = null, required = emptySet(), agent, setOf("com.b"))
        assertEquals(emptySet<String>(), d.toSuspend)
        assertEquals(setOf("com.b"), d.toUnsuspend)
        assertFalse(d.emptyAndIgnored)
    }

    @Test
    fun `empty allowlist is ignored`() {
        val d = AllowlistPlan.decide(apps, allowed = emptyList(), required = emptySet(), agent, setOf("com.b"))
        assertTrue(d.emptyAndIgnored)
        assertEquals(emptySet<String>(), d.toSuspend)
        assertEquals(setOf("com.b"), d.toUnsuspend)  // still releases prior suspensions
    }

    @Test
    fun `allowlist suspends everything not on it`() {
        val d = AllowlistPlan.decide(apps, allowed = listOf("com.a"), required = emptySet(), agent, emptySet())
        assertEquals(setOf("com.b", "com.c", "com.atakmap.app.civ"), d.toSuspend)
        assertEquals(emptySet<String>(), d.toUnsuspend)
    }

    @Test
    fun `required apps and the agent are implicitly allowed`() {
        val d = AllowlistPlan.decide(
            apps, allowed = listOf("com.a"), required = setOf("com.atakmap.app.civ"), agent, emptySet()
        )
        assertEquals(setOf("com.b", "com.c"), d.toSuspend)
    }

    @Test
    fun `adding an app to the list un-suspends it and leaves the rest`() {
        val d = AllowlistPlan.decide(
            apps, allowed = listOf("com.a", "com.b"), required = emptySet(), agent,
            previouslySuspended = setOf("com.b", "com.c", "com.atakmap.app.civ"),
        )
        assertEquals(emptySet<String>(), d.toSuspend)
        assertEquals(setOf("com.b"), d.toUnsuspend)
    }

    @Test
    fun `a package we already suspended is not re-suspended`() {
        val d = AllowlistPlan.decide(
            apps, allowed = listOf("com.a"), required = emptySet(), agent,
            previouslySuspended = setOf("com.b"),
        )
        assertEquals(setOf("com.c", "com.atakmap.app.civ"), d.toSuspend)  // not com.b again
        assertEquals(emptySet<String>(), d.toUnsuspend)
    }
}
