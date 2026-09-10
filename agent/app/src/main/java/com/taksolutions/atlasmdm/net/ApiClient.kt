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
import com.taksolutions.atlasmdm.diag.AgentLog

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

    /**
     * Ask the server whether [pin] is this install's provisioning bypass code.
     *
     * ⚠️ **`enrollClient`, not `mtlsClient`.** This is called from the setup
     * wizard, before the device has any identity — the same position
     * [enroll] is in, and for the same reason the enrollment token is what
     * authorizes it.
     *
     * ⚠️ **The PIN is never stored, cached or logged**, here or anywhere else.
     * It is a fixed per-install secret, so a copy left in an agent preference
     * file or a log bundle outlives the one moment it was needed.
     *
     * Returns null when the server could not be reached or did not answer
     * usefully — a distinct outcome from "wrong code", because the operator can
     * do something about one and not the other.
     */
    fun checkBypassPin(token: String, pin: String): BypassPinAnswer? {
        val body = JSONObject().put("secret", token).put("pin", pin)
        val request = Request.Builder()
            .url("$baseUrl/api/v1/provisioning/bypass-pin")
            .post(body.toString().toRequestBody(JSON))
            .build()
        return try {
            val json = enrollClient.newCall(request).execute().readJson()
            BypassPinAnswer(
                accepted = json.optBoolean("accepted", false),
                attemptsRemaining = json.optInt("attempts_remaining", -1),
            )
        } catch (e: Exception) {
            // Includes a 404 for an unusable enrollment token, which is not
            // "wrong PIN" either — the operator needs to know the difference.
            AgentLog.w(TAG, "bypass PIN check could not be completed: ${e.message}")
            null
        }
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
     * Download an artifact, resuming if a partial download is already present.
     *
     * The hash is verified before the caller is told it succeeded, so a truncated or
     * corrupted transfer can never reach an installer.
     *
     * ⚠️ **Two reconcile passes can run at once**, and before this they downloaded
     * the same artifact to the same path: one writing from offset 0 while the other
     * appended a resumed range. That produces a file of exactly the right *length*
     * whose bytes are interleaved garbage, so the only symptom is a hash mismatch —
     * which reads as a corrupt download and sends the agent round again, forever.
     * It cost five 20 MB downloads per agent update and made every rollout look
     * broken (observed against builds 51, 57, 59 and 60).
     *
     * Two things prevent it. Downloads of a given artifact are **serialised** on the
     * hash, so a second pass waits and then finds the finished file. And bytes land
     * in a `.part` file that is renamed into place **only after it verifies**, so
     * the destination never holds anything unverified and a caller that checks it
     * cannot see a half-written file.
     */
    /**
     * Fetch an app icon into [destination]. Returns false if it could not be had.
     *
     * Unlike an artifact this has no hash to verify against — it is not
     * content-addressed — so the only check is that the body decodes as an image,
     * which the caller does. A missing icon is an ordinary outcome, not an error:
     * an app whose icon is a vector drawable has none to send (W53).
     */
    fun downloadIcon(path: String, destination: File): Boolean {
        destination.parentFile?.mkdirs()
        val request = Request.Builder().url("$baseUrl$path").get().build()
        return runCatching {
            mtlsClient.newCall(request).execute().use { response ->
                if (!response.isSuccessful) return false
                val body = response.body ?: return false
                val part = File(destination.parentFile, "${destination.name}.part")
                body.byteStream().use { input ->
                    java.io.FileOutputStream(part).use { output ->
                        input.copyTo(output, DEFAULT_BUFFER_SIZE)
                    }
                }
                // Same rename-after-write discipline as an artifact: a reader must
                // never find a half-written file at the final path.
                destination.delete()
                part.renameTo(destination)
            }
        }.getOrDefault(false)
    }

    /**
     * @param onProgress bytes-so-far and total, for a caller drawing a bar. Called
     *   on the calling (background) thread, once per buffer.
     * @param isCancelled polled between buffers. A cancelled transfer leaves its
     *   `.part` behind on purpose, so resuming later costs only what is missing.
     */
    fun downloadArtifact(
        sha256: String,
        destination: File,
        onProgress: ((Long, Long) -> Unit)? = null,
        isCancelled: (() -> Boolean)? = null,
    ): Boolean =
        synchronized(downloadLockFor(sha256)) {
            // A concurrent pass may have finished it while this one waited.
            if (destination.exists() && sha256Of(destination) == sha256.lowercase()) return true
            downloadLocked(sha256, destination, onProgress, isCancelled)
        }

    /** Thrown to unwind a transfer the caller asked to stop. */
    class TransferCancelled : java.io.IOException("cancelled")

    private fun downloadLocked(
        sha256: String,
        destination: File,
        onProgress: ((Long, Long) -> Unit)? = null,
        isCancelled: (() -> Boolean)? = null,
    ): Boolean {
        destination.parentFile?.mkdirs()
        val part = File(destination.parentFile, "${destination.name}.part")
        val existing = if (part.exists()) part.length() else 0L

        val builder = Request.Builder().url("$baseUrl/api/v1/device/artifacts/$sha256").get()
        if (existing > 0) builder.header("Range", "bytes=$existing-")

        var expected = -1L
        var written = 0L
        mtlsClient.newCall(builder.build()).execute().use { response ->
            expected = response.body?.contentLength() ?: -1L
            when {
                response.code == 416 -> {
                    // Already hold the whole file, or the local copy is longer than
                    // the remote. Verification below decides which.
                }
                response.code == 206 ->
                    written = appendBody(response, part, true, existing, onProgress, isCancelled)
                response.isSuccessful -> {
                    part.delete()
                    written = appendBody(response, part, false, 0L, onProgress, isCancelled)
                }
                else -> throw ApiException(response.code, response.message)
            }
        }

        // A body that stops early does **not** raise: `copyTo` simply returns when
        // the stream ends. Without this the only evidence was a hash mismatch, which
        // is indistinguishable from corruption and hides the real cause.
        if (expected >= 0 && written != expected) {
            AgentLog.w(TAG, "artifact $sha256: got $written of $expected bytes")
            part.delete()
            return false
        }

        if (sha256Of(part) == sha256.lowercase()) {
            destination.delete()
            if (part.renameTo(destination)) return true
            AgentLog.w(TAG, "artifact $sha256: could not move the verified download into place")
        }

        // Stale or corrupt: start clean rather than resuming onto bad bytes forever.
        part.delete()
        return false
    }

    /**
     * Copy the body out, returning the bytes written so a short one is detectable.
     *
     * ⚠️ An explicit loop rather than `copyTo`, which can neither report progress
     * nor be interrupted. [alreadyOnDisk] is added to the running total so a
     * resumed transfer measures the **whole file**, not the remainder — a bar that
     * jumps to 70% and crawls is worse than no bar.
     */
    private fun appendBody(
        response: Response,
        destination: File,
        append: Boolean,
        alreadyOnDisk: Long,
        onProgress: ((Long, Long) -> Unit)?,
        isCancelled: (() -> Boolean)?,
    ): Long {
        val body = response.body ?: return 0L
        val total = body.contentLength().let { if (it >= 0) it + alreadyOnDisk else -1L }
        var written = 0L

        body.byteStream().use { input ->
            java.io.FileOutputStream(destination, append).use { output ->
                val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
                while (true) {
                    if (isCancelled?.invoke() == true) throw TransferCancelled()
                    val read = input.read(buffer)
                    if (read <= 0) break
                    output.write(buffer, 0, read)
                    written += read
                    onProgress?.invoke(alreadyOnDisk + written, total)
                }
            }
        }
        return written
    }

    private fun Response.readJson(): JSONObject = use {
        val text = body?.string().orEmpty()
        if (!isSuccessful) throw ApiException(code, text.ifBlank { message })
        if (text.isBlank()) JSONObject() else JSONObject(text)
    }

    /** What the server said about a typed bypass PIN. */
    data class BypassPinAnswer(val accepted: Boolean, val attemptsRemaining: Int)

    companion object {
        private const val TAG = "ApiClient"
        private val JSON = "application/json; charset=utf-8".toMediaType()

        /**
         * One lock per artifact hash, shared by every `ApiClient` in the process.
         *
         * Held for the duration of a download so two reconcile passes cannot write
         * the same file at once. Keyed by hash rather than a single global lock so
         * unrelated downloads still overlap; entries are never evicted, which is
         * fine — a device sees a handful of distinct artifacts, and each key is a
         * 64-character string.
         */
        private val downloadLocks = java.util.concurrent.ConcurrentHashMap<String, Any>()

        private fun downloadLockFor(sha256: String): Any =
            downloadLocks.computeIfAbsent(sha256.lowercase()) { Any() }

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
