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

import com.taksolutions.atlasmdm.policy.AppConfigPlan.Value
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The coercion table (W49).
 *
 * Every case here is a *silent* failure if it goes wrong: a Bundle carrying the
 * wrong type makes the app fall back to its own default, the device reports
 * success, and nothing says the setting did not take.
 */
class AppConfigPlanTest {

    @Test
    fun `an integer key becomes an int, not the string the operator typed`() {
        // Butterfly's InactivityTimeoutSeconds. As a String this returns 0 from
        // getInt and the app quietly uses its own default.
        assertEquals(
            Value.AsInt(300),
            AppConfigPlan.coerce("InactivityTimeoutSeconds", "300", AppConfigPlan.TYPE_INTEGER),
        )
    }

    @Test
    fun `a boolean key becomes a boolean, in any spelling an operator might use`() {
        // Outlook has 33 of these; the console sends "true"/"false", but an APK's
        // own default arrives as 0/1, so both have to read the same way.
        for (yes in listOf("true", "TRUE", " true ", "1", "yes")) {
            assertEquals(
                "'$yes' should be true",
                Value.AsBoolean(true),
                AppConfigPlan.coerce("k", yes, AppConfigPlan.TYPE_BOOLEAN),
            )
        }
        for (no in listOf("false", "False", "0", "no")) {
            assertEquals(
                "'$no' should be false",
                Value.AsBoolean(false),
                AppConfigPlan.coerce("k", no, AppConfigPlan.TYPE_BOOLEAN),
            )
        }
    }

    @Test
    fun `a numeric-looking string key stays a string`() {
        // The reason the type must travel rather than be guessed. Butterfly's
        // ApprovedEnterpriseDeviceSecret could plausibly be all digits, and sending
        // it as an int would corrupt a credential.
        assertEquals(
            Value.AsString("12345"),
            AppConfigPlan.coerce("ApprovedEnterpriseDeviceSecret", "12345", AppConfigPlan.TYPE_STRING),
        )
    }

    @Test
    fun `a value that cannot be its declared type is refused, not guessed`() {
        val notANumber = AppConfigPlan.coerce("timeout", "soon", AppConfigPlan.TYPE_INTEGER)
        val notABoolean = AppConfigPlan.coerce("enabled", "maybe", AppConfigPlan.TYPE_BOOLEAN)

        assertTrue(notANumber is Value.Rejected)
        assertTrue(notABoolean is Value.Rejected)
        // The message has to name the key: an operator reading it in the console
        // has no other way to tell which of forty settings is wrong.
        assertTrue((notANumber as Value.Rejected).reason.contains("timeout"))
        assertTrue((notABoolean as Value.Rejected).reason.contains("enabled"))
    }

    @Test
    fun `an unknown declared type is refused rather than sent as a string`() {
        // Sending a string would be a coin flip: right for a string key, silently
        // wrong for every other type. The refusal is visible; a wrong type is not.
        val result = AppConfigPlan.coerce("mystery", "value", null)

        assertTrue(result is Value.Rejected)
        assertTrue((result as Value.Rejected).reason.contains("no declared type"))
    }

    @Test
    fun `a bundle key is refused, because a flat value cannot express one`() {
        // Gboard's `preferences`. The console already refuses to offer it; this is
        // the second gate, for a desired state written by any other route.
        val result = AppConfigPlan.coerce("preferences", "{}", AppConfigPlan.TYPE_BUNDLE)

        assertTrue(result is Value.Rejected)
        assertTrue((result as Value.Rejected).reason.contains("bundle"))
    }

    @Test
    fun `a choice sends a number when it reads as one, and text otherwise`() {
        // Chrome's choices are integers, but the option list is a resource array the
        // APK does not expose — so the operator typed it and either shape is
        // legitimate.
        assertEquals(
            Value.AsInt(1),
            AppConfigPlan.coerce("AdsSetting", "1", AppConfigPlan.TYPE_CHOICE),
        )
        assertEquals(
            Value.AsString("BlockAll"),
            AppConfigPlan.coerce("AdsSetting", "BlockAll", AppConfigPlan.TYPE_CHOICE),
        )
    }

    @Test
    fun `a multi-select is a string list, never a scalar`() {
        // ⚠️ Android carries multi-select as String[]: RestrictionsManager stores it
        // with putStringArray and the app reads it with getStringArray, which returns
        // null for a String or an Int. Sent as a scalar the app silently keeps its
        // default while the device reports the policy applied.
        assertEquals(
            Value.AsStringList(listOf("example.com", "other.test")),
            AppConfigPlan.coerce("AllowedDomains", "example.com,other.test", AppConfigPlan.TYPE_MULTI_SELECT),
        )
    }

    @Test
    fun `a multi-select accepts one entry per line, and tolerates spacing`() {
        assertEquals(
            Value.AsStringList(listOf("a.example", "b.example")),
            AppConfigPlan.coerce("AllowedDomains", " a.example \n b.example \n", AppConfigPlan.TYPE_MULTI_SELECT),
        )
    }

    @Test
    fun `a single multi-select value is still a list`() {
        // The shape must not depend on how many were chosen — one entry typed
        // without a separator is still String[1], not a String.
        assertEquals(
            Value.AsStringList(listOf("only.one")),
            AppConfigPlan.coerce("AllowedDomains", "only.one", AppConfigPlan.TYPE_MULTI_SELECT),
        )
    }

    @Test
    fun `an empty multi-select is an empty list rather than a rejection`() {
        // "None of them" is a legitimate selection and an empty array says it.
        assertEquals(
            Value.AsStringList(emptyList()),
            AppConfigPlan.coerce("AllowedDomains", "  ", AppConfigPlan.TYPE_MULTI_SELECT),
        )
    }

    @Test
    fun `a newline-terminated multi-select keeps commas inside its values`() {
        assertEquals(
            Value.AsStringList(listOf("Smith, John", "Doe, Jane")),
            AppConfigPlan.coerce("Names", "Smith, John\nDoe, Jane\n", AppConfigPlan.TYPE_MULTI_SELECT),
        )
    }

    @Test
    fun `a single selected value containing a comma is not torn in half`() {
        // ⚠️ The case a "contains a newline" guard got wrong. One checked box joins
        // to itself with no separator, so a guard keying on "contains" fell through
        // to comma-splitting and turned one chosen value into two the app never
        // offered — silently, with the device reporting the policy applied. The
        // console terminates its lists with a newline so one item is as
        // unambiguous as ten.
        assertEquals(
            Value.AsStringList(listOf("Smith, John")),
            AppConfigPlan.coerce("Names", "Smith, John\n", AppConfigPlan.TYPE_MULTI_SELECT),
        )
    }

    @Test
    fun `a hand-typed comma list still works`() {
        // No trailing newline means it did not come from the console, and there a
        // comma is the separator an operator would reach for.
        assertEquals(
            Value.AsStringList(listOf("a.example", "b.example")),
            AppConfigPlan.coerce("Domains", "a.example, b.example", AppConfigPlan.TYPE_MULTI_SELECT),
        )
    }

    @Test
    fun `a numeric-looking multi-select is not turned into an int`() {
        // The bug this replaced: multi-select shared the choice branch, so a value
        // that read as a number became AsInt and the app got the wrong type twice
        // over — wrong container and wrong element type.
        assertEquals(
            Value.AsStringList(listOf("1", "2")),
            AppConfigPlan.coerce("Flags", "1,2", AppConfigPlan.TYPE_MULTI_SELECT),
        )
    }
}
