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

import android.content.Context
import com.taksolutions.atlasmdm.core.AgentConfig
import com.taksolutions.atlasmdm.diag.AgentLog
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/**
 * Records where the device is, on the interval a TRACKING_FENCING policy asks for
 * (W106).
 *
 * The shape follows [DataUsageTracker]: a thin shell over a pure plan, reconciled
 * unconditionally on every sync so that *removing* the policy turns tracking off
 * rather than leaving the last interval running for ever.
 *
 * ⚠️ **A real fix, requested on the interval** (W162). This used to read
 * `getLastKnownLocation`, which starts no GPS session and returns whatever some
 * other app happened to leave in the cache — so a track was only as good as the
 * device's other software, and a tablet running no mapping app produced a straight
 * line of identical stale points that looked exactly like a stationary device.
 *
 * The battery argument the old comment made is real, and is answered by bounding
 * rather than by not asking: one single-shot request per interval, capped at
 * [CurrentFix.SAMPLE_TIMEOUT_MS] and cancelled on the way out. A burst on the
 * interval, never a held session. The fix's own timestamp is still reported, so a
 * fallback to the cache is visibly stale rather than quietly presented as current.
 *
 * ⚠️ **Buffered on disk, delivered on the next check-in.** A device out of
 * coverage keeps recording; it comes back with a track rather than a gap. The
 * buffer is only cleared once the server has actually accepted the batch.
 */
class LocationTracker(private val context: Context) {

    private val config: AgentConfig by lazy { AgentConfig(context) }

    private val fixes: CurrentFix by lazy { CurrentFix(context) }

    /** Is tracking switched on for this device? */
    fun isEnabled(): Boolean = config.locationIntervalMinutes > 0

    /**
     * Apply the policy section, and return any errors worth reporting.
     *
     * Absent section means no tracking policy reaches this device, which is not
     * the same as an error — it means off.
     */
    fun reconcile(section: JSONObject?, fenceDefaultMinutes: Int = 5): List<String> {
        val tracking = LocationSamplingPlan.intervalMinutes(section)
        val fences = GeofencePlan.parse(section)

        // Remembered so fences can be evaluated on iterations with no bundle —
        // every iteration of an outage, which is when a fence most needs to work.
        config.geofencesJson = section?.optJSONArray(GeofencePlan.FENCES_KEY)?.toString()

        // ⚠️ A fence implies sampling even when tracking is off. Otherwise an
        // operator who set a fence and left the interval at 0 has configured
        // something that can never evaluate, and it reads as broken rather than
        // as unconfigured.
        val minutes = GeofencePlan.samplingInterval(
            trackingMinutes = tracking,
            overrideMinutes = config.geofenceIntervalOverride,
            hasFences = fences.isNotEmpty(),
            fenceDefaultMinutes = fenceDefaultMinutes,
        )
        val previous = config.locationIntervalMinutes

        if (minutes != previous) {
            AgentLog.i(TAG, "location reporting interval: $previous -> $minutes minute(s)")
            config.locationIntervalMinutes = minutes
        }

        if (fences.isEmpty() && config.activeGeofences.isNotEmpty()) {
            // ⚠️ The policy has stopped naming any fence, so whatever the last one
            // was doing must be undone now. Left to the sampler, a device whose
            // tracking was switched off in the same edit would never take another
            // fix, and would keep its radios held wherever the fence left them.
            GeofenceEnforcer(context).enforce(GeofencePlan.Actions())
            config.geofenceIntervalOverride = 0
        }

        if (minutes <= 0) {
            // ⚠️ Points already recorded are still delivered. Turning tracking off
            // stops new samples; it does not retract a track the operator has
            // already been told about, and dropping it here would lose points the
            // server was about to receive.
            return emptyList()
        }

        val errors = mutableListOf<String>()

        if (!hasPermission()) {
            // Worth reporting rather than silently not tracking: this is the
            // difference between "no policy" and "policy that cannot run".
            errors += "location tracking is on but location permission is not granted"
        }
        if (!ensureLocationServicesOn()) {
            errors += "location tracking is on but location services are off"
        }
        return errors
    }

