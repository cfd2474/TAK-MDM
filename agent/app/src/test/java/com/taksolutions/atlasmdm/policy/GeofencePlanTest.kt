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

import com.taksolutions.atlasmdm.policy.GeofencePlan.Radio
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Geofence geometry and conflict resolution (W106 C4).
 *
 * These are the cases nobody produces by carrying a tablet around: a fence at high
 * latitude, two fences disagreeing, a device standing exactly still. Off-device is
 * the only place they get tested at all.
 */
class GeofencePlanTest {

    private fun fence(
        name: String = "HQ",
        lat: Double = 33.6236,
        lon: Double = -117.1270,
        radius: Double = 200.0,
        entry: Boolean = true,
        password: Boolean = false,
        wifi: Radio = Radio.UNMANAGED,
        bluetooth: Radio = Radio.UNMANAGED,
        override: Int = 0,
    ) = GeofencePlan.Fence(name, lat, lon, radius, entry, password, wifi, bluetooth, override)

    // -------------------------------------------------------------- geometry

    @Test
    fun `a known distance comes out right`() {
        // Los Angeles to New York, about 3,936 km.
        val metres = GeofencePlan.distanceMetres(34.0522, -118.2437, 40.7128, -74.0060)

        assertTrue("was $metres", metres > 3_930_000 && metres < 3_950_000)
    }

    @Test
    fun `a degree of longitude shrinks towards the pole`() {
        // ⚠️ The reason this is haversine rather than the flat approximation. A
        // degree of longitude is ~111 km at the equator and ~55 km at 60 degrees;
        // treating lat/lon as a plane makes a fence wrong by a factor that depends
        // on where in the world it is, which tests near the equator never catch.
        val atEquator = GeofencePlan.distanceMetres(0.0, 0.0, 0.0, 1.0)
        val atSixty = GeofencePlan.distanceMetres(60.0, 0.0, 60.0, 1.0)

        assertTrue(atEquator > 111_000 && atEquator < 111_500)
        assertTrue("was $atSixty", atSixty > 55_000 && atSixty < 56_000)
    }

    @Test
    fun `a device standing perfectly still is inside its fence`() {
        // ⚠️ Floating point can push haversine's argument a hair above 1.0 for two
        // identical points, and asin of that is NaN — which compares false against
        // every radius and would read as "outside every fence" for a device that
        // had not moved at all.
        val here = fence(lat = 45.0, lon = -93.0)
        val distance = GeofencePlan.distanceMetres(45.0, -93.0, 45.0, -93.0)

        assertFalse("distance was NaN", distance.isNaN())
        assertEquals(0.0, distance, 0.001)
        assertTrue(GeofencePlan.isInside(here, 45.0, -93.0))
    }

    @Test
    fun `the boundary counts as inside`() {
        // Someone has to own the edge. Inside is the choice that makes a fence's
        // stated radius the distance it actually covers.
        val f = fence(radius = 1000.0)
        val north = 33.6236 + (1000.0 / 111_320.0)

        assertTrue(GeofencePlan.isInside(f, north, -117.1270))
    }

    // --------------------------------------------------------------- triggers

    @Test
    fun `entry applies inside and exit applies outside`() {
        val entry = fence(entry = true)
        val exit = fence(entry = false)

        assertTrue(GeofencePlan.isActive(entry, 33.6236, -117.1270))
        assertFalse(GeofencePlan.isActive(exit, 33.6236, -117.1270))

        // A long way away.
        assertFalse(GeofencePlan.isActive(entry, 40.0, -74.0))
        assertTrue(GeofencePlan.isActive(exit, 40.0, -74.0))
    }

