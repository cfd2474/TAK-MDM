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