    /**
     * Take a sample if the interval has elapsed.
     *
     * Called from the sync loop on every iteration, including the ones where the
     * server could not be reached — which is the whole point of buffering.
     */
    fun sampleIfDue(now: Long = System.currentTimeMillis()) {
        val minutes = config.locationIntervalMinutes
        if (!LocationSamplingPlan.isDue(config.lastLocationSampleAt, now, minutes)) return

        // Anchored whether or not a fix is obtained. Otherwise a device that
        // cannot get a position retries on every loop iteration — every couple of
        // minutes — instead of on the interval it was told.
        config.lastLocationSampleAt = now

        if (!hasPermission()) {
            AgentLog.w(TAG, "location sample skipped: permission not granted")
            return
        }

        // ⚠️ Blocks the sync loop for up to SAMPLE_TIMEOUT_MS. That is the cost of
        // a position worth having, and it is why the sample timeout is well under
        // `locate`'s: this runs unattended on every interval, and policy, commands
        // and the long-poll are all waiting behind it.
        val outcome = CurrentFix(context).request(CurrentFix.SAMPLE_TIMEOUT_MS, now)
        val fix = outcome.candidate ?: run {
            AgentLog.w(TAG, "location sample skipped: ${outcome.failure ?: "no position"}")
            return
        }

        val overflow = LocationSamplingPlan.overflowCount(config.pendingLocations.size)
        if (overflow > 0) {
            // Said out loud. Losing the start of a long outage is exactly the kind
            // of gap someone asks about months later.
            AgentLog.w(TAG, "location buffer full: dropping $overflow oldest point(s)")
        }

        val point = LocationSamplingPlan.point(
            latitude = fix.latitude,
            longitude = fix.longitude,
            accuracyMetres = fix.accuracyMetres,
            provider = fix.provider,
            fixedAtMillis = fix.timeMillis,
            isoTimestamp = iso8601(fix.timeMillis),
        )
        config.pendingLocations =
            LocationSamplingPlan.buffered(config.pendingLocations, point.toString())

        // ⚠️ The age is the thing to read in this line, not the coordinates. A
        // run of samples a second or two old is a live GPS session; ages that climb
        // steadily are the cache being re-reported, which is the W162 bug
        // returning.
        AgentLog.i(
            TAG,
            "location sampled (${fix.provider}, " +
                "${LocationFixPlan.ageSeconds(fix, now)}s old, " +
                "${if (outcome.live) "live" else "cached"}); " +
                "${config.pendingLocations.size} buffered"
        )

        evaluateFences(fix.latitude, fix.longitude, now - fix.timeMillis)
    }

    /**
     * Decide which fences apply at this position, and carry out what they say.
     *
     * Runs on the fix, not on the sync: a fence has to keep working when the
     * server cannot be reached, which is the situation it mostly exists for.
     */
    private fun evaluateFences(latitude: Double, longitude: Double, fixAgeMillis: Long) {
        val raw = config.geofencesJson ?: return
        val fences = runCatching {
            GeofencePlan.parse(JSONObject().put(GeofencePlan.FENCES_KEY, JSONArray(raw)))
        }.getOrElse {
            AgentLog.w(TAG, "could not read the stored geofences: ${it.message}")
            return
        }
        if (fences.isEmpty()) return

        var actions = GeofencePlan.resolve(fences, latitude, longitude)

        // ⚠️ **A stale fix is treated as outside a trusted area.**
        //
        // Every other fence action is safe to hold on an old position — a radio
        // stays off and the worst case is an inconvenience. Suspending the
        // passcode is not: a device that lost GPS indoors, or was carried out of
        // the zone in a bag, would sit unlocked on the strength of a fix from
        // hours ago, and nothing would look wrong from the console.
        //
        // So if the device's position cannot be confirmed *now*, the passcode
        // comes back. The cost is a tablet that occasionally relocks when it need
        // not; the alternative is one unlocked somewhere nobody can place.
        if (actions.lock == GeofencePlan.Lock.OFF && fixAgeMillis > TRUSTED_FIX_MAX_AGE_MS) {
            AgentLog.w(
                TAG,
                "trusted area not honoured: the position is ${fixAgeMillis / 60_000} " +
                    "minutes old, so the passcode stays in force",
            )
            actions = actions.copy(lock = GeofencePlan.Lock.NONE)
        }

        config.geofenceIntervalOverride = actions.intervalOverrideMinutes
        GeofenceEnforcer(context).enforce(actions)
    }

    // Permission and the master location switch both live on CurrentFix now, so
    // that `locate` gets them too — it had neither, and a device with location
    // switched off in Settings answered an operator with a bare failure.
    private fun hasPermission(): Boolean = fixes.hasPermission()

    private fun ensureLocationServicesOn(): Boolean = fixes.ensureLocationServicesOn()

    companion object {
        private const val TAG = "LocationTracker"

        /**
         * How old a fix may be and still hold a trusted area open.
         *
         * ⚠️ Ten minutes, and deliberately not the reporting interval: an operator
         * may set a long interval to save battery, and that must not buy a longer
         * window in which a device sits unlocked on a position nobody has
         * confirmed.
         */
        const val TRUSTED_FIX_MAX_AGE_MS = 10 * 60 * 1000L

        /**
         * ⚠️ `Locale.US` and an explicit UTC zone, not the device's.
         *
         * A tablet set to an Arabic locale formats digits as Eastern Arabic
         * numerals, which the server cannot parse — and the failure would appear
         * only on devices configured that way, long after this shipped.
         */
        fun iso8601(millis: Long): String {
            val format = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US)
            format.timeZone = TimeZone.getTimeZone("UTC")
            return format.format(Date(millis))
        }
    }
}
