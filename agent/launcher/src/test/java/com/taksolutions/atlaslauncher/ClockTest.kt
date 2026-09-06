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
import java.time.Instant
import java.time.ZoneId

class ClockTest {

    /** 2026-09-06 14:15:30 UTC. Chosen so the zone offset is visible in the result. */
    private val instant = Instant.parse("2026-09-06T14:15:30Z")

    /** UTC-04:00 in September, so a Zulu bug shows as a four-hour error. */
    private val newYork = ZoneId.of("America/New_York")

    @Test
    fun `zulu is UTC whatever the device zone is`() {
        assertEquals("141530Z", Clock.format(instant, zulu = true, zone = newYork))
        assertEquals("141530Z", Clock.format(instant, zulu = true, zone = ZoneId.of("Asia/Tokyo")))
    }

    /**
     * The bug this guards against: reading the device zone and *labelling* it Z.
     * Four hours wrong and confidently marked as the shared reference is worse
     * than an unlabelled clock, because someone would act on it.
     */
    @Test
    fun `local time is the device zone and is not labelled Z`() {
        assertEquals("10:15:30", Clock.format(instant, zulu = false, zone = newYork))
        assertEquals("23:15:30", Clock.format(instant, zulu = false, zone = ZoneId.of("Asia/Tokyo")))
    }

    @Test
    fun `zulu is the TAK form - no separators, trailing Z`() {
        val text = Clock.format(instant, zulu = true, zone = ZoneId.of("UTC"))
        assertEquals(7, text.length)
        assertEquals('Z', text.last())
        assertEquals(true, text.dropLast(1).all { it.isDigit() })
    }

    @Test
    fun `midnight is zero-padded, not blank`() {
        assertEquals(
            "000500Z",
            Clock.format(Instant.parse("2026-09-06T00:05:00Z"), zulu = true, zone = newYork),
        )
    }
}
