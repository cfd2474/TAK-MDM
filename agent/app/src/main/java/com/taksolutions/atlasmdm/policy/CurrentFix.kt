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
import android.os.CancellationSignal
import androidx.core.content.ContextCompat
import com.taksolutions.atlasmdm.admin.MdmDeviceAdminReceiver
import com.taksolutions.atlasmdm.diag.AgentLog
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * Asks the device where it actually is, now (W162).
 *
 * ⚠️ **This is the thing the agent never did.** Both `locate` and the periodic
 * sampler read `getLastKnownLocation`, which starts nothing — it hands back a fix
 * some other app happened to leave in the cache. On a tablet running ATAK that
 * looks perfect; on one that is not, it returns a position from hours ago and
 * from somewhere else, and nothing in the console distinguishes the two. An
 * operator pressing **Locate** and being shown where the tablet was this morning
 * is worse served than one shown nothing.
 *
 * So this requests a real fix, and the last-known cache becomes what it should
 * always have been: the fallback, reported with its age attached.
 *
 * ⚠️ **Bounded, and never a held session.** `getCurrentLocation` is a single-shot
 * request that the platform tears down on its own, and every call here is capped
 * by the caller's timeout and a [CancellationSignal] fired in a `finally`. That is
 * the difference between a short GPS burst on an interval and the radio held open
 * all day, which is what the original design was written to avoid — and it is
 * still worth avoiding.
 */
class CurrentFix(private val context: Context) {

    private val manager: LocationManager? =
        context.getSystemService(LocationManager::class.java)

    /** What [request] found, and whether it is worth calling current. */
    data class Outcome(
        val candidate: LocationFixPlan.Candidate?,
        val live: Boolean,
        val failure: String? = null,
    ) {
        val found: Boolean get() = candidate != null
    }

    fun hasPermission(): Boolean =
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
     *
     * Lives here rather than in [LocationTracker] so that `locate` gets it too. It
     * did not have it, so a device with location switched off in Settings answered
     * the operator with a bare failure that named none of that.
     */
    fun ensureLocationServicesOn(): Boolean {
        val enabled = manager?.isLocationEnabled ?: false
        if (enabled) return true

        val dpm = context.getSystemService(DevicePolicyManager::class.java) ?: return false
        val admin = ComponentName(context, MdmDeviceAdminReceiver::class.java)
        if (!dpm.isDeviceOwnerApp(context.packageName)) return false

        return runCatching {
            dpm.setLocationEnabled(admin, true)
            AgentLog.i(TAG, "location services turned on")
            manager?.isLocationEnabled ?: false
        }.getOrElse {
            AgentLog.w(TAG, "could not turn location services on: ${it.message}")
            false
        }
    }

