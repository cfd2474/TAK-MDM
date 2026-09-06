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
 * Turning an operator's typed-in values into the types an app can actually read
 * (W49).
 *
 * ⚠️ **This is the whole reason managed configuration is not a string map.** An
 * app reads its configuration with `getInt` / `getBoolean`, and a Bundle holding
 * the *string* `"300"` returns **0** from `getInt` while `"true"` returns
 * **false** from `getBoolean`. The app falls back to its own default, the device
 * reports success, and nothing anywhere says the setting did not take.
 *
 * Nor can the type be guessed. "Looks numeric, send an int" would corrupt a
 * genuine string key whose value happens to be digits — Butterfly's
 * `ApprovedEnterpriseDeviceSecret` is exactly that shape. So the server sends each
 * key's declared type alongside its value, read from the build being deployed.
 *
 * Pure, so the coercion table is tested off-device; the `setApplicationRestrictions`
 * call it feeds only runs on hardware.
 */
object AppConfigPlan {

    /** `RestrictionEntry` type constants, mirroring the server's reader. */
    const val TYPE_BOOLEAN = 1
    const val TYPE_CHOICE = 2
    const val TYPE_MULTI_SELECT = 4
    const val TYPE_INTEGER = 5
    const val TYPE_STRING = 6
    const val TYPE_BUNDLE = 7
    const val TYPE_BUNDLE_ARRAY = 8

    sealed interface Value {
        data class AsBoolean(val value: Boolean) : Value
        data class AsInt(val value: Int) : Value
        data class AsString(val value: String) : Value

        /**
         * A `multi-select`, which Android carries as a `String[]`.
         *
         * A `List` rather than an `Array` so equality is by content — a data class
         * holding an `Array` compares by identity, which would make every test of
         * this case pass or fail for the wrong reason.
         */
        data class AsStringList(val value: List<String>) : Value

        /** The value cannot be expressed as its declared type; [reason] says why. */
        data class Rejected(val reason: String) : Value
    }

    /** Separators an operator might reasonably type into a single text box. */
    private val MULTI_SELECT_SEPARATORS = charArrayOf('\n', ',')

    /**
     * Coerce one value to the type the app declared for it.
     *
     * @param declaredType the `restrictionType` from the app's own schema, or null
     *   when the server could not determine it.
     */
    fun coerce(key: String, raw: String, declaredType: Int?): Value = when (declaredType) {
        TYPE_BOOLEAN -> when (raw.trim().lowercase()) {
            "true", "1", "yes" -> Value.AsBoolean(true)
            "false", "0", "no" -> Value.AsBoolean(false)
            else -> Value.Rejected(
                "$key expects true or false but the policy has \"$raw\""
            )
        }

        TYPE_INTEGER -> raw.trim().toIntOrNull()?.let { Value.AsInt(it) }
            ?: Value.Rejected("$key expects a whole number but the policy has \"$raw\"")

        // A choice is declared as a string or an int by the app; its option list is
        // a resource array the APK does not expose, so the operator typed the value
        // themselves. Send it as a number when it reads as one — Chrome's choices
        // are integers — and as text otherwise.
        TYPE_CHOICE -> raw.trim().toIntOrNull()?.let { Value.AsInt(it) } ?: Value.AsString(raw)

        // ⚠️ A multi-select is a `String[]`, never a scalar. `RestrictionsManager`
        // stores it with `putStringArray` and `RestrictionEntry.getAllSelectedStrings`
        // returns `String[]`, so an app reads it with `Bundle.getStringArray` —
        // which returns **null** when the key holds a String or an Int, swallowing
        // the type mismatch. The app then uses its own default while the device
        // reports the policy applied: exactly the silent failure this file exists
        // to prevent, which is why it cannot share the `TYPE_CHOICE` branch.
        // ⚠️ A **newline-terminated** payload is the console's, and is split on
        // newlines only. A previous attempt keyed on "contains a newline", which
        // is right for two or more selections and wrong for exactly one: a
        // single checked value joins to itself with no newline at all, falls
        // through to comma-splitting, and an option value containing a comma —
        // "Smith, John" — is torn into two values the app never offered. The
        // console now ends every generated list with a newline, so one item is
        // as unambiguous as ten. Anything else is an operator's hand-typed list,
        // where commas and newlines are both reasonable separators.
        TYPE_MULTI_SELECT -> raw.split(
            *(if (raw.endsWith('\n')) charArrayOf('\n') else MULTI_SELECT_SEPARATORS)
        )
            .map { it.trim() }
            .filter { it.isNotEmpty() }
            .let { selected ->
                if (selected.isEmpty()) {
                    // An empty selection is legitimate — it means "none of them" —
                    // and an empty array says that precisely.
                    Value.AsStringList(emptyList())
                } else {
                    Value.AsStringList(selected)
                }
            }

        TYPE_BUNDLE, TYPE_BUNDLE_ARRAY -> Value.Rejected(
            "$key is a bundle, which cannot be set from a flat value"
        )

        TYPE_STRING -> Value.AsString(raw)

        // No declared type: the app was uploaded before its schema was recorded, or
        // it no longer declares this key. Sending a string would be a coin flip —
        // right for a string key, silently wrong for every other type — so it is
        // refused and reported instead.
        null -> Value.Rejected(
            "$key has no declared type in the deployed build, so its value cannot " +
                "be sent as anything the app is sure to read"
        )

        else -> Value.AsString(raw)
    }
}
