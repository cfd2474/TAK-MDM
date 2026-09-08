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

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Which install failures are worth another go (W96, R19).
 *
 * The case that produced this: an SM-X520 handed a 32-bit Chrome downloaded it,
 * failed to install it, and did the same again on every reconcile for days. The
 * outcome could never have differed — the build's native code does not match the
 * CPU, and no amount of waiting changes either.
 */
class InstallRetryPlanTest {

    @Test
    fun `the failure that started this is never retried`() {
        val real =
            "status 7: INSTALL_FAILED_NO_MATCHING_ABIS: INSTALL_FAILED_NO_MATCHING_ABIS: " +
                "Failed to extract native libraries, res=-113"

        assertFalse(InstallRetryPlan.shouldRetry(real))
    }

    @Test
    fun `a build needing a newer Android is never retried`() {
        assertFalse(InstallRetryPlan.shouldRetry("status 7: INSTALL_FAILED_OLDER_SDK"))
    }

    @Test
    fun `a downgrade is never retried`() {
        assertFalse(
            InstallRetryPlan.shouldRetry("status 7: INSTALL_FAILED_VERSION_DOWNGRADE")
        )
    }

    @Test
    fun `a signature clash is never retried`() {
        // Fixable, but not by this agent and not by trying again.
        assertFalse(
            InstallRetryPlan.shouldRetry("status 7: INSTALL_FAILED_UPDATE_INCOMPATIBLE")
        )
    }

    @Test
    fun `a full disk is retried`() {
        // Clears on its own the moment something is deleted.
        assertTrue(
            InstallRetryPlan.shouldRetry("status 4: INSTALL_FAILED_INSUFFICIENT_STORAGE")
        )
    }

    @Test
    fun `an unfamiliar failure is retried`() {
        // ⚠️ The default leans this way on purpose. These strings come from the
        // platform and are matched as text; calling an unknown failure permanent
        // would strand an app over something transient, which is the worse of the
        // two mistakes.
        assertTrue(InstallRetryPlan.shouldRetry("status 1: something nobody has seen"))
        assertTrue(InstallRetryPlan.shouldRetry(null))
        assertTrue(InstallRetryPlan.shouldRetry(""))
    }

    @Test
    fun `the key changes when the build does`() {
        // ⚠️ The operator's fix has to be visible. Keyed on the package alone, a
        // device that rejected one APK would go on rejecting the good one that
        // replaced it.
        val bad = InstallRetryPlan.keyFor("com.android.chrome", "aaaa")
        val good = InstallRetryPlan.keyFor("com.android.chrome", "bbbb")

        assertTrue(bad != good)
        assertEquals(bad, InstallRetryPlan.keyFor("com.android.chrome", "aaaa"))
    }
}