    /**
     * Ask every enabled provider at once, and take the best answer that arrives.
     *
     * ⚠️ **In parallel, not in order.** Asking GPS first and falling back to the
     * network on timeout would cost the full timeout indoors before producing the
     * coarse answer it could have given immediately. Asking together means the
     * network fix is already in hand while GPS is still settling, and the GPS fix
     * displaces it if it lands in time — the operator waits once, not twice.
     *
     * Returns as soon as every provider has answered, so an outdoor device with a
     * warm GPS comes back in a second or two rather than sitting out the timeout.
     */
    fun request(timeoutMs: Long, now: Long = System.currentTimeMillis()): Outcome {
        if (!hasPermission()) {
            return Outcome(null, live = false, failure = "location permission not granted")
        }
        val manager = manager
            ?: return Outcome(null, live = false, failure = "no location service")

        if (!ensureLocationServicesOn()) {
            // Not fatal on its own — a cached fix may still exist and is better
            // than nothing — but it is the reason a live request will find nothing,
            // so it is named rather than left for someone to deduce.
            AgentLog.w(TAG, "location services are off and could not be turned on")
        }

        val providers = PROVIDERS.filter { provider ->
            runCatching { manager.isProviderEnabled(provider) }.getOrDefault(false)
        }

        val found = CopyOnWriteArrayList<LocationFixPlan.Candidate>()
        if (providers.isNotEmpty()) {
            val latch = CountDownLatch(providers.size)
            val signal = CancellationSignal()
            try {
                providers.forEach { provider ->
                    runCatching {
                        @Suppress("MissingPermission")
                        manager.getCurrentLocation(
                            provider,
                            signal,
                            { runnable -> runnable.run() },
                        ) { location ->
                            // ⚠️ null is the documented answer for "could not fix
                            // in time", not an error. It still has to count down,
                            // or a single silent provider holds the whole request
                            // open for the full timeout.
                            location?.let { found += it.toCandidate() }
                            latch.countDown()
                        }
                    }.onFailure {
                        AgentLog.w(TAG, "could not ask $provider for a fix: ${it.message}")
                        latch.countDown()
                    }
                }
                latch.await(timeoutMs, TimeUnit.MILLISECONDS)
            } finally {
                // Fired whether the wait completed or timed out. A request left
                // outstanding is a GPS session nobody is waiting for.
                signal.cancel()
            }
        }

        val fresh = found.filter { LocationFixPlan.isFresh(it, now) }
        LocationFixPlan.best(fresh)?.let { fix ->
            AgentLog.i(
                TAG,
                "live fix from ${fix.provider} " +
                    "(${LocationFixPlan.ageSeconds(fix, now)}s old, " +
                    "±${fix.accuracyMetres?.toInt() ?: -1}m)",
            )
            return Outcome(fix, live = true)
        }

        // ⚠️ Nothing current. The cache is still worth reporting — a position from
        // an hour ago answers "which building" even when it cannot answer "which
        // room" — but it is returned flagged, so no caller can present it as
        // current by accident.
        val cached = lastKnown(manager)
        if (cached == null) {
            val why =
                if (providers.isEmpty()) "no location provider is enabled"
                else "no fix within ${timeoutMs / 1000}s and no last known position"
            return Outcome(null, live = false, failure = why)
        }
        AgentLog.w(
            TAG,
            "no live fix within ${timeoutMs / 1000}s; falling back to a cached " +
                "${LocationFixPlan.ageSeconds(cached, now)}s-old fix from ${cached.provider}",
        )
        return Outcome(cached, live = false)
    }

    private fun lastKnown(manager: LocationManager): LocationFixPlan.Candidate? =
        PROVIDERS.mapNotNull { provider ->
            runCatching {
                @Suppress("MissingPermission")
                manager.getLastKnownLocation(provider)
            }.getOrNull()
        }.maxByOrNull { it.time }?.toCandidate()

    private fun Location.toCandidate() = LocationFixPlan.Candidate(
        latitude = latitude,
        longitude = longitude,
        accuracyMetres = if (hasAccuracy()) accuracy else null,
        provider = provider ?: "unknown",
        timeMillis = time,
    )

    companion object {
        private const val TAG = "CurrentFix"

        /**
         * Asked in this order only for logging; they are queried together.
         *
         * `FUSED_PROVIDER` is API 31 and `minSdk` is 33, so it needs no guard. It
         * is listed first because it is the one that blends GPS, network and the
         * device's own sensors, and on a tablet indoors it is routinely the only
         * one that answers usefully.
         */
        private val PROVIDERS = listOf(
            LocationManager.FUSED_PROVIDER,
            LocationManager.GPS_PROVIDER,
            LocationManager.NETWORK_PROVIDER,
        )

        /**
         * How long `locate` waits.
         *
         * A cold GPS fix outdoors is tens of seconds, and this is a button an
         * operator pressed and is watching — they will wait for a real answer, and
         * the command queue's own delivery is slower than this anyway. Shorter
         * would mean routinely falling back to the cache, which is the bug.
         */
        const val LOCATE_TIMEOUT_MS = 45_000L

        /**
         * How long a scheduled sample waits.
         *
         * ⚠️ Shorter than `locate`, and deliberately: this runs on the sync loop,
         * unattended, on the tracking interval. Holding that loop for 45 s every
         * time a device sits indoors would delay policy, commands and the
         * long-poll for a position nobody asked for at that moment. Twenty seconds
         * catches a warm fix and gives up on a cold one.
         */
        const val SAMPLE_TIMEOUT_MS = 20_000L
    }
}
