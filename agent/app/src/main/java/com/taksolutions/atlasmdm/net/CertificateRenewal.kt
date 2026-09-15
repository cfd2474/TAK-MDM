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

import com.taksolutions.atlasmdm.diag.AgentLog
import java.security.KeyPair
import java.util.Date
import java.util.concurrent.TimeUnit

/**
 * When to ask for a new certificate, and what to do with the answer (W174).
 *
 * Before this, a certificate was issued once at enrolment and never again. When
 * it expired the tablet had to be factory reset and re-provisioned by hand — and
 * the same was true whenever the *issuing* CA expired, which is what made
 * rotating a certificate authority a fleet-wide event instead of a maintenance
 * task.
 *
 * ⚠️ **The key never changes.** The identity key lives in the Android Keystore,
 * StrongBox where the hardware has it, and cannot be exported. Renewal asks for a
 * new *certificate* over the same key, which is what makes it safe to run
 * unattended: there is no swap to get half-done, and a renewal that fails leaves
 * the working certificate exactly where it was.
 *
 * ⚠️ **The decision is the server's.** The window arrives on every check-in rather
 * than being compiled in, so an operator can change it without shipping an agent —
 * which matters because a device that renews too late is a device that cannot be
 * reached to be corrected.
 */
object CertificateRenewal {

    /** Window used before a check-in has ever stated one. */
    const val DEFAULT_WINDOW_DAYS = 30

    /**
     * ⚠️ A floor, not a default. A server that sent `0` — through a bug, or a
     * value an operator typed — would mean "renew only once it has expired", and
     * a device cannot renew a certificate it can no longer authenticate with.
     * That is unrecoverable without a factory reset, so it is refused here.
     */
    const val MINIMUM_WINDOW_DAYS = 1

    /** ⚠️ And a ceiling: a window longer than the certificate means renewing on
     * every single check-in, which is a busy loop against the CA. */
    const val MAXIMUM_WINDOW_DAYS = 3650

    fun windowDays(stated: Int?): Int {
        val value = stated ?: DEFAULT_WINDOW_DAYS
        return value.coerceIn(MINIMUM_WINDOW_DAYS, MAXIMUM_WINDOW_DAYS)
    }

    /**
     * Is this certificate close enough to expiry to replace?
     *
     * Expressed in days remaining rather than as a fraction of life, so changing
     * the issued validity does not silently move when the whole fleet renews.
     */
    fun isDue(notAfter: Date, now: Long, windowDays: Int): Boolean {
        val remaining = notAfter.time - now
        return remaining <= TimeUnit.DAYS.toMillis(windowDays.toLong())
    }

    /**
     * How long to wait before trying again after a failure.
     *
     * ⚠️ Backs off, because the common reason renewal fails is that the server is
     * unreachable — and a fleet that retried on every sync would turn a brief
     * outage into a stampede the moment it came back. The window is measured in
     * days; there is no hurry within it.
     */
    fun retryDelayMillis(consecutiveFailures: Int): Long {
        val hours = when {
            consecutiveFailures <= 1 -> 1L
            consecutiveFailures == 2 -> 4L
            else -> 12L
        }
        return TimeUnit.HOURS.toMillis(hours)
    }

    /**
     * Run a renewal if one is due. Returns true when a new certificate was
     * installed.
     *
     * Every failure path leaves the existing certificate untouched: the device
     * keeps working and tries again later. The only thing that changes state is
     * [DeviceIdentity.installCertificate], which itself refuses a certificate
     * issued for a different key.
     */
    fun renewIfDue(
        identity: DeviceIdentity = DeviceIdentity,
        api: ApiClient,
        serialNumber: String,
        windowDays: Int,
        now: Long = System.currentTimeMillis(),
    ): Boolean {
        val chain = identity.certificateChain() ?: return false
        val current = chain.first()

        if (!isDue(current.notAfter, now, windowDays)) return false

        val privateKey = identity.privateKey() ?: run {
            AgentLog.w(TAG, "certificate is due for renewal but the key is gone")
            return false
        }

        val daysLeft = TimeUnit.MILLISECONDS.toDays(current.notAfter.time - now)
        AgentLog.i(TAG, "certificate expires in ${daysLeft}d; renewing")

        return runCatching {
            // ⚠️ The *existing* public key, taken from the certificate we hold.
            // The server refuses a request for any other, and rightly: a
            // certificate for a key this device does not have is one it would be
            // obliged to throw away.
            val csr = identity.createCsrPem(
                KeyPair(current.publicKey, privateKey), serialNumber
            )
            val answer = api.renewCertificate(csr)
            identity.installCertificate(answer.certificatePem, answer.caPem)

            val installed = identity.certificateChain()?.first()
            AgentLog.i(
                TAG,
                "certificate renewed; now expires ${installed?.notAfter}",
            )
            true
        }.getOrElse { error ->
            // ⚠️ Warn, never throw. A failed renewal is not a failed sync — the
            // device still holds a working certificate and there are days of
            // window left. Propagating would abort the rest of the reconcile and
            // turn a retryable problem into an unmanaged device.
            AgentLog.w(TAG, "certificate renewal failed; keeping the current one", error)
            false
        }
    }

    private const val TAG = "CertificateRenewal"
}
