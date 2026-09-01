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

package org.takmdm.agent.diag

import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * These logs leave the device when an operator collects them, so what the redactor
 * misses is disclosed to whoever can read the console.
 */
class RedactorTest {

    @After
    fun tearDown() = Redactor.resetForTest()

    @Test
    fun `a registered secret is removed`() {
        Redactor.protect("s3cret-enrollment-token-value")

        val scrubbed = Redactor.scrub("enrolling with s3cret-enrollment-token-value now")

        assertFalse(scrubbed.contains("s3cret-enrollment-token-value"))
        assertTrue(scrubbed.contains("[redacted]"))
    }

    @Test
    fun `a registered secret is removed everywhere it appears`() {
        Redactor.protect("token-aaaaaaaa")

        val scrubbed = Redactor.scrub("token-aaaaaaaa then again token-aaaaaaaa")

        assertFalse(scrubbed.contains("token-aaaaaaaa"))
    }

    @Test
    fun `a forgotten secret is no longer masked`() {
        Redactor.protect("consumed-token-value")
        Redactor.forget("consumed-token-value")

        // Not cosmetic: the set is process-wide, and a token consumed at enrolment
        // would otherwise mask any later text that happened to contain it.
        assertTrue(Redactor.scrub("consumed-token-value").contains("consumed-token-value"))
    }

    @Test
    fun `short values are not registered`() {
        Redactor.protect("ok")

        // Masking every two-character string would redact ordinary prose and leave
        // a log nobody can read — its own kind of failure.
        assertEquals("that looks ok to me", Redactor.scrub("that looks ok to me"))
    }

    @Test
    fun `the longest matching secret wins`() {
        Redactor.protect("abcdefgh")
        Redactor.protect("abcdefgh-ijklmnop")

        val scrubbed = Redactor.scrub("value abcdefgh-ijklmnop end")

        // Masking the shorter one first would leave "-ijklmnop" exposed beside the
        // mask, which discloses the tail of the secret and looks like a bug.
        assertEquals("value [redacted] end", scrubbed)
    }

    @Test
    fun `a private key block is removed whole`() {
        val text = """
            before
            -----BEGIN EC PRIVATE KEY-----
            MHcCAQEEIQD1234567890
            -----END EC PRIVATE KEY-----
            after
        """.trimIndent()

        val scrubbed = Redactor.scrub(text)

        assertFalse(scrubbed.contains("MHcCAQEEIQD1234567890"))
        assertTrue(scrubbed.contains("before"))
        assertTrue(scrubbed.contains("after"))
    }

    @Test
    fun `a labelled token is removed but its label is kept`() {
        val scrubbed = Redactor.scrub("POST failed: token=AbCdEf0123456789xyz")

        assertFalse(scrubbed.contains("AbCdEf0123456789xyz"))
        // The label survives so the reader can see what was removed; a bare mask
        // reads like a parsing fault rather than a deliberate redaction.
        assertTrue(scrubbed.contains("token="))
    }

    @Test
    fun `an authorization header value is removed`() {
        val scrubbed = Redactor.scrub("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9")

        assertFalse(scrubbed.contains("eyJhbGciOiJIUzI1NiJ9"))
    }

    @Test
    fun `ordinary text is left alone`() {
        val message = "checkin ok: state_version=4, applied 3 files, 0 errors"

        // A redactor that mangles normal lines gets turned off, and then it protects
        // nothing at all.
        assertEquals(message, Redactor.scrub(message))
    }
}
