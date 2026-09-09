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
import kotlin.math.asin
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * Which fences a position is subject to, and what they add up to (W106 C4).
 *
 * Pure: geometry and a fold over a list. That matters more here than elsewhere,
 * because the interesting cases — a fence crossing the antimeridian, two fences
 * disagreeing, a device exactly on a boundary — are ones nobody can produce by
 * carrying a tablet around, and would otherwise never be tested at all.
 *
 * ⚠️ **Evaluated on the device, deliberately.** A fence that needs the network to
 * decide whether it applies is not a fence: the first thing that happens in the
 * places these exist for is losing the network.
 */
object GeofencePlan {

    const val FENCES_KEY = "geofences"

    /** Mean Earth radius, metres. */
    private const val EARTH_RADIUS_M = 6_371_008.8

    enum class Radio { ON, OFF, UNMANAGED }

    /**
     * What a fence asks of the screen lock (W111).
     *
     * ⚠️ `OFF` suspends the passcode *this system set*, and cannot touch a PIN the
     * user chose — `setKeyguardDisabled` cannot bypass one and neither can Knox.
     * The server only accepts `OFF` on a profile whose PASSWORD policy sets a
     * passcode, which is the one case where there is something to put back.
     */
    enum class Lock { NONE, OFF, ON }

    data class Fence(
        val name: String,
        val latitude: Double,
        val longitude: Double,
        val radiusMetres: Double,
        val triggerOnEntry: Boolean,
        val lock: Lock,
        val wifi: Radio,
        val bluetooth: Radio,
        val intervalOverrideMinutes: Int,
    )

    /**
     * What the device should do, once every active fence has had its say.
     *
     * `null` on a radio means no fence expressed an opinion, which is different
     * from "leave it on" — nothing is applied and nothing is released.
     */
    data class Actions(
        val lock: Lock = Lock.NONE,
        val wifi: Radio = Radio.UNMANAGED,
        val bluetooth: Radio = Radio.UNMANAGED,
        val intervalOverrideMinutes: Int = 0,
        val activeFences: List<String> = emptyList(),
    ) {
        val hasAny: Boolean
            get() = lock != Lock.NONE ||
                wifi != Radio.UNMANAGED ||
                bluetooth != Radio.UNMANAGED ||
                intervalOverrideMinutes > 0
    }

    // ------------------------------------------------------------------ parse

    fun parse(section: JSONObject?): List<Fence> {
        val array = section?.optJSONArray(FENCES_KEY) ?: return emptyList()
        val out = mutableListOf<Fence>()
        for (i in 0 until array.length()) {
            val row = array.optJSONObject(i) ?: continue
            // A fence missing its geometry is not a fence. Skipped rather than
            // defaulted to 0,0 — which is a real place in the Atlantic, and a
            // device would be "outside" it for ever, silently applying every
            // exit-triggered action the row carried.
            if (!row.has("latitude") || !row.has("longitude") || !row.has("radius_m")) continue
            out += Fence(
                name = row.optString("name", "unnamed"),
                latitude = row.optDouble("latitude"),
                longitude = row.optDouble("longitude"),
                radiusMetres = row.optDouble("radius_m", 0.0),
                triggerOnEntry = row.optString("trigger", "entry") != "exit",
                lock = lock(row),
                wifi = radio(row.optString("wifi", "unmanaged")),
                bluetooth = radio(row.optString("bluetooth", "unmanaged")),
                intervalOverrideMinutes =
                    row.optInt("reporting_interval_override_minutes", 0).coerceAtLeast(0),
            )
        }
        return out
    }

    /** Reads the three-state field, and the pre-W111 boolean beside it. */
    private fun lock(row: JSONObject): Lock {
        if (row.has("password")) {
            return when (row.optString("password", "none")) {
                "on" -> Lock.ON
                "off" -> Lock.OFF
                else -> Lock.NONE
            }
        }
        return if (row.optBoolean("password_enforced", false)) Lock.ON else Lock.NONE
    }

