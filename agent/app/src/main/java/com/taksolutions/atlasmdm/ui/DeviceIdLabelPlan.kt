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
 * When the device ID label belongs on screen (W136).
 *
 * Pure, and separate from both the window and the watcher, because the two
 * rules below are the whole feature and neither can be exercised on a JVM if it
 * is tangled with `WindowManager` or `UsageStatsManager`.
 */
object DeviceIdLabelPlan {

    /**
     * Whether a launcher is in front, given the package that most recently
     * resumed an activity.
     *
     * ⚠️ **A null [foreground] means "no answer", not "not home".**
     * `UsageStatsManager.queryEvents` returns nothing before the user's first
     * unlock and nothing at all when no activity has resumed inside the query
     * window — which is the *normal* state of a tablet sitting untouched on its
     * home screen. Reading that as "not home" would make the label vanish a
     * second after anyone stopped touching the device, which is precisely when
     * someone is most likely to be reading it off a shelf.
     */
    fun onHome(foreground: String?, homePackages: Set<String>, previously: Boolean): Boolean =
        if (foreground == null) previously else foreground in homePackages

    /**
     * Whether to show [label] right now.
     *
     * ⚠️ **Ungated when [gated] is false, rather than hidden.** Gating needs
     * usage access, which is an app-op a Device Owner cannot grant itself. If
     * the permission is missing the choice is between a label in the wrong
     * place and no label at all, and the label exists to identify the tablet —
     * so it shows, and the reconcile warns. Hiding it would turn one missing
     * tap into a device that cannot be identified, which is the failure the
     * feature was built to prevent.
     */
    fun visible(label: String?, onHome: Boolean, gated: Boolean): Boolean =
        !label.isNullOrBlank() && (onHome || !gated)
}