    @Test
    fun `a fence is a state and not an edge, so it holds while it holds`() {
        // ⚠️ The operator's own words: entry is "when the device is inside". A
        // device rebooted inside a fence, or carried across the boundary while
        // switched off, is still subject to it — an edge-triggered fence that
        // missed its edge would stay wrong for ever.
        val f = fence(entry = true, wifi = Radio.OFF)

        repeat(3) {
            assertTrue(GeofencePlan.isActive(f, 33.6236, -117.1270))
        }
        assertEquals(
            Radio.OFF,
            GeofencePlan.resolve(listOf(f), 33.6236, -117.1270).wifi,
        )
    }

    // -------------------------------------------------------------- conflicts

    @Test
    fun `off beats on when two fences disagree about a radio`() {
        val on = fence(name = "campus", radius = 5000.0, wifi = Radio.ON)
        val off = fence(name = "vault", radius = 100.0, wifi = Radio.OFF)

        val actions = GeofencePlan.resolve(listOf(on, off), 33.6236, -117.1270)

        assertEquals(Radio.OFF, actions.wifi)
        assertEquals(listOf("campus", "vault"), actions.activeFences)
    }

    @Test
    fun `order does not change the answer`() {
        // Most-restrictive has to be commutative, or the result would depend on
        // the order the operator happened to add the fences in.
        val on = fence(name = "a", radius = 5000.0, bluetooth = Radio.ON)
        val off = fence(name = "b", radius = 5000.0, bluetooth = Radio.OFF)

        assertEquals(
            GeofencePlan.resolve(listOf(on, off), 33.6236, -117.1270).bluetooth,
            GeofencePlan.resolve(listOf(off, on), 33.6236, -117.1270).bluetooth,
        )
    }

    @Test
    fun `any fence requiring a password wins`() {
        val lax = fence(name = "a", radius = 5000.0, password = false)
        val strict = fence(name = "b", radius = 5000.0, password = true)

        assertTrue(GeofencePlan.resolve(listOf(lax, strict), 33.6236, -117.1270).passwordEnforced)
    }

    @Test
    fun `the shortest override wins, and zero is not the shortest`() {
        // ⚠️ 0 means "no opinion", so a plain min() would let it beat every real
        // value and switch reporting off inside a fence — the exact opposite of
        // what a fence with an override is for.
        val noOpinion = fence(name = "a", radius = 5000.0, override = 0)
        val slow = fence(name = "b", radius = 5000.0, override = 30)
        val fast = fence(name = "c", radius = 5000.0, override = 5)

        val actions = GeofencePlan.resolve(listOf(noOpinion, slow, fast), 33.6236, -117.1270)

        assertEquals(5, actions.intervalOverrideMinutes)
    }

    @Test
    fun `an inactive fence contributes nothing`() {
        val far = fence(name = "elsewhere", lat = 10.0, lon = 10.0, wifi = Radio.OFF)

        val actions = GeofencePlan.resolve(listOf(far), 33.6236, -117.1270)

        assertEquals(Radio.UNMANAGED, actions.wifi)
        assertFalse(actions.hasAny)
    }

    // ------------------------------------------------------------------ parse

    @Test
    fun `a fence missing its geometry is skipped, not defaulted to zero zero`() {
        // ⚠️ 0,0 is a real place in the Atlantic. Defaulting to it would make every
        // device permanently "outside" that fence, silently applying whatever an
        // exit trigger carried — radios off, everywhere, for ever.
        val section = JSONObject().put(
            "geofences",
            JSONArray().put(JSONObject().put("name", "broken").put("trigger", "exit")),
        )

        assertTrue(GeofencePlan.parse(section).isEmpty())
    }

    @Test
    fun `an absent section is no fences rather than an error`() {
        assertTrue(GeofencePlan.parse(null).isEmpty())
        assertTrue(GeofencePlan.parse(JSONObject()).isEmpty())
    }