    private fun radio(value: String): Radio = when (value) {
        "on" -> Radio.ON
        "off" -> Radio.OFF
        else -> Radio.UNMANAGED
    }

    // --------------------------------------------------------------- geometry

    /**
     * Great-circle distance in metres.
     *
     * ⚠️ **Haversine, not the flat approximation.** A degree of longitude is
     * 111 km at the equator and 0 km at the pole, so treating latitude and
     * longitude as a plane makes a fence wrong by a factor that depends on where
     * it is — correct in testing near the equator and badly wrong at 60° north.
     * The `asin(min(1.0, ...))` guard matters too: floating point can push the
     * argument a hair above 1 for two identical points, and `asin` of that is NaN,
     * which would make a device sitting still read as outside every fence.
     */
    fun distanceMetres(
        lat1: Double, lon1: Double, lat2: Double, lon2: Double,
    ): Double {
        val phi1 = Math.toRadians(lat1)
        val phi2 = Math.toRadians(lat2)
        val dPhi = Math.toRadians(lat2 - lat1)
        val dLambda = Math.toRadians(lon2 - lon1)

        val a = sin(dPhi / 2) * sin(dPhi / 2) +
            cos(phi1) * cos(phi2) * sin(dLambda / 2) * sin(dLambda / 2)
        return 2 * EARTH_RADIUS_M * asin(min(1.0, sqrt(a)))
    }

    fun isInside(fence: Fence, latitude: Double, longitude: Double): Boolean =
        distanceMetres(fence.latitude, fence.longitude, latitude, longitude) <= fence.radiusMetres

    /**
     * Is this fence's condition met at this position?
     *
     * Entry means inside; exit means outside — the operator's own words. A state,
     * not an edge: the actions hold while the condition holds, which is the only
     * reading that survives a reboot or a boundary crossed while switched off.
     */
    fun isActive(fence: Fence, latitude: Double, longitude: Double): Boolean {
        val inside = isInside(fence, latitude, longitude)
        return if (fence.triggerOnEntry) inside else !inside
    }

    // ------------------------------------------------------------------- fold

    /**
     * Combine every active fence, most restrictive winning.
     *
     * ⚠️ **"Most restrictive" needs saying per field, because it is not one rule.**
     *
     * * A radio: `OFF` beats `ON` beats `UNMANAGED`. A fence that turns a radio
     *   off is normally the security-motivated one, and losing connectivity is
     *   recoverable in a way that leaking is not.
     * * A password: required beats not required. There is no "un-require".
     * * An interval override: the **shortest non-zero** wins. More frequent
     *   reporting is the more restrictive answer, and `0` here means "no opinion"
     *   rather than "never" — so it must lose to any real value, which a plain
     *   `min` would get exactly backwards.
     */
    fun resolve(fences: List<Fence>, latitude: Double, longitude: Double): Actions {
        val active = fences.filter { isActive(it, latitude, longitude) }
        if (active.isEmpty()) return Actions()

        var wifi = Radio.UNMANAGED
        var bluetooth = Radio.UNMANAGED
        var lock = Lock.NONE
        var interval = 0

        for (fence in active) {
            wifi = moreRestrictive(wifi, fence.wifi)
            bluetooth = moreRestrictive(bluetooth, fence.bluetooth)
            // ⚠️ ON beats OFF beats NONE. A trusted area must never win over a
            // fence that requires a lock — overlapping them is exactly how a
            // secure zone would be silently unlocked by a neighbouring one.
            lock = when {
                lock == Lock.ON || fence.lock == Lock.ON -> Lock.ON
                lock == Lock.OFF || fence.lock == Lock.OFF -> Lock.OFF
                else -> Lock.NONE
            }
            if (fence.intervalOverrideMinutes > 0) {
                interval =
                    if (interval == 0) fence.intervalOverrideMinutes
                    else min(interval, fence.intervalOverrideMinutes)
            }
        }

        return Actions(
            lock = lock,
            wifi = wifi,
            bluetooth = bluetooth,
            intervalOverrideMinutes = interval,
            activeFences = active.map { it.name },
        )
    }

