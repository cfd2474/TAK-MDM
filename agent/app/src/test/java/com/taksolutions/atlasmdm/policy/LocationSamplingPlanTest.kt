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
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * When a device takes a position, and what it does with a backlog (W106 C2).
 *
 * The cases worth testing are the ones a tablet reaches rarely and a developer
 * never does by hand: a week out of coverage, a clock that jumped, a buffer past
 * what the server will accept in one request.
 */
class LocationSamplingPlanTest {

    private val minute = 60_000L

    // ---------------------------------------------------------------- interval

    @Test
    fun `an absent section means tracking is off`() {
        assertEquals(0, LocationSamplingPlan.intervalMinutes(null))
        assertEquals(0, LocationSamplingPlan.intervalMinutes(JSONObject()))
    }

    @Test
    fun `zero means off rather than as often as possible`() {
        val section = JSONObject().put("reporting_interval_minutes", 0)

        assertEquals(0, LocationSamplingPlan.intervalMinutes(section))
        assertFalse(LocationSamplingPlan.isDue(0L, Long.MAX_VALUE / 2, 0))
    }

    @Test
    fun `a negative interval is read as off, not as always due`() {
        // Nothing should send one, but "always due" would mean a fix every couple
        // of minutes for ever, which is a battery complaint rather than an error.
        val section = JSONObject().put("reporting_interval_minutes", -5)

        assertEquals(0, LocationSamplingPlan.intervalMinutes(section))
    }

    // ------------------------------------------------------------------ timing

    @Test
    fun `a device that has never sampled is due immediately`() {
        assertTrue(LocationSamplingPlan.isDue(lastSampleAt = 0L, now = 1_000L, intervalMinutes = 5))
    }

    @Test
    fun `not due until the interval has actually elapsed`() {
        val last = 1_000_000L

        assertFalse(LocationSamplingPlan.isDue(last, last + 4 * minute, 5))
        assertTrue(LocationSamplingPlan.isDue(last, last + 5 * minute, 5))
    }

    @Test
    fun `a clock that went backwards does not disable tracking until it catches up`() {
        // ⚠️ An NTP correction, or a user setting the date. Read naively as
        // "elapsed is negative, so not yet", the device would stop reporting for
        // as long as the jump lasted and nothing would say why.
        val last = 5_000_000L
        val now = last - 60 * minute

        assertTrue(LocationSamplingPlan.isDue(last, now, 5))
    }

    // ------------------------------------------------------------------ buffer

    @Test
    fun `points are kept in the order they were recorded`() {
        var buffer = listOf<String>()
        buffer = LocationSamplingPlan.buffered(buffer, "first")
        buffer = LocationSamplingPlan.buffered(buffer, "second")
        buffer = LocationSamplingPlan.buffered(buffer, "third")

        assertEquals(listOf("first", "second", "third"), buffer)
    }

    @Test
    fun `a full buffer drops the oldest, keeping the recent end of the track`() {
        val full = (1..LocationSamplingPlan.MAX_BUFFERED).map { "point-$it" }

        val after = LocationSamplingPlan.buffered(full, "newest")

        assertEquals(LocationSamplingPlan.MAX_BUFFERED, after.size)
        assertEquals("point-2", after.first())
        assertEquals("newest", after.last())
    }

    @Test
    fun `overflow is counted so it can be logged rather than lost quietly`() {
        assertEquals(0, LocationSamplingPlan.overflowCount(0))
        assertEquals(0, LocationSamplingPlan.overflowCount(LocationSamplingPlan.MAX_BUFFERED - 1))
        assertEquals(1, LocationSamplingPlan.overflowCount(LocationSamplingPlan.MAX_BUFFERED))
    }

    // ------------------------------------------------------------------ batches

    @Test
    fun `a batch never exceeds what the server will accept`() {
        // ⚠️ The server answers an oversized batch with a 422, not by trimming it.
        // Sending the whole backlog would fail every check-in rather than one.
        val backlog = (1..1_500).map { "point-$it" }

        val batch = LocationSamplingPlan.nextBatch(backlog)

        assertEquals(LocationSamplingPlan.MAX_PER_CHECKIN, batch.size)
        assertTrue(batch.size <= LocationSamplingPlan.MAX_PER_CHECKIN)
    }

    @Test
    fun `a batch is the oldest points, so a track fills in order`() {
        val backlog = (1..600).map { "point-$it" }

        val batch = LocationSamplingPlan.nextBatch(backlog)

        assertEquals("point-1", batch.first())
        assertEquals("point-500", batch.last())
    }

    @Test
    fun `acceptance drops exactly what was sent, not the whole buffer`() {
        // ⚠️ Sampling runs on the same loop, so points can arrive while a check-in
        // is in flight. Clearing wholesale would discard fixes the server never
        // saw, and nothing would ever notice.
        val sent = (1..500).map { "point-$it" }
        val arrivedMeanwhile = listOf("newer-a", "newer-b")

        val remaining = LocationSamplingPlan.remaining(sent + arrivedMeanwhile, sent.size)

        assertEquals(arrivedMeanwhile, remaining)
    }

    @Test
    fun `a fully delivered buffer ends up empty`() {
        val all = listOf("a", "b", "c")

        assertEquals(emptyList<String>(), LocationSamplingPlan.remaining(all, 3))
        assertEquals(emptyList<String>(), LocationSamplingPlan.remaining(all, 99))
    }

    // ------------------------------------------------------------------- shape

    @Test
    fun `a point uses the server's field names, not the platform's`() {
        val point = LocationSamplingPlan.point(
            latitude = 39.7392,
            longitude = -104.9903,
            accuracyMetres = 12.5f,
            provider = "gps",
            fixedAtMillis = 1_757_332_800_000L,
            isoTimestamp = "2025-09-08T12:00:00Z",
        )

        assertEquals(39.7392, point.getDouble("latitude"), 0.00001)
        assertEquals(12.5, point.getDouble("accuracy_m"), 0.001)
        assertEquals("2025-09-08T12:00:00Z", point.getString("recorded_at"))
        assertEquals("gps", point.getString("provider"))
    }

    @Test
    fun `an unreported accuracy is omitted rather than sent as a number`() {
        // "The device did not say" and "accurate to 0 m" are different claims, and
        // the console shows them differently.
        val point = LocationSamplingPlan.point(
            latitude = 1.0,
            longitude = 2.0,
            accuracyMetres = null,
            provider = null,
            fixedAtMillis = 0L,
            isoTimestamp = "2026-01-01T00:00:00Z",
        )

        assertFalse(point.has("accuracy_m"))
        assertFalse(point.has("provider"))
    }

    @Test
    fun `one corrupt buffered entry does not cost the whole batch`() {
        // ⚠️ The buffer only drains on success, so a point that cannot be
        // serialised would block every point behind it permanently.
        val array = LocationSamplingPlan.toJsonArray(
            listOf("""{"latitude":1}""", "not json at all", """{"latitude":2}""")
        )

        assertEquals(2, array.length())
    }
}