    @Test
    fun `a fence round-trips from the policy JSON`() {
        val section = JSONObject().put(
            "geofences",
            JSONArray().put(
                JSONObject()
                    .put("name", "Vault")
                    .put("latitude", 33.6236)
                    .put("longitude", -117.1270)
                    .put("radius_m", 150)
                    .put("trigger", "entry")
                    .put("password_enforced", true)
                    .put("wifi", "off")
                    .put("bluetooth", "on")
                    .put("reporting_interval_override_minutes", 2)
            ),
        )

        val parsed = GeofencePlan.parse(section).single()

        assertEquals("Vault", parsed.name)
        assertEquals(150.0, parsed.radiusMetres, 0.001)
        assertTrue(parsed.triggerOnEntry)
        assertTrue(parsed.passwordEnforced)
        assertEquals(Radio.OFF, parsed.wifi)
        assertEquals(Radio.ON, parsed.bluetooth)
        assertEquals(2, parsed.intervalOverrideMinutes)
    }

    // ------------------------------------------------------------- scheduling

    @Test
    fun `a fence makes the device sample even when tracking is off`() {
        // ⚠️ Otherwise an operator who sets a fence but leaves the interval at 0
        // has configured something that can never evaluate, and it reads as broken
        // rather than as unconfigured.
        val interval = GeofencePlan.samplingInterval(
            trackingMinutes = 0, overrideMinutes = 0, hasFences = true, fenceDefaultMinutes = 5,
        )

        assertEquals(5, interval)
    }

    @Test
    fun `no fences and no tracking means no sampling`() {
        assertEquals(
            0,
            GeofencePlan.samplingInterval(0, 0, hasFences = false, fenceDefaultMinutes = 5),
        )
    }

    @Test
    fun `an override tightens the interval rather than loosening it`() {
        assertEquals(
            2,
            GeofencePlan.samplingInterval(15, 2, hasFences = true, fenceDefaultMinutes = 5),
        )
        // A slower override does not slow a faster tracking interval.
        assertEquals(
            5,
            GeofencePlan.samplingInterval(5, 30, hasFences = true, fenceDefaultMinutes = 5),
        )
    }

    // ------------------------------------------------------- password folding

    @Test
    fun `an enforcing fence raises the password floor in the spec`() {
        // ⚠️ Folded into the PASSWORD spec rather than applied separately, so the
        // existing single writer applies and releases it. A second writer would be
        // undone by the next reconcile, minutes later, silently.
        val merged = GeofencePlan.passwordSpecWithFence(JSONObject(), enforced = true)

        assertEquals(GeofencePlan.PASSWORD_QUALITY_SOMETHING, merged.optInt("quality"))
    }

    @Test
    fun `a stricter password policy is not weakened by the fence floor`() {
        val strict = JSONObject().put("quality", 6).put("min_length", 12)

        val merged = GeofencePlan.passwordSpecWithFence(strict, enforced = true)

        assertEquals(6, merged.optInt("quality"))
        assertEquals(12, merged.optInt("min_length"), )
    }

    @Test
    fun `no fence means the spec is handed through untouched`() {
        // ⚠️ This is the release path. The floor is simply not added, and the same
        // single writer pushes the policy's own value back — which for an absent
        // policy is the permissive one.
        val original = JSONObject().put("quality", 2)

        val untouched = GeofencePlan.passwordSpecWithFence(original, enforced = false)

        assertEquals(2, untouched.optInt("quality"))
        assertFalse(untouched === JSONObject())
    }

    @Test
    fun `folding does not mutate the policy it was given`() {
        // The caller may apply the same policy object elsewhere; a fence that
        // edited it in place would leak its floor into everything downstream.
        val original = JSONObject().put("quality", 0)

        GeofencePlan.passwordSpecWithFence(original, enforced = true)

        assertEquals(0, original.optInt("quality"))
    }

    @Test
    fun `an absent password policy still gets the fence floor`() {
        val merged = GeofencePlan.passwordSpecWithFence(null, enforced = true)

        assertEquals(GeofencePlan.PASSWORD_QUALITY_SOMETHING, merged.optInt("quality"))
    }
}
