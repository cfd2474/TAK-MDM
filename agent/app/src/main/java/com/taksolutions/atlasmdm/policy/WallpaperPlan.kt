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

/**
 * Which wallpaper this device should use.
 *
 * The choice is made here rather than on the server (D46): the device knows its own
 * `smallestScreenWidthDp` and the server does not, so sending both slots and
 * deciding locally costs two strings and removes a whole class of "the server
 * guessed wrong" failure. Only the chosen image is ever downloaded.
 *
 * An operator with one form factor uploads one image, and it applies everywhere —
 * having to upload the same picture twice to cover a fleet that is all tablets
 * would be a chore invented by the implementation.
 */
object WallpaperPlan {

    /**
     * Android's own tablet boundary — the `sw600dp` resource qualifier. Using the
     * same line as the resource system means the split matches what every other app
     * on the device already assumes, rather than inventing a threshold that
     * disagrees with the layout the user is looking at.
     */
    const val TABLET_MIN_WIDTH_DP = 600

    enum class Choice { TABLET, PHONE, NONE }

    /**
     * Whether to put the device back on its factory wallpaper.
     *
     * Only when the policy now names **no image at all** and the agent had
     * previously applied one. Two things this deliberately does not do:
     *
     * - it does not clear a wallpaper the agent never set, which would be the same
     *   overreach as R19's restore-what-we-never-displaced;
     * - it does not clear when a slot is filled but its file has left the library.
     *   That is a *broken* policy, not a removed one, and wiping the wallpaper
     *   would turn a reported error into a visible change nobody asked for.
     *
     * Unlike a screen timeout there is nothing to remember: `WallpaperManager.clear`
     * restores the device default, and the user's own previous picture is not
     * recoverable from the platform in any case.
     */
    fun shouldClear(
        policyNamesAnyImage: Boolean,
        previouslyApplied: Boolean
    ): Boolean = !policyNamesAnyImage && previouslyApplied

    /**
     * @param hasTablet a tablet image is available in the desired state.
     * @param hasPhone a phone image is available.
     * @param smallestWidthDp this device's `smallestScreenWidthDp`.
     */
    fun choose(hasTablet: Boolean, hasPhone: Boolean, smallestWidthDp: Int): Choice = when {
        !hasTablet && !hasPhone -> Choice.NONE
        // Only one uploaded: it applies whatever this device is. The operator said
        // what they wanted by uploading exactly one.
        !hasPhone -> Choice.TABLET
        !hasTablet -> Choice.PHONE
        smallestWidthDp >= TABLET_MIN_WIDTH_DP -> Choice.TABLET
        else -> Choice.PHONE
    }
}
