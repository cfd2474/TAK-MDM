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

import org.json.JSONObject

/**
 * Reading operator-authored text out of a CUSTOMIZATIONS spec (W42).
 *
 * Small, but not trivial enough to inline: **"absent", "empty" and "blank" are
 * three different instructions to Android**, and only one of them is the one an
 * operator means when they clear a text box.
 *
 * For `setDeviceOwnerLockScreenInfo` the platform documents that null or empty
 * *"clears the device owner info and the user owner info is shown"* — the field
 * goes back to the user — while a string of **only whitespace** leaves the lock
 * screen *"blank and the user will not be allowed to change it"*. An operator who
 * deletes the contents of a box and leaves a stray space has not asked for the
 * device to hold a blank message forever. So blank collapses to null here.
 *
 * The second trap is Android's own: [JSONObject.optString] returns the **literal
 * string `"null"`** for an explicit JSON null and `""` for a missing key. Without
 * the [JSONObject.isNull] check, a null arriving from the server would paint the
 * word "null" across the lock screen of every device it reached.
 *
 * Pure, so both rules are exercised by unit tests; the `DevicePolicyManager` calls
 * in [PolicyApplier.applyCustomizations] only run on hardware.
 */
object CustomizationsPlan {

    /** The text to push for [key], or null meaning "clear it / stop managing it". */
    fun message(spec: JSONObject, key: String): String? {
        if (spec.isNull(key)) return null
        return spec.optString(key).takeIf { it.isNotBlank() }
    }
}
