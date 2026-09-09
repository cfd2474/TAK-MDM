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

import org.json.JSONArray
import org.json.JSONObject

/**
 * When to take a position, and what the buffer holds afterwards (W106).
 *
 * Pure, and deliberately so: every decision here is arithmetic over a clock and a
 * list, and none of it needs Android. That is what makes the awkward cases —
 * a clock that went backwards, a week-long outage, a buffer larger than the server
 * will accept in one request — testable on the JVM rather than only on a tablet
 * that has been offline for a week.
 */
object LocationSamplingPlan {

    /** Policy key. `0` means tracking is off; absent means the same thing. */
    const val INTERVAL_KEY = "reporting_interval_minutes"

    /**
     * Most points held on the device awaiting delivery.
     *
     * At five-minute reporting this is about a week offline. Beyond it the oldest
     * go first: a track is read from the recent end, and an operator looking at a
     * tablet that has just come back wants where it is now far more than where it
     * was six days ago.
     */
    const val MAX_BUFFERED = 2_000

    /**
     * Most points sent in one check-in.
     *
     * ⚠️ Must stay at or below the server's own cap, which rejects an oversized
     * batch with a 422 rather than trimming it. A device with a long backlog
     * therefore drains across several check-ins — the loop runs every couple of
     * minutes, so a week's backlog clears in minutes, not days.
     */
    const val MAX_PER_CHECKIN = 500

    /** Minutes between samples, or 0 for off. Absent or negative reads as off. */
    fun intervalMinutes(section: JSONObject?): Int {
        val raw = section?.optInt(INTERVAL_KEY, 0) ?: 0
        return if (raw > 0) raw else 0
    }

    /**
     * Is a sample due?
     *
     * ⚠️ **A clock that moved backwards must not disable tracking until it catches
     * up.** `lastSampleAt` is wall-clock time, so an NTP correction — or a user
     * setting the date — can put the last sample in the future. Treated naively as
     * "elapsed is negative, so not due yet", a device whose clock jumped forward
     * and back would stop reporting for as long as the jump lasted, silently. Any
     * negative elapsed is read as "due now, and re-anchor".
     */
    fun isDue(lastSampleAt: Long, now: Long, intervalMinutes: Int): Boolean {
        if (intervalMinutes <= 0) return false
        if (lastSampleAt <= 0L) return true
        val elapsed = now - lastSampleAt
        if (elapsed < 0L) return true
        return elapsed >= intervalMinutes * 60_000L
    }

    /**
     * The buffer after adding one point, oldest first, capped.
     *
     * Returns the list to persist. Dropping happens at the front, and the caller
     * logs it: silently losing the start of a long outage is the sort of thing
     * that is noticed months later when someone asks where a device was.
     */
    fun buffered(existing: List<String>, addition: String): List<String> {
        val grown = existing + addition
        return if (grown.size <= MAX_BUFFERED) grown else grown.takeLast(MAX_BUFFERED)
    }

    /** How many points a buffer of this size would discard when one is added. */
    fun overflowCount(existingSize: Int): Int =
        maxOf(0, existingSize + 1 - MAX_BUFFERED)

    /**
     * The next batch to send: oldest first, never more than the server accepts.
     *
     * Oldest first so a track fills in order rather than arriving inside out, and
     * so a device that never fully drains still delivers a continuous history
     * rather than a scattering of recent points.
     */
    fun nextBatch(buffered: List<String>): List<String> =
        buffered.take(MAX_PER_CHECKIN)

    /**
     * What remains buffered once a batch has been *accepted*.
     *
     * ⚠️ Keyed off what was sent, not "empty". The check-in that carried the batch
     * can be answered long after sampling added more points to the buffer, and
     * clearing it wholesale would throw away fixes the server never saw.
     */
    fun remaining(buffered: List<String>, sent: Int): List<String> =
        if (sent >= buffered.size) emptyList() else buffered.drop(sent)

    /**
     * One point, in the shape the check-in schema reads.
     *
     * ⚠️ The names here are the *server's*, not the platform's. `Location` calls
     * these `accuracy` and `time`, and the `locate` command reports them as
     * `accuracy_metres` / `fixed_at_millis`; the check-in wants `accuracy_m` and an
     * ISO-8601 `recorded_at`. Three vocabularies for one fix, so the translation
     * is done once, here, rather than at each call site.
     */
    fun point(
        latitude: Double,
        longitude: Double,
        accuracyMetres: Float?,
        provider: String?,
        fixedAtMillis: Long,
        isoTimestamp: String,
    ): JSONObject = JSONObject()
        .put("latitude", latitude)
        .put("longitude", longitude)
        .apply {
            // Absent means "the device did not say", which the console shows
            // differently from a reported accuracy. Never send a stand-in number.
            if (accuracyMetres != null) put("accuracy_m", accuracyMetres.toDouble())
            if (!provider.isNullOrBlank()) put("provider", provider)
        }
        .put("recorded_at", isoTimestamp)

    /** The buffered strings as a JSON array, for the check-in body. */
    fun toJsonArray(points: List<String>): JSONArray {
        val array = JSONArray()
        for (raw in points) {
            // A single unparseable entry must not cost the whole batch: it would
            // block every point behind it for ever, since the buffer only drains
            // on success.
            runCatching { array.put(JSONObject(raw)) }
        }
        return array
    }
}
