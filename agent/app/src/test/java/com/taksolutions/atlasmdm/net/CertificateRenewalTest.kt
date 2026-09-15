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

package com.taksolutions.atlasmdm.net

import java.util.Date
import java.util.concurrent.TimeUnit
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * When a device decides to replace its own certificate (W174).
 *
 * ⚠️ The dangerous direction is renewing **too late**. A certificate that has
 * fully expired cannot authenticate the request that would replace it, so the
 * device is unreachable and needs a factory reset — the exact outcome this whole
 * feature exists to abolish. Everything here leans early.
 */
class CertificateRenewalTest {

    private val now = 1_800_000_000_000L

    private fun inDays(days: Long) = Date(now + TimeUnit.DAYS.toMillis(days))

    // ----------------------------------------------------------------------- //
    // When
    // ----------------------------------------------------------------------- //

    @Test
    fun `a fresh certificate is left alone`() {
        assertFalse(CertificateRenewal.isDue(inDays(800), now, windowDays = 30))
    }

    @Test
    fun `one inside the window is renewed`() {
        assertTrue(CertificateRenewal.isDue(inDays(20), now, windowDays = 30))
    }

    @Test
    fun `the boundary renews rather than waiting`() {
        // ⚠️ Exactly at the window renews. Waiting for "less than" would mean a
        // device that syncs once a day could skip its only chance.
        assertTrue(CertificateRenewal.isDue(inDays(30), now, windowDays = 30))
    }

    @Test
    fun `an already expired certificate still reads as due`() {
        // It cannot succeed — the request needs a valid certificate — but the
        // attempt and its log line are how an operator finds out.
        assertTrue(CertificateRenewal.isDue(inDays(-5), now, windowDays = 30))
    }

    // ----------------------------------------------------------------------- //
    // ⚠️ The window the server states is not blindly obeyed
    // ----------------------------------------------------------------------- //

    @Test
    fun `a stated window is used`() {
        assertEquals(45, CertificateRenewal.windowDays(45))
    }

    @Test
    fun `no stated window falls back to the default`() {
        assertEquals(CertificateRenewal.DEFAULT_WINDOW_DAYS, CertificateRenewal.windowDays(null))
    }

    @Test
    fun `a zero window is refused because it is unrecoverable`() {
        // ⚠️ Zero means "renew once expired", and a device cannot renew a
        // certificate it can no longer authenticate with. A server bug, or a
        // number an operator typed, would brick the fleet one device at a time.
        assertEquals(CertificateRenewal.MINIMUM_WINDOW_DAYS, CertificateRenewal.windowDays(0))
    }

    @Test
    fun `a negative window is refused`() {
        assertEquals(CertificateRenewal.MINIMUM_WINDOW_DAYS, CertificateRenewal.windowDays(-30))
    }

    @Test
    fun `an absurd window is capped`() {
        // A window longer than the certificate means renewing on every check-in,
        // which is a busy loop against the CA.
        assertEquals(CertificateRenewal.MAXIMUM_WINDOW_DAYS, CertificateRenewal.windowDays(99_999))
    }

    // ----------------------------------------------------------------------- //
    // Retrying
    // ----------------------------------------------------------------------- //

    @Test
    fun `the first retry is soon and later ones are not`() {
        val first = CertificateRenewal.retryDelayMillis(1)
        val second = CertificateRenewal.retryDelayMillis(2)
        val later = CertificateRenewal.retryDelayMillis(9)

        assertTrue(first < second)
        assertTrue(second < later)
    }

    @Test
    fun `backing off stays well inside a thirty day window`() {
        // ⚠️ The backoff must never grow past the window, or a device that failed
        // a few times would stop trying until after it had expired.
        val longest = CertificateRenewal.retryDelayMillis(100)

        assertTrue(longest < TimeUnit.DAYS.toMillis(1))
    }
}
