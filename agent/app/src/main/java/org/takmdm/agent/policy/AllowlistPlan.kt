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
 * The pure part of `APP_CATALOG.allowed_packages` enforcement: given the set of
 * non-system user apps on the device, decide which to suspend and which to
 * un-suspend. Kept free of `PackageManager` / `DevicePolicyManager` so the diff
 * is unit-tested even though [Reconciler.enforceAllowlist] runs only on hardware.
 *
 * `allowed_packages == null` means no allowlist — nothing is enforced.
 * An **empty** list also means no allowlist (an empty INTERSECT of two policies
 * that do not overlap is a stacking accident, not "suspend everything" — R4).
 */
data class AllowlistDecision(
    val toSuspend: Set<String>,
    val toUnsuspend: Set<String>,
    /** True when an allowlist is present but empty, so the caller can report it. */
    val emptyAndIgnored: Boolean,
)

object AllowlistPlan {

    fun decide(
        userApps: Set<String>,
        allowed: List<String>?,
        required: Set<String>,
        agentPackage: String,
        previouslySuspended: Set<String>,
    ): AllowlistDecision {
        if (allowed == null) {
            // No allowlist at all — release anything we suspended before.
            return AllowlistDecision(emptySet(), previouslySuspended, emptyAndIgnored = false)
        }
        if (allowed.isEmpty()) {
            return AllowlistDecision(emptySet(), previouslySuspended, emptyAndIgnored = true)
        }

        // required apps and the agent are implicitly allowed.
        val allowSet = allowed.toSet() + required + agentPackage

        val shouldBeSuspended = userApps.filterTo(HashSet()) { it !in allowSet }
        val toSuspend = shouldBeSuspended.filterTo(HashSet()) { it !in previouslySuspended }
        val toUnsuspend = previouslySuspended.filterTo(HashSet()) { it !in shouldBeSuspended }
        return AllowlistDecision(toSuspend, toUnsuspend, emptyAndIgnored = false)
    }
}
