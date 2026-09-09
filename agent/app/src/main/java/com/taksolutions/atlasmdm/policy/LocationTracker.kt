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

import android.Manifest
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationManager
import android.os.Build
import androidx.core.content.ContextCompat
import com.taksolutions.atlasmdm.admin.MdmDeviceAdminReceiver
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
 * ⚠️ **Last known position, not a fresh fix** — the same decision
 * `LocateCommandHandler` already made, for the same reason. Requesting a live fix
 * can take minutes indoors, and doing that on a timer would hold a GPS session
 * open on a battery-powered tablet all day. The fix's own timestamp is reported,
 * so a stale point is visibly stale rather than quietly presented as current.
 *
 * ⚠️ **Buffered on disk, delivered on the next check-in.** A device out of
 * coverage keeps recording; it comes back with a track rather than a gap. The
 * buffer is only cleared once the server has actually accepted the batch.
 */
class LocationTracker(private val context: Context) {

    private val config: AgentConfig by lazy { AgentConfig(context) }

    private val manager: LocationManager? =
        context.getSystemService(LocationManager::class.java)

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

        val fix = lastKnown() ?: run {
            AgentLog.w(TAG, "location sample skipped: no last known position")
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
            accuracyMetres = if (fix.hasAccuracy()) fix.accuracy else null,
            provider = fix.provider,
            fixedAtMillis = fix.time,
            isoTimestamp = iso8601(fix.time),
        )
        config.pendingLocations =
            LocationSamplingPlan.buffered(config.pendingLocations, point.toString())

        AgentLog.i(
            TAG,
            "location sampled (${fix.provider}, ${(now - fix.time) / 1000}s old); " +
                "${config.pendingLocations.size} buffered"
        )

        evaluateFences(fix.latitude, fix.longitude)
    }

    /**
     * Decide which fences apply at this position, and carry out what they say.
     *
     * Runs on the fix, not on the sync: a fence has to keep working when the
     * server cannot be reached, which is the situation it mostly exists for.
     */
    private fun evaluateFences(latitude: Double, longitude: Double) {
        val raw = config.geofencesJson ?: return
        val fences = runCatching {
            GeofencePlan.parse(JSONObject().put(GeofencePlan.FENCES_KEY, JSONArray(raw)))
        }.getOrElse {
            AgentLog.w(TAG, "could not read the stored geofences: ${it.message}")
            return
        }
        if (fences.isEmpty()) return

        val actions = GeofencePlan.resolve(fences, latitude, longitude)
        config.geofenceIntervalOverride = actions.intervalOverrideMinutes
        GeofenceEnforcer(context).enforce(actions)
    }

    private fun hasPermission(): Boolean =
        ContextCompat.checkSelfPermission(
            context, Manifest.permission.ACCESS_FINE_LOCATION
        ) == PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(
                context, Manifest.permission.ACCESS_COARSE_LOCATION
            ) == PackageManager.PERMISSION_GRANTED

    /**
     * Make sure the device's master location setting is on.
     *
     * ⚠️ Without this, a perfectly permissioned agent reports nothing and no log
     * anywhere says why — the fixes simply never exist. `setLocationEnabled` is a
     * Device Owner API (API 30+); `Settings.Secure.LOCATION_MODE` is deprecated for
     * this and must not be used through `setSecureSetting` (Android reference §6).
     */
    private fun ensureLocationServicesOn(): Boolean {
        val enabled = manager?.isLocationEnabled ?: false
        if (enabled) return true

        val dpm = context.getSystemService(DevicePolicyManager::class.java) ?: return false
        val admin = ComponentName(context, MdmDeviceAdminReceiver::class.java)
        if (!dpm.isDeviceOwnerApp(context.packageName)) return false

        return runCatching {
            dpm.setLocationEnabled(admin, true)
            AgentLog.i(TAG, "location services turned on for tracking")
            manager?.isLocationEnabled ?: false
        }.getOrElse {
            AgentLog.w(TAG, "could not turn location services on: ${it.message}")
            false
        }
    }

    private fun lastKnown(): Location? {
        val providers = listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER)
        return providers.mapNotNull { provider ->
            runCatching {
                @Suppress("MissingPermission")
                manager?.getLastKnownLocation(provider)
            }.getOrNull()
        }.maxByOrNull { it.time }
    }

    companion object {
        private const val TAG = "LocationTracker"

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
