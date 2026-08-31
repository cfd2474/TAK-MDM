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

package org.takmdm.agent.core

import android.util.Base64
import android.util.Log
import java.security.KeyFactory
import java.security.Signature
import java.security.spec.X509EncodedKeySpec
import org.json.JSONObject

/**
 * Verifies the Ed25519 signature over a desired-state bundle.
 *
 * The signature is checked independently of TLS, so a compromised proxy cannot
 * rewrite policy in flight, and a bundle delivered out of band (a LAN relay, a file)
 * is just as trustworthy as one fetched directly.
 *
 * The public key is pinned at enrollment — the one exchange already authenticated
 * by a secret an operator handed over.
 */
object BundleVerifier {

    private const val TAG = "BundleVerifier"

    // DER prefix for an Ed25519 SubjectPublicKeyInfo. The server publishes the raw
    // 32-byte key, but KeyFactory wants SPKI, so it is wrapped here rather than
    // making the server emit a format only this client needs.
    private val SPKI_PREFIX = byteArrayOf(
        0x30, 0x2a, 0x30, 0x05, 0x06, 0x03, 0x2b, 0x65, 0x70, 0x03, 0x21, 0x00
    )

    fun verify(document: JSONObject, signatureBase64: String, publicKeyBase64: String): Boolean {
        return try {
            val raw = Base64.decode(publicKeyBase64, Base64.DEFAULT)
            require(raw.size == 32) { "Ed25519 public key must be 32 bytes, got ${raw.size}" }

            val publicKey = KeyFactory.getInstance("Ed25519")
                .generatePublic(X509EncodedKeySpec(SPKI_PREFIX + raw))

            Signature.getInstance("Ed25519").run {
                initVerify(publicKey)
                update(CanonicalJson.encode(document))
                verify(Base64.decode(signatureBase64, Base64.DEFAULT))
            }
        } catch (e: Exception) {
            // Never treat a verification error as a pass. A malformed key or
            // signature must reject the bundle, not skip the check.
            Log.e(TAG, "bundle signature verification failed", e)
            false
        }
    }
}
