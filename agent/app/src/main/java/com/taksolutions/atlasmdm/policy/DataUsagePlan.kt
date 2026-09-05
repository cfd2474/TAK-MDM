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

import java.util.Calendar
import java.util.TimeZone

/**
 * The arithmetic behind data-usage thresholds (W44): which stretch of time counts,
 * and whether a figure has crossed a line the operator drew.
 *
 * Pure and therefore tested, because the interesting failures here are all
 * off-by-one: a monthly window that starts on the wrong day quietly measures the
 * wrong bytes, and a device would report a cap as un-crossed for a month.
 *
 * The `NetworkStatsManager` calls that supply the bytes live in `DataUsageTracker`
 * and only run on hardware.
 */
object DataUsagePlan {

    /** Mirrors the server's `UsagePeriod` ordinals. */
    enum class Period { DAILY, WEEKLY, MONTHLY }

    /** Mirrors the server's `UsageMetric` ordinals. */
    enum class Metric { MOBILE_DATA, WIFI_DATA, TOTAL_DATA }

    private val PERIODS = Period.entries
    private val METRICS = Metric.entries

    fun period(ordinal: Int): Period = PERIODS.getOrNull(ordinal) ?: Period.MONTHLY

    fun metric(ordinal: Int): Metric = METRICS.getOrNull(ordinal) ?: Metric.MOBILE_DATA

    /** A rule as the desired state carries it. */
    data class Rule(
        val period: Period,
        val metric: Metric,
        val thresholdMb: Long,
        /** Null for a device-wide rule; a package name for a per-app one. */
        val packageName: String? = null,
    )

    /** Half-open `[start, end)` in epoch millis — what a query should cover. */
    data class Window(val start: Long, val end: Long)

    /**
     * The accounting window containing [now] for [period].
     *
     * @param resetDailyAt "HH:mm" local time the daily counter restarts, or null
     *   for midnight.
     * @param resetMonthlyOnDay day of month the billing cycle restarts (1-28), or
     *   null for the 1st. The server caps this at 28 so the day exists in every
     *   month — a cycle pinned to the 31st would skip February entirely and the
     *   counter would never reset.
     */
    fun windowFor(
        period: Period,
        now: Long,
        resetDailyAt: String? = null,
        resetMonthlyOnDay: Int? = null,
        zone: TimeZone = TimeZone.getDefault(),
    ): Window {
        val (resetHour, resetMinute) = parseTimeOfDay(resetDailyAt)

        val start = Calendar.getInstance(zone).apply {
            timeInMillis = now
            set(Calendar.HOUR_OF_DAY, resetHour)
            set(Calendar.MINUTE, resetMinute)
            set(Calendar.SECOND, 0)
            set(Calendar.MILLISECOND, 0)

            when (period) {
                Period.DAILY -> {
                    // Before today's reset time, the live window is yesterday's.
                    if (timeInMillis > now) add(Calendar.DAY_OF_MONTH, -1)
                }

                Period.WEEKLY -> {
                    set(Calendar.DAY_OF_WEEK, firstDayOfWeek)
                    if (timeInMillis > now) add(Calendar.WEEK_OF_YEAR, -1)
                }

                Period.MONTHLY -> {
                    set(Calendar.DAY_OF_MONTH, (resetMonthlyOnDay ?: 1).coerceIn(1, 28))
                    if (timeInMillis > now) add(Calendar.MONTH, -1)
                }
            }
        }

        val end = (start.clone() as Calendar).apply {
            when (period) {
                Period.DAILY -> add(Calendar.DAY_OF_MONTH, 1)
                Period.WEEKLY -> add(Calendar.WEEK_OF_YEAR, 1)
                Period.MONTHLY -> add(Calendar.MONTH, 1)
            }
        }

        return Window(start.timeInMillis, end.timeInMillis)
    }

    /** True once [usedBytes] has passed the rule's threshold. */
    fun isCrossed(rule: Rule, usedBytes: Long): Boolean =
        usedBytes >= rule.thresholdMb * BYTES_PER_MB

    /**
     * A key identifying "this rule, in this window", stable across syncs.
     *
     * The agent records the keys it has already warned about, so a device sitting
     * over its limit for three weeks produces **one** notification rather than one
     * every fifteen minutes. Including the window start is what makes the next
     * period warn again rather than staying silent forever.
     */
    fun notifiedKey(rule: Rule, window: Window): String =
        listOf(
            rule.packageName ?: "device",
            rule.period.name,
            rule.metric.name,
            rule.thresholdMb.toString(),
            window.start.toString(),
        ).joinToString("|")

    /** MB with one decimal, for a notification an operator's user has to read. */
    fun formatMb(bytes: Long): String =
        String.format(java.util.Locale.US, "%.1f MB", bytes.toDouble() / BYTES_PER_MB)

    private fun parseTimeOfDay(value: String?): Pair<Int, Int> {
        val parts = value?.split(":")?.takeIf { it.size == 2 } ?: return 0 to 0
        val hour = parts[0].toIntOrNull()?.takeIf { it in 0..23 } ?: return 0 to 0
        val minute = parts[1].toIntOrNull()?.takeIf { it in 0..59 } ?: return 0 to 0
        return hour to minute
    }

    // Mebibytes, matching how Android's own Settings reports data usage. A
    // threshold an operator sets as "500 MB" should trip where the platform's own
    // usage screen says 500 MB, not 24 MB earlier.
    const val BYTES_PER_MB: Long = 1024L * 1024L
}