    private fun moreRestrictive(current: Radio, candidate: Radio): Radio = when {
        current == Radio.OFF || candidate == Radio.OFF -> Radio.OFF
        current == Radio.ON || candidate == Radio.ON -> Radio.ON
        else -> Radio.UNMANAGED
    }

    /**
     * The interval to sample at, given the tracking policy and any override.
     *
     * ⚠️ **A fence implies sampling even when tracking is off.** An operator who
     * sets a fence and leaves the reporting interval at 0 has configured something
     * that could never evaluate — it would read as broken rather than as
     * unconfigured. So the presence of any fence puts a floor under the interval,
     * using the deployment's configured poll default.
     */
    fun samplingInterval(
        trackingMinutes: Int,
        overrideMinutes: Int,
        hasFences: Boolean,
        fenceDefaultMinutes: Int,
    ): Int {
        if (overrideMinutes > 0) {
            return if (trackingMinutes > 0) min(trackingMinutes, overrideMinutes) else overrideMinutes
        }
        if (trackingMinutes > 0) return trackingMinutes
        return if (hasFences) fenceDefaultMinutes.coerceAtLeast(1) else 0
    }

    /**
     * The PASSWORD spec to apply, with an active fence's requirement folded in.
     *
     * ⚠️ **The fence must feed the existing writer, not become a second one.**
     * `PolicyApplier.applyPassword` drives every password field to a definite
     * value on *every* reconcile, pushing the permissive value when the policy is
     * absent — that is R14, and it exists because a latched
     * `minimumPasswordLength` from a policy that no longer applied once made a
     * device reject a passcode with no way to clear it from the console.
     *
     * A geofence that called `setPasswordQuality` itself would therefore be undone
     * by the next sync, minutes later, silently. Folding the requirement into the
     * spec instead keeps exactly one writer, and makes release automatic: when the
     * fence stops being active the floor is simply no longer added, and the same
     * code path pushes the policy's own value back.
     *
     * `SOMETHING` (ordinal 1) is the floor: *some* lock — pattern, PIN or
     * password. `effectiveQuality` already takes the strictest of what it is
     * given, so a PASSWORD policy asking for more keeps its answer.
     */
    fun passwordSpecWithFence(spec: JSONObject?, lock: Lock): JSONObject {
        val base = spec ?: JSONObject()

        // ⚠️ A trusted area hands the applier an **empty** spec, which is not the
        // same as skipping it. `applyPassword` drives every field to a definite
        // value on every reconcile and treats absent as permissive (R14) — so an
        // empty spec is what actively releases the constraints, and releasing
        // them is what lets the passcode be cleared at all.
        if (lock == Lock.OFF) return JSONObject()
        if (lock != Lock.ON) return base

        val merged = JSONObject()
        for (key in base.keys()) merged.put(key, base.get(key))
        val existing = if (base.has("quality")) base.optInt("quality", 0) else 0
        merged.put("quality", maxOf(existing, PASSWORD_QUALITY_SOMETHING))
        return merged
    }

    /** `PasswordPlan.PwQuality.SOMETHING` — some lock, of any kind. */
    const val PASSWORD_QUALITY_SOMETHING = 1

    /** The stored name of a lock state, and back. Unknown reads as NONE — the
     *  safe end: a device with an unreadable setting keeps its passcode. */
    fun lockFromName(name: String?): Lock = when (name) {
        "on" -> Lock.ON
        "off" -> Lock.OFF
        else -> Lock.NONE
    }

    fun nameOf(lock: Lock): String = when (lock) {
        Lock.ON -> "on"
        Lock.OFF -> "off"
        Lock.NONE -> "none"
    }

    /** Fences as JSON, for the buffered record of what was applied. */
    fun namesOf(fences: List<Fence>): JSONArray = JSONArray(fences.map { it.name })
}
