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
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Which position to believe (W162).
 *
 * ⚠️ The case that matters most is the one an operator cannot see: the network
 * provider answers in milliseconds with a kilometre of error, GPS answers in tens
 * of seconds within metres, and an ordering that preferred *recency* would return
 * the cell-tower estimate every single time. The GPS session would still run, the
 * battery would still be spent, and the console would look exactly as wrong as it
 * did before any of this was written.
 */
class LocationFixPlanTest {

    private val now = 1_700_000_000_000L

    private fun fix(
        accuracy: Float?,
        ageSeconds: Long,
        provider: String = "gps",
    ) = LocationFixPlan.Candidate(
        latitude = 39.7392,
        longitude = -104.9903,
        accuracyMetres = accuracy,
        provider = provider,
        timeMillis = now - ageSeconds * 1000L,
    )

    // ----------------------------------------------------------------------- //
    // Choosing between providers
    // ----------------------------------------------------------------------- //

    @Test
    fun `a precise gps fix beats a newer but vague network fix`() {
        val gps = fix(accuracy = 8f, ageSeconds = 20, provider = "gps")
        val network = fix(accuracy = 1200f, ageSeconds = 0, provider = "network")

        assertEquals(gps, LocationFixPlan.best(listOf(network, gps)))
    }

    @Test
    fun `between two precise fixes the more accurate one wins`() {
        val good = fix(accuracy = 5f, ageSeconds = 10)
        val worse = fix(accuracy = 40f, ageSeconds = 0)

        assertEquals(good, LocationFixPlan.best(listOf(worse, good)))
    }

    @Test
    fun `between two equally accurate fixes the newer one wins`() {
        val older = fix(accuracy = 10f, ageSeconds = 25)
        val newer = fix(accuracy = 10f, ageSeconds = 2)

        assertEquals(newer, LocationFixPlan.best(listOf(older, newer)))
    }

    @Test
    fun `among only vague fixes the newest wins`() {
        val old = fix(accuracy = 900f, ageSeconds = 28, provider = "network")
        val recent = fix(accuracy = 2400f, ageSeconds = 1, provider = "network")

        // ⚠️ Deliberately not the "more accurate" 900 m one. Past the usable
        // radius the number describes a town rather than a position, so comparing
        // 900 m against 2 400 m is a distinction without a difference — whereas
        // being 27 seconds fresher is real.
        assertEquals(recent, LocationFixPlan.best(listOf(old, recent)))
    }

    @Test
    fun `a fix that will not state its accuracy cannot beat one that does`() {
        val unknown = fix(accuracy = null, ageSeconds = 0)
        val known = fix(accuracy = 30f, ageSeconds = 20)

        assertEquals(known, LocationFixPlan.best(listOf(unknown, known)))
    }

    @Test
    fun `an unknown accuracy is still reported when it is all there is`() {
        val unknown = fix(accuracy = null, ageSeconds = 3)

        assertEquals(unknown, LocationFixPlan.best(listOf(unknown)))
    }

    @Test
    fun `nothing in means nothing out`() {
        assertNull(LocationFixPlan.best(emptyList()))
    }

    // ----------------------------------------------------------------------- //
    // Freshness
    // ----------------------------------------------------------------------- //

    @Test
    fun `a fix inside the window is current`() {
        assertTrue(LocationFixPlan.isFresh(fix(accuracy = 10f, ageSeconds = 29), now))
    }

    @Test
    fun `a fix past the window is not`() {
        assertFalse(LocationFixPlan.isFresh(fix(accuracy = 10f, ageSeconds = 31), now))
    }

    @Test
    fun `the thirty eight minute fix that started all this is not current`() {
        assertFalse(LocationFixPlan.isFresh(fix(accuracy = 1500f, ageSeconds = 38 * 60), now))
    }

    @Test
    fun `a clock running ahead does not disqualify the device from reporting`() {
        // ⚠️ A negative age is a skewed clock, not a fix from the future. Reading
        // it as stale would mean a tablet whose clock is wrong can never report
        // its position at all — and nobody holding that tablet can see why.
        val ahead = fix(accuracy = 10f, ageSeconds = -600)

        assertTrue(LocationFixPlan.isFresh(ahead, now))
        assertEquals(0L, LocationFixPlan.ageSeconds(ahead, now))
    }

    @Test
    fun `age is reported in whole seconds`() {
        assertEquals(90L, LocationFixPlan.ageSeconds(fix(accuracy = 10f, ageSeconds = 90), now))
    }
}
