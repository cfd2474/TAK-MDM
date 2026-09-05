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

import com.taksolutions.atlasmdm.policy.DataUsagePlan.Metric
import com.taksolutions.atlasmdm.policy.DataUsagePlan.Period
import com.taksolutions.atlasmdm.policy.DataUsagePlan.Rule
import java.util.Calendar
import java.util.TimeZone
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class DataUsagePlanTest {

    private val utc = TimeZone.getTimeZone("UTC")

    /** Epoch millis for a UTC wall-clock time, so the assertions read as dates. */
    private fun at(
        year: Int, month: Int, day: Int, hour: Int = 0, minute: Int = 0,
    ): Long = Calendar.getInstance(utc).apply {
        clear()
        set(year, month - 1, day, hour, minute, 0)
    }.timeInMillis

    // ----------------------------------------------------------------------- //
    // Windows
    // ----------------------------------------------------------------------- //

    @Test
    fun `a daily window runs midnight to midnight by default`() {
        val w = DataUsagePlan.windowFor(Period.DAILY, at(2026, 9, 5, 14, 30), zone = utc)

        assertEquals(at(2026, 9, 5), w.start)
        assertEquals(at(2026, 9, 6), w.end)
    }

    @Test
    fun `before the daily reset time, the live window is still yesterday's`() {
        // The counter resets at 10:00. At 09:00 the period that is running is the
        // one that began at 10:00 *yesterday* — reading today's would report an
        // hour of usage against a full day's allowance.
        val w = DataUsagePlan.windowFor(
            Period.DAILY, at(2026, 9, 5, 9, 0), resetDailyAt = "10:00", zone = utc
        )

        assertEquals(at(2026, 9, 4, 10, 0), w.start)
        assertEquals(at(2026, 9, 5, 10, 0), w.end)
    }

    @Test
    fun `after the daily reset time, the window is today's`() {
        val w = DataUsagePlan.windowFor(
            Period.DAILY, at(2026, 9, 5, 11, 0), resetDailyAt = "10:00", zone = utc
        )

        assertEquals(at(2026, 9, 5, 10, 0), w.start)
        assertEquals(at(2026, 9, 6, 10, 0), w.end)
    }

    @Test
    fun `a monthly window starts on the configured billing day`() {
        val w = DataUsagePlan.windowFor(
            Period.MONTHLY, at(2026, 9, 20), resetMonthlyOnDay = 15, zone = utc
        )

        assertEquals(at(2026, 9, 15), w.start)
        assertEquals(at(2026, 10, 15), w.end)
    }

    @Test
    fun `before the billing day, the live month is the previous one`() {
        val w = DataUsagePlan.windowFor(
            Period.MONTHLY, at(2026, 9, 3), resetMonthlyOnDay = 15, zone = utc
        )

        assertEquals(at(2026, 8, 15), w.start)
        assertEquals(at(2026, 9, 15), w.end)
    }

    @Test
    fun `a monthly window crossing February still lands on a real date`() {
        // The server caps the billing day at 28 for exactly this reason; the agent
        // coerces too, so a hand-written desired state cannot produce a window that
        // skips a month.
        val w = DataUsagePlan.windowFor(
            Period.MONTHLY, at(2026, 3, 10), resetMonthlyOnDay = 31, zone = utc
        )

        assertEquals(at(2026, 2, 28), w.start)
        assertEquals(at(2026, 3, 28), w.end)
    }

    @Test
    fun `a malformed reset time falls back to midnight rather than throwing`() {
        // Desired state comes off the wire; a bad value must not take the whole
        // reconcile down with it.
        for (bad in listOf("", "nonsense", "25:00", "10:99", "10", "10:00:00")) {
            val w = DataUsagePlan.windowFor(
                Period.DAILY, at(2026, 9, 5, 14, 0), resetDailyAt = bad, zone = utc
            )
            assertEquals("fallback for '$bad'", at(2026, 9, 5), w.start)
        }
    }

    @Test
    fun `windows are half-open so a byte is never counted twice`() {
        val first = DataUsagePlan.windowFor(Period.DAILY, at(2026, 9, 5, 12, 0), zone = utc)
        val second = DataUsagePlan.windowFor(Period.DAILY, at(2026, 9, 6, 12, 0), zone = utc)

        assertEquals(first.end, second.start)
    }

    // ----------------------------------------------------------------------- //
    // Thresholds
    // ----------------------------------------------------------------------- //

    private fun rule(mb: Long, pkg: String? = null) =
        Rule(Period.MONTHLY, Metric.MOBILE_DATA, mb, pkg)

    @Test
    fun `a threshold trips at or above the limit`() {
        val r = rule(500)

        assertFalse(DataUsagePlan.isCrossed(r, 499 * DataUsagePlan.BYTES_PER_MB))
        assertTrue(DataUsagePlan.isCrossed(r, 500 * DataUsagePlan.BYTES_PER_MB))
        assertTrue(DataUsagePlan.isCrossed(r, 900 * DataUsagePlan.BYTES_PER_MB))
    }

    @Test
    fun `MB means mebibytes, matching what Android's own usage screen shows`() {
        // A "500 MB" cap that fired at 477 MB by the platform's own reckoning would
        // look like a bug to whoever is holding the device.
        assertEquals(1024L * 1024L, DataUsagePlan.BYTES_PER_MB)
    }

    // ----------------------------------------------------------------------- //
    // Warn once per window
    // ----------------------------------------------------------------------- //

    @Test
    fun `the same rule in the same window keeps one key`() {
        val w = DataUsagePlan.windowFor(Period.MONTHLY, at(2026, 9, 20), zone = utc)

        assertEquals(
            DataUsagePlan.notifiedKey(rule(500), w),
            DataUsagePlan.notifiedKey(rule(500), w),
        )
    }

    @Test
    fun `the next window warns again`() {
        // Without the window in the key, a device over its cap would warn once and
        // then stay silent for good.
        val september = DataUsagePlan.windowFor(Period.MONTHLY, at(2026, 9, 20), zone = utc)
        val october = DataUsagePlan.windowFor(Period.MONTHLY, at(2026, 10, 20), zone = utc)

        assertNotEquals(
            DataUsagePlan.notifiedKey(rule(500), september),
            DataUsagePlan.notifiedKey(rule(500), october),
        )
    }

    @Test
    fun `different rules do not share a key`() {
        val w = DataUsagePlan.windowFor(Period.MONTHLY, at(2026, 9, 20), zone = utc)
        val keys = setOf(
            DataUsagePlan.notifiedKey(rule(500), w),
            DataUsagePlan.notifiedKey(rule(900), w),
            DataUsagePlan.notifiedKey(rule(500, "com.atakmap.app.civ"), w),
            DataUsagePlan.notifiedKey(rule(500, "com.example.other"), w),
            DataUsagePlan.notifiedKey(
                Rule(Period.MONTHLY, Metric.WIFI_DATA, 500), w
            ),
        )

        assertEquals("each distinct rule needs its own key", 5, keys.size)
    }

    // ----------------------------------------------------------------------- //
    // Ordinals off the wire
    // ----------------------------------------------------------------------- //

    @Test
    fun `ordinals map to the server's enums, and nonsense falls back`() {
        assertEquals(Period.DAILY, DataUsagePlan.period(0))
        assertEquals(Period.MONTHLY, DataUsagePlan.period(2))
        assertEquals(Metric.MOBILE_DATA, DataUsagePlan.metric(0))
        assertEquals(Metric.TOTAL_DATA, DataUsagePlan.metric(2))

        // A future server sending an ordinal this build has never heard of must not
        // crash the reconcile; the safest reading is the common case.
        assertEquals(Period.MONTHLY, DataUsagePlan.period(99))
        assertEquals(Metric.MOBILE_DATA, DataUsagePlan.metric(-1))
    }
}
