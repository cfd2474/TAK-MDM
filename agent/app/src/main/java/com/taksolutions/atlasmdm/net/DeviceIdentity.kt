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

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import com.taksolutions.atlasmdm.diag.AgentLog
import java.io.ByteArrayInputStream
import android.security.keystore.KeyInfo
import java.security.KeyFactory
import java.security.KeyPair
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.PrivateKey
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate
import java.security.spec.ECGenParameterSpec
import org.bouncycastle.asn1.x500.X500NameBuilder
import org.bouncycastle.asn1.x500.style.BCStyle
import org.bouncycastle.operator.jcajce.JcaContentSignerBuilder
import org.bouncycastle.pkcs.jcajce.JcaPKCS10CertificationRequestBuilder
import org.bouncycastle.util.io.pem.PemObject
import org.bouncycastle.util.io.pem.PemWriter

/**
 * The device's cryptographic identity.
 *
 * An EC P-256 keypair is generated inside the Android Keystore, backed by StrongBox
 * where the hardware provides it. The private key is never extractable, so this
 * identity cannot be copied off a lost device the way a bearer token could — and
 * there is nothing to expire while a device is dark for a month.
 */
object DeviceIdentity {

    private const val TAG = "DeviceIdentity"
    private const val ALIAS = "takmdm-device-identity"
    private const val ANDROID_KEYSTORE = "AndroidKeyStore"

