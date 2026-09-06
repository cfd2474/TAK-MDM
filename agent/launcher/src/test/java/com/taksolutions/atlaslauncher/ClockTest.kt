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
import org.junit.Assert.assertNotEquals
import org.junit.Test
import java.time.Instant
import java.time.ZoneId

class ClockTest {

    /** 2026-09-06 14:15:30 UTC. Chosen so the zone offset is visible in the result. */
    private val instant = Instant.parse("2026-09-06T14:15:30Z")

    /** UTC-04:00 in September, so a Zulu bug shows as a four-hour error. */
    private val newYork = ZoneId.of("America/New_York")

    @Test
    fun `the local row is the device zone, 24-hour, with separators`() {
        assertEquals("10:15:30", Clock.local(instant, newYork))
        assertEquals("23:15:30", Clock.local(instant, ZoneId.of("Asia/Tokyo")))
    }

    /**
     * The bug this guards against: showing the device's own time on the Zulu row.
     * Four hours wrong and confidently marked as the shared reference is worse
     * than no Zulu row at all, because someone would act on it.
     */
    @Test
    fun `the zulu row is UTC whatever the device zone is`() {
        assertEquals("141530Z", Clock.zulu(instant))
    }

    @Test
    fun `the two rows differ by the offset, so a mix-up is visible`() {
        // Not a tautology: if `zulu` ever read the device zone, these would be
        // equal for every device, and the test would be the only thing that saw
        // it — the screen would just show the same time twice.
        assertNotEquals(
            Clock.local(instant, newYork).replace(":", ""),
            Clock.zulu(instant).dropLast(1),
        )
    }

    @Test
    fun `zulu keeps the TAK form - no separators, trailing Z`() {
        val text = Clock.zulu(instant)
        assertEquals(7, text.length)
        assertEquals('Z', text.last())
        assertEquals(true, text.dropLast(1).all { it.isDigit() })
    }

    @Test
    fun `local uses a 24-hour clock, never AM or PM`() {
        val evening = Instant.parse("2026-09-06T23:45:00Z")
        assertEquals("19:45:00", Clock.local(evening, newYork))
    }

    @Test
    fun `midnight is zero-padded on both rows, not blank`() {
        val justAfterMidnight = Instant.parse("2026-09-06T00:05:00Z")
        assertEquals("000500Z", Clock.zulu(justAfterMidnight))
        assertEquals("00:05:00", Clock.local(justAfterMidnight, ZoneId.of("UTC")))
    }
}
