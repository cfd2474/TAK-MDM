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
import org.junit.Test
import org.takmdm.agent.policy.AppUpdatePlan.Action

class AppUpdatePlanTest {

    @Test
    fun `absent app is always installed`() {
        assertEquals(Action.INSTALL, AppUpdatePlan.decide(installed = null, desired = 5, autoUpdate = true))
        assertEquals(Action.INSTALL, AppUpdatePlan.decide(installed = null, desired = 5, autoUpdate = false))
    }

    @Test
    fun `up-to-date app is skipped regardless of auto_update`() {
        assertEquals(Action.SKIP_UP_TO_DATE, AppUpdatePlan.decide(installed = 5, desired = 5, autoUpdate = true))
        assertEquals(Action.SKIP_UP_TO_DATE, AppUpdatePlan.decide(installed = 7, desired = 5, autoUpdate = false))
    }

    @Test
    fun `behind and auto_update on upgrades`() {
        assertEquals(Action.UPGRADE, AppUpdatePlan.decide(installed = 3, desired = 5, autoUpdate = true))
    }

    @Test
    fun `behind and auto_update off leaves it`() {
        assertEquals(Action.SKIP_PINNED, AppUpdatePlan.decide(installed = 3, desired = 5, autoUpdate = false))
    }
}
