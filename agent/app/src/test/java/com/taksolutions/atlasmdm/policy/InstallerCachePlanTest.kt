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

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class InstallerCachePlanTest {

    @Test
    fun `an installed app's parts are discarded`() {
        assertTrue(InstallerCachePlan.discardAfterInstall(installSucceeded = true))
    }

    @Test
    fun `a failed install keeps its parts for the retry`() {
        // The expensive mistake: throwing away a verified download means fetching
        // the whole APK again over whatever connection the device is on.
        assertFalse(InstallerCachePlan.discardAfterInstall(installSucceeded = false))
    }

    @Test
    fun `the build that was being installed is now running, so its APK goes`() {
        assertTrue(InstallerCachePlan.selfUpdateFinished(runningVersionCode = 88, pendingVersionCode = 88))
    }

    @Test
    fun `a later build overtook the pending one, and its APK goes too`() {
        // ⚠️ The reason this is `>=` rather than `==`. Two updates landing between
        // syncs would otherwise strand the first APK on disk permanently: nothing
        // that ever runs again could match its version.
        assertTrue(InstallerCachePlan.selfUpdateFinished(runningVersionCode = 90, pendingVersionCode = 88))
    }

    @Test
    fun `an update that did not take keeps its download`() {
        // The old build is still running — the install failed or was refused — so
        // the next attempt resumes from the APK already on disk.
        assertFalse(InstallerCachePlan.selfUpdateFinished(runningVersionCode = 87, pendingVersionCode = 88))
    }
}
