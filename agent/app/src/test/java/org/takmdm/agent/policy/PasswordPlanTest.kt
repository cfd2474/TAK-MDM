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

package org.takmdm.agent.policy

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.takmdm.agent.policy.PasswordPlan.PwQuality

class PasswordPlanTest {

    @Test
    fun `nothing set yields UNSPECIFIED, not null`() {
        // R14: the applier must always have a value to push, so a quality left by
        // a policy that no longer applies is released rather than latched.
        assertEquals(PwQuality.UNSPECIFIED, PasswordPlan.effectiveQuality(null, null, null, null, null))
        assertEquals(PwQuality.UNSPECIFIED, PasswordPlan.effectiveQuality(0, null, null, null, null))
    }

    @Test
    fun `a zero min length does not raise the quality`() {
        // Absent and explicitly-zero both mean "no floor", so neither forces NUMERIC.
        assertEquals(PwQuality.UNSPECIFIED, PasswordPlan.effectiveQuality(null, 0, null, null, null))
    }

    @Test
    fun `quality field maps straight through`() {
        assertEquals(PwQuality.ALPHABETIC, PasswordPlan.effectiveQuality(4, null, null, null, null))
        assertEquals(PwQuality.COMPLEX, PasswordPlan.effectiveQuality(6, null, null, null, null))
    }

    @Test
    fun `a min length floor forces at least NUMERIC`() {
        assertEquals(PwQuality.NUMERIC, PasswordPlan.effectiveQuality(null, 8, null, null, null))
        // but does not pull a higher quality down
        assertEquals(PwQuality.ALPHANUMERIC, PasswordPlan.effectiveQuality(5, 8, null, null, null))
    }

    @Test
    fun `any character-class minimum forces COMPLEX`() {
        assertEquals(PwQuality.COMPLEX, PasswordPlan.effectiveQuality(null, null, 1, null, null))
        assertEquals(PwQuality.COMPLEX, PasswordPlan.effectiveQuality(2, null, null, 2, null))
        assertEquals(PwQuality.COMPLEX, PasswordPlan.effectiveQuality(null, null, null, null, 1))
    }

    @Test
    fun `a zero character-class minimum is not a requirement`() {
        assertEquals(PwQuality.NUMERIC, PasswordPlan.effectiveQuality(2, null, 0, 0, 0))
    }

    @Test
    fun `charClassMinimumsApply only at COMPLEX`() {
        assertTrue(PasswordPlan.charClassMinimumsApply(PwQuality.COMPLEX))
        assertFalse(PasswordPlan.charClassMinimumsApply(PwQuality.ALPHANUMERIC))
        assertFalse(PasswordPlan.charClassMinimumsApply(PwQuality.UNSPECIFIED))
    }

    @Test
    fun `R14 the exact case that broke on hardware`() {
        // A policy asking only for a numeric passcode must resolve to NUMERIC —
        // and because the applier now also pushes min_length 0, a 4-digit PIN is
        // no longer rejected by a length latched from a policy long since removed.
        val q = PasswordPlan.effectiveQuality(quality = 2, minLength = null, null, null, null)
        assertEquals(PwQuality.NUMERIC, q)
        assertFalse(PasswordPlan.charClassMinimumsApply(q))
    }
}
