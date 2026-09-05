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

import java.io.File
import java.io.IOException
import java.net.Socket
import java.security.KeyStore
import java.security.MessageDigest
import java.security.Principal
import java.security.PrivateKey
import java.security.cert.X509Certificate
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLContext
import javax.net.ssl.SSLSocket
import javax.net.ssl.TrustManagerFactory
import javax.net.ssl.X509KeyManager
import javax.net.ssl.X509TrustManager
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONObject
import com.taksolutions.atlasmdm.core.AgentConfig

/** Raised when the server answers with a non-success status. */
class ApiException(val code: Int, message: String) : IOException("HTTP $code: $message")

/**
 * HTTP client for the MDM server.
 *
 * Two clients are built. Enrollment runs over plain TLS, because the device has no
 * certificate yet and the enrollment token is the credential. Everything afterwards
 * runs over mTLS using the keystore-held identity.
 */
class ApiClient(private val config: AgentConfig) {

    private val baseUrl: String
        get() = config.serverUrl?.trimEnd('/') ?: error("no server URL configured")

    // ----------------------------------------------------------------------- //
    // TLS plumbing
    // ----------------------------------------------------------------------- //

    /**
     * Trust managers for the server's TLS certificate.
     *
     * A pinned CA is used when provisioning supplied one — the self-signed
     * development server. Otherwise the platform trust store applies, which is what
     * a real deployment with a publicly-issued certificate wants.
     */
    private fun trustManager(): X509TrustManager {
        val caPem = config.serverCaPem
        val factory = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm())

        if (caPem.isNullOrBlank()) {
            factory.init(null as KeyStore?)
        } else {
            val store = KeyStore.getInstance(KeyStore.getDefaultType()).apply {
                load(null)
                setCertificateEntry("takmdm-server-ca", DeviceIdentity.parseCertificate(caPem))
            }
            factory.init(store)
        }

