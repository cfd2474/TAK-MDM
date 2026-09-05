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

package com.taksolutions.atlasmdm.ui

/**
 * Which tab a managed app belongs on in the DPC's Apps section (W48).
 *
 * Pure, and separate from [MainActivity], because misfiling an app is a silent
 * failure — it simply does not appear where someone looked — and an Activity
 * cannot be unit-tested. The rendering stays in the Activity; the decision lives
 * here, matching the `*Plan` convention used across the policy package.
 *
 * ⚠️ Every managed app is **required** by policy. The marketplace tier (F4) is
 * files, not apps, so [AppsTab.AVAILABLE] means *"policy wants this and it is not
 * installed yet"* — a queue, not a shop.
 */
object AppsTabPlan {

    enum class AppsTab { AVAILABLE, INSTALLED, UPDATES }

    /**
     * @param available whether the server resolved a publishable build for this
     *   app. False means the policy names something with nothing to install.
     * @param installedVersionCode what is on the device now, or null if absent.
     * @param wantedVersionCode the build the policy is asking for.
     */
    fun tabFor(
        available: Boolean,
        installedVersionCode: Long?,
        wantedVersionCode: Long,
    ): AppsTab = when {
        // Not installable at all — no published build resolves for it. It stays in
        // Available rather than being hidden: this is the only place the device
        // admits a policy is broken, and filtering it away would lose that signal
        // while looking tidier.
        !available -> AppsTab.AVAILABLE
        installedVersionCode == null -> AppsTab.AVAILABLE
        // Ahead of the policy counts as Installed, not as an update. A device that
        // somehow carries a newer build has nothing to fetch, and Android would
        // refuse the downgrade anyway.
        installedVersionCode >= wantedVersionCode -> AppsTab.INSTALLED
        else -> AppsTab.UPDATES
    }
}
