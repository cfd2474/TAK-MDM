package org.takmdm.agent.net

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Log
import java.io.ByteArrayInputStream
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
            Log.w(TAG, "StrongBox unavailable, falling back to TEE-backed key", e)
            generate(useStrongBox = false)
        }
    }

    private fun generate(useStrongBox: Boolean): KeyPair {
        val spec = KeyGenParameterSpec.Builder(
            ALIAS,
            KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY
        )
            .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
            .setDigests(KeyProperties.DIGEST_SHA256)
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
    fun createCsrPem(keyPair: KeyPair, serialNumber: String): String {
        // The server discards this subject and builds its own, but a CSR must carry
        // one, and the serial makes an intercepted request self-describing.
        val subject = X500NameBuilder(BCStyle.INSTANCE)
            .addRDN(BCStyle.CN, serialNumber)
            .build()

        val signer = JcaContentSignerBuilder("SHA256withECDSA")
            // The private key lives in the keystore and cannot be exported, so the
            // signing operation has to run inside that provider.
            .setProvider(ANDROID_KEYSTORE)
            .build(keyPair.private)

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
    fun installCertificate(certificatePem: String, caPem: String?) {
        val store = keyStore()
        val privateKey = store.getKey(ALIAS, null) as? PrivateKey
            ?: error("no private key at alias $ALIAS")

        val chain = buildList {
            add(parseCertificate(certificatePem))
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