        return factory.trustManagers.filterIsInstance<X509TrustManager>().first()
    }

    /**
     * Presents the keystore identity as a client certificate.
     *
     * Written by hand rather than via KeyManagerFactory: the private key is
     * non-exportable and lives in the AndroidKeyStore provider, which the default
     * factories do not reliably handle.
     */
    private fun keyManager(): X509KeyManager = object : X509KeyManager {
        override fun getClientAliases(keyType: String?, issuers: Array<out Principal>?) =
            arrayOf(DeviceIdentity.alias())

        override fun chooseClientAlias(
            keyType: Array<out String>?,
            issuers: Array<out Principal>?,
            socket: Socket?
        ) = DeviceIdentity.alias()

        override fun getCertificateChain(alias: String?): Array<X509Certificate>? =
            DeviceIdentity.certificateChain()

        override fun getPrivateKey(alias: String?): PrivateKey? = DeviceIdentity.privateKey()

        override fun getServerAliases(keyType: String?, issuers: Array<out Principal>?) = null
        override fun chooseServerAlias(
            keyType: String?,
            issuers: Array<out Principal>?,
            socket: Socket?
        ) = null
    }

    private fun buildClient(withClientCertificate: Boolean): OkHttpClient {
        val trust = trustManager()
        val context = SSLContext.getInstance("TLS").apply {
            init(
                if (withClientCertificate) arrayOf(keyManager()) else null,
                arrayOf(trust),
                null
            )
        }
        return OkHttpClient.Builder()
            .sslSocketFactory(context.socketFactory, trust)
            .connectTimeout(30, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .retryOnConnectionFailure(true)
            .build()
    }

    private val enrollClient: OkHttpClient by lazy { buildClient(withClientCertificate = false) }
    private val mtlsClient: OkHttpClient by lazy { buildClient(withClientCertificate = true) }

    /** Long-poll needs a client whose read timeout outlives the server's hold. */
    private fun waitClient(timeoutSeconds: Long): OkHttpClient =
        mtlsClient.newBuilder().readTimeout(timeoutSeconds + 15, TimeUnit.SECONDS).build()

    // ----------------------------------------------------------------------- //
    // Endpoints
    // ----------------------------------------------------------------------- //

    fun enroll(
        token: String,
        csrPem: String,
        serialNumber: String,
        model: String,
        osVersion: String,
        agentVersion: String,
        identifiers: org.json.JSONArray = org.json.JSONArray()
    ): JSONObject {
        val body = JSONObject()
            .put("token", token)
            .put("csr_pem", csrPem)
            .put("serial_number", serialNumber)
            .put("model", model)
            .put("os_version", osVersion)
            .put("agent_version", agentVersion)
            // Every identity this device can report, so re-enrolment matches on any
            // it has used before (R13).
            .put("identifiers", identifiers)

        val request = Request.Builder()
            .url("$baseUrl/api/v1/enroll")
            .post(body.toString().toRequestBody(JSON))
            .build()

        return enrollClient.newCall(request).execute().readJson()
    }

    fun checkin(payload: JSONObject): JSONObject {
        val request = Request.Builder()
            .url("$baseUrl/api/v1/device/checkin")
            .post(payload.toString().toRequestBody(JSON))
            .build()
        return mtlsClient.newCall(request).execute().readJson()
    }

    /**
     * Upload a diagnostic log bundle.
     *
     * Its own endpoint rather than a field on check-in: this body is up to a
     * megabyte and is sent a handful of times in a device's life, while check-in
     * runs every couple of minutes on a link assumed to be poor. Folding one into
     * the other would make every routine check-in carry the worst case.
     */
    fun uploadLogs(
        content: String,
        commandId: String?,
        agentVersion: String,
        truncated: Boolean
    ): JSONObject {
        val body = JSONObject()
            .put("content", content)
            .put("command_id", commandId ?: JSONObject.NULL)
            .put("agent_version", agentVersion)
            .put("truncated", truncated)

        val request = Request.Builder()
            .url("$baseUrl/api/v1/device/logs")
            .post(body.toString().toRequestBody(JSON))
            .build()
        return mtlsClient.newCall(request).execute().readJson()
    }

    /** Blocks until the server says to check in, or the hold expires. */
    fun waitForChange(stateVersion: Int, timeoutSeconds: Long): JSONObject {
        val request = Request.Builder()
            .url("$baseUrl/api/v1/device/wait?state_version=$stateVersion&timeout=$timeoutSeconds")
            .get()
            .build()
        return waitClient(timeoutSeconds).newCall(request).execute().readJson()
    }

    /**
     * Download an artifact, resuming if a partial file is already present.
     *
     * The hash is verified before the caller is told it succeeded, so a truncated or
     * corrupted transfer can never reach an installer.
     */
    fun downloadArtifact(sha256: String, destination: File): Boolean {
        destination.parentFile?.mkdirs()
        val existing = if (destination.exists()) destination.length() else 0L

        val builder = Request.Builder().url("$baseUrl/api/v1/device/artifacts/$sha256").get()
        if (existing > 0) builder.header("Range", "bytes=$existing-")

        mtlsClient.newCall(builder.build()).execute().use { response ->
            when {
                response.code == 416 -> {
                    // Already have the whole file, or the local copy is longer than
                    // the remote. Verification below decides which.
                }
                response.code == 206 -> appendBody(response, destination)
                response.isSuccessful -> {
                    destination.delete()
                    appendBody(response, destination)
                }
                else -> throw ApiException(response.code, response.message)
            }
        }

        if (sha256Of(destination) == sha256.lowercase()) return true

        // A mismatch means the partial file was stale or the transfer was corrupted.
        // Start clean rather than resuming onto bad bytes forever.
        destination.delete()
        return false
    }

    private fun appendBody(response: Response, destination: File) {
        response.body?.byteStream()?.use { input ->
            java.io.FileOutputStream(destination, destination.exists()).use { output ->
                input.copyTo(output, DEFAULT_BUFFER_SIZE)
            }
        }
    }

    private fun Response.readJson(): JSONObject = use {
        val text = body?.string().orEmpty()
        if (!isSuccessful) throw ApiException(code, text.ifBlank { message })
        if (text.isBlank()) JSONObject() else JSONObject(text)
    }

    companion object {
        private val JSON = "application/json; charset=utf-8".toMediaType()

        fun sha256Of(file: File): String {
            if (!file.exists()) return ""
            val digest = MessageDigest.getInstance("SHA-256")
            file.inputStream().use { stream ->
                val buffer = ByteArray(64 * 1024)
                while (true) {
                    val read = stream.read(buffer)
                    if (read <= 0) break
                    digest.update(buffer, 0, read)
                }
            }
            return digest.digest().joinToString("") { "%02x".format(it) }
        }
    }
}