    private fun keyStore(): KeyStore =
        KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }

    fun hasKey(): Boolean = keyStore().containsAlias(ALIAS)

    fun hasCertificate(): Boolean = certificateChain() != null

    /**
     * Create the keypair, preferring StrongBox and falling back to the TEE.
     *
     * StrongBox is a separate security chip and is not present on every model, so a
     * failure here is a hardware fact rather than an error — but it must be a
     * deliberate fallback, never a silent drop to a software key.
     */
    fun generateKeyPair(): KeyPair {
        deleteIdentity()
        return try {
            generate(useStrongBox = true)
        } catch (e: Exception) {
            AgentLog.w(TAG, "StrongBox unavailable, falling back to TEE-backed key", e)
            generate(useStrongBox = false)
        }
    }

    private fun generate(useStrongBox: Boolean): KeyPair {
        val spec = KeyGenParameterSpec.Builder(
            ALIAS,
            KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY
        )
            .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
            // Broad on purpose. A TLS handshake picks its own signature algorithm,
            // and a key restricted to SHA-256 alone fails the moment the server
            // negotiates anything else — as an opaque SSLHandshakeException with no
            // indication that the key is the problem. DIGEST_NONE matters too:
            // some TLS stacks hash first and ask the key to sign raw bytes.
            .setDigests(
                KeyProperties.DIGEST_NONE,
                KeyProperties.DIGEST_SHA256,
                KeyProperties.DIGEST_SHA384,
                KeyProperties.DIGEST_SHA512,
            )
            // No user authentication requirement: the agent must work on a locked,
            // unattended device.
            .setUserAuthenticationRequired(false)
            .apply { if (useStrongBox) setIsStrongBoxBacked(true) }
            .build()

        return KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, ANDROID_KEYSTORE)
            .apply { initialize(spec) }
            .generateKeyPair()
    }

    /** A PKCS#10 CSR proving possession of the keystore-held private key. */
    /**
     * Where the device's private key actually lives, asked of the key itself.
     *
     * Generation prefers StrongBox and falls back to the TEE, and the fallback is a
     * warning logged once at enrolment — long gone by the time anyone wonders. The
     * answer that matters is what the key *is* now, not what was attempted, so this
     * reads `KeyInfo` rather than trusting a record of the attempt.
     */
    fun keySecurityLevel(): String {
        val store = keyStore()
        val key = runCatching { store.getKey(ALIAS, null) as? PrivateKey }.getOrNull()
            ?: return "no key at alias $ALIAS"

        return runCatching {
            val factory = KeyFactory.getInstance(key.algorithm, ANDROID_KEYSTORE)
            val info = factory.getKeySpec(key, KeyInfo::class.java)

            // getSecurityLevel() is API 31+ and is the only call that distinguishes
            // StrongBox from the TEE. isInsideSecureHardware() only says "not
            // software", which cannot answer this question.
            val level = runCatching { info.securityLevel }.getOrNull()
            val named = when (level) {
                KeyProperties.SECURITY_LEVEL_STRONGBOX -> "STRONGBOX"
                KeyProperties.SECURITY_LEVEL_TRUSTED_ENVIRONMENT -> "TRUSTED_ENVIRONMENT (TEE)"
                KeyProperties.SECURITY_LEVEL_SOFTWARE -> "SOFTWARE"
                KeyProperties.SECURITY_LEVEL_UNKNOWN -> "UNKNOWN"
                KeyProperties.SECURITY_LEVEL_UNKNOWN_SECURE -> "UNKNOWN_SECURE"
                else -> "unreported ($level)"
            }
            @Suppress("DEPRECATION")
            "$named, insideSecureHardware=${info.isInsideSecureHardware}"
        }.getOrElse { "could not read KeyInfo: ${it.javaClass.simpleName}: ${it.message}" }
    }

    fun createCsrPem(keyPair: KeyPair, serialNumber: String): String {
        // The server discards this subject and builds its own, but a CSR must carry
        // one, and the serial makes an intercepted request self-describing.
        val subject = X500NameBuilder(BCStyle.INSTANCE)
            .addRDN(BCStyle.CN, serialNumber)
            .build()

        // Deliberately no setProvider().
        //
        // The AndroidKeyStore provider supplies KeyStore and KeyPairGenerator but
        // *not* Signature — those live in a separate provider named
        // "AndroidKeyStoreBCWorkaround". Naming AndroidKeyStore explicitly
        // therefore fails with "no such algorithm: SHA256WITHECDSA", which is what
        // silently stopped every enrollment.
        //
        // Leaving the provider unset uses JCA's delayed provider selection: the
        // provider is chosen at initSign() time from the key itself, which resolves
        // to the right one for a non-exportable keystore key.
        val signer = JcaContentSignerBuilder("SHA256withECDSA").build(keyPair.private)

        val csr = JcaPKCS10CertificationRequestBuilder(subject, keyPair.public).build(signer)

        return java.io.StringWriter().use { writer ->
            PemWriter(writer).use { it.writeObject(PemObject("CERTIFICATE REQUEST", csr.encoded)) }
            writer.toString()
        }
    }

    /**
     * Attach the issued certificate chain to the existing keystore alias.
     *
     * The private key stays exactly where it was; only the chain is replaced. This
     * is the supported way to install a real certificate over the self-signed
     * placeholder that key generation creates.
     */
    /**
     * ⚠️ Refuses a certificate whose public key is not this device's.
     *
     * Storing one leaves an identity that cannot complete a TLS handshake -
     * nginx reports "bad signature" and the device is unreachable for good,
     * because it can no longer check in to be told anything. Failing here
     * instead leaves the previous identity intact and says why.
     */
    fun installCertificate(certificatePem: String, caPem: String?) {
        val store = keyStore()
        val privateKey = store.getKey(ALIAS, null) as? PrivateKey
            ?: error("no private key at alias $ALIAS")

        val leaf = parseCertificate(certificatePem)

        // ⚠️ The certificate has to belong to the key that is about to be paired
        // with it. A hardware-backed private key cannot be read back to compare,
        // so the check is against the public key the keystore holds for this
        // alias - which is the one the CSR carried.
        val ours = store.getCertificate(ALIAS)?.publicKey
        if (ours != null && ours != leaf.publicKey) {
            error(
                "the issued certificate is for a different key than this device " +
                    "holds; refusing to install it. Enrolling twice at once causes " +
                    "this, and storing it would make the device unreachable."
            )
        }

        val chain = buildList {
            add(leaf)
            caPem?.let { add(parseCertificate(it)) }
        }.toTypedArray()

        store.setKeyEntry(ALIAS, privateKey, null, chain)
    }

    fun certificateChain(): Array<X509Certificate>? {
        val store = keyStore()
        if (!store.containsAlias(ALIAS)) return null
        val chain = store.getCertificateChain(ALIAS) ?: return null
        val certificates = chain.filterIsInstance<X509Certificate>()
        // Key generation leaves a self-signed placeholder. Treat that as "no
        // certificate yet" rather than presenting it and failing the handshake.
        if (certificates.isEmpty()) return null
        val leaf = certificates.first()
        if (leaf.subjectX500Principal == leaf.issuerX500Principal) return null
        return certificates.toTypedArray()
    }

    fun privateKey(): PrivateKey? = keyStore().getKey(ALIAS, null) as? PrivateKey

    fun alias(): String = ALIAS

    fun deleteIdentity() {
        val store = keyStore()
        if (store.containsAlias(ALIAS)) store.deleteEntry(ALIAS)
    }

    fun parseCertificate(pem: String): X509Certificate =
        CertificateFactory.getInstance("X.509")
            .generateCertificate(ByteArrayInputStream(pem.toByteArray())) as X509Certificate
}
