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

/**
 * The install/upgrade/skip decision for one required app — pure, so the
 * `auto_update` truth table is unit-tested even though [Reconciler.reconcileApps]
 * is exercised only on hardware.
 */
object AppUpdatePlan {

    enum class Action { INSTALL, UPGRADE, SKIP_UP_TO_DATE, SKIP_PINNED }

    /**
     * @param installed the installed versionCode, or null if the app is absent.
     * @param desired the versionCode the server resolved for this policy.
     * @param autoUpdate `required_apps[].auto_update` — false means "install once,
     *   never chase a newer build".
     */
    fun decide(installed: Long?, desired: Long, autoUpdate: Boolean): Action = when {
        installed == null -> Action.INSTALL
        installed >= desired -> Action.SKIP_UP_TO_DATE
        !autoUpdate -> Action.SKIP_PINNED
        else -> Action.UPGRADE
    }
}
