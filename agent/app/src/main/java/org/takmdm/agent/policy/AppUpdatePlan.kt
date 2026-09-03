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

    enum class Action { INSTALL, UPGRADE, SKIP_UP_TO_DATE, SKIP_PINNED, REFUSED_DOWNGRADE }

    /**
     * @param installed the installed versionCode, or null if the app is absent.
     * @param desired the versionCode the server resolved for this policy.
     * @param autoUpdate `required_apps[].auto_update` — false means "install once,
     *   never chase a newer build".
     */
    fun decide(installed: Long?, desired: Long, autoUpdate: Boolean): Action = when {
        installed == null -> Action.INSTALL
        installed == desired -> Action.SKIP_UP_TO_DATE
        // The device is *ahead* of what the policy asks for. Android refuses to
        // install an older versionCode over a newer one, and Device Owner does not
        // override it, so the only route down is uninstall-then-install — which
        // destroys the app's data and is never something to do as a side effect of
        // a policy edit.
        //
        // This used to fold into SKIP_UP_TO_DATE and say nothing, so an operator
        // pinning an older build saw the policy apply cleanly and never learned the
        // device had ignored it. Distinguished so the reconciler can report it.
        installed > desired -> Action.REFUSED_DOWNGRADE
        !autoUpdate -> Action.SKIP_PINNED
        else -> Action.UPGRADE
    }
}
