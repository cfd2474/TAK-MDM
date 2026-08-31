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

package org.takmdm.agent.sync

import android.content.Context
import android.os.Build
import android.util.Log
import java.io.File
import org.json.JSONArray
import org.json.JSONObject
import org.takmdm.agent.core.AgentConfig
import org.takmdm.agent.core.BundleVerifier
import org.takmdm.agent.files.FileDeployer
import org.takmdm.agent.install.AppInstaller
import org.takmdm.agent.net.ApiClient
import org.takmdm.agent.net.DeviceIdentity
import org.takmdm.agent.policy.PolicyApplier

/** Outcome of one reconciliation pass. */
data class SyncOutcome(
    val stateVersion: Int,
    val appliedStateVersion: Int?,
    val errors: List<String>
)

/**
 * Converges the device onto the desired state.
 *
 * Declarative, not a command replay: the agent diffs what the server wants against
 * what the device has and computes its own actions. A device dark for three weeks
 * receives one document and catches up, rather than replaying a backlog whose
 * intermediate steps have been overtaken (D5).
 */
class Reconciler(private val context: Context) {

    private val config = AgentConfig(context)
    private val api = ApiClient(config)
    private val policyApplier = PolicyApplier(context)
    private val installer = AppInstaller(context)
    private val deployer = FileDeployer(context, config)

    private val cacheDir: File by lazy {
        File(context.cacheDir, "artifacts").apply { mkdirs() }
    }

    // ----------------------------------------------------------------------- //
    // Enrollment
    // ----------------------------------------------------------------------- //

    fun enrollIfNeeded(): Boolean {
        if (config.isEnrolled && DeviceIdentity.hasCertificate()) return true

        val token = config.enrollmentToken
        val serverUrl = config.serverUrl
        if (token.isNullOrBlank() || serverUrl.isNullOrBlank()) {
            Log.w(TAG, "no enrollment token or server URL; awaiting provisioning")
            return false
        }

        return runCatching {
            val serial = serialNumber()
            val keyPair = DeviceIdentity.generateKeyPair()
            val csr = DeviceIdentity.createCsrPem(keyPair, serial)

            val response = api.enroll(
                token = token,
                csrPem = csr,
                serialNumber = serial,
                model = Build.MODEL,
                osVersion = Build.VERSION.RELEASE,
                agentVersion = AGENT_VERSION
            )

            DeviceIdentity.installCertificate(
                response.getString("certificate_pem"),
                response.optString("ca_certificate_pem").takeIf { it.isNotBlank() }
            )
            config.deviceId = response.getString("device_id")
            config.bundleKeyBase64 = response.optString("bundle_signing_public_key")
            // The token is single-use and no longer needed; keeping it would leave a
            // usable enrollment credential on the device.
            config.enrollmentToken = null

            Log.i(TAG, "enrolled as ${config.deviceId}")
            true
        }.getOrElse {
            Log.e(TAG, "enrollment failed", it)
            false
        }
    }

    private fun serialNumber(): String = runCatching {
        // Requires READ_PHONE_STATE or Device Owner privilege; as Device Owner this
        // returns the real hardware serial, which is what re-enrollment matches on.
        Build.getSerial()
    }.getOrNull()?.takeIf { it.isNotBlank() && it != Build.UNKNOWN }
        ?: "${Build.MODEL}-${android.provider.Settings.Secure.getString(context.contentResolver, android.provider.Settings.Secure.ANDROID_ID)}"

    // ----------------------------------------------------------------------- //
    // Check-in and convergence
    // ----------------------------------------------------------------------- //

    fun sync(): SyncOutcome {
        if (!enrollIfNeeded()) {
            return SyncOutcome(config.stateVersion, null, listOf("not enrolled"))
        }

        val request = JSONObject()
            .put("state_version", config.stateVersion)
            .put("applied_state_version", config.appliedStateVersion)
            .put("agent_version", AGENT_VERSION)
            .put("os_version", Build.VERSION.RELEASE)
            .put("applied_optional_files", JSONArray(config.selectedOptionalFiles.toList()))

        val response = api.checkin(request)
        val serverVersion = response.optInt("state_version", config.stateVersion)

        val bundle = response.optJSONObject("desired_state")
        if (bundle != null) {
            val signature = response.optString("signature")
            val key = config.bundleKeyBase64
            if (key.isNullOrBlank() || !BundleVerifier.verify(bundle, signature, key)) {
                // Refuse rather than apply. An unverified bundle is exactly what the
                // signature exists to catch.
                return SyncOutcome(
                    serverVersion, null, listOf("desired-state signature did not verify")
                )
            }
            config.cachedDesiredState = bundle.toString()
            config.stateVersion = serverVersion
        }

        val desired = config.cachedDesiredState?.let { JSONObject(it) }
            ?: return SyncOutcome(serverVersion, null, emptyList())

        val errors = applyDesiredState(desired)
        if (errors.isEmpty()) {
            config.appliedStateVersion = config.stateVersion
        }

        return SyncOutcome(config.stateVersion, config.appliedStateVersion, errors)
    }

    fun applyDesiredState(desired: JSONObject): List<String> {
        val errors = mutableListOf<String>()
        errors += policyApplier.apply(desired.optJSONObject("policy") ?: JSONObject())
        errors += reconcileApps(desired.optJSONArray("apps") ?: JSONArray())
        errors += reconcileFiles(desired.optJSONObject("files") ?: JSONObject())
        return errors
    }

    // ----------------------------------------------------------------------- //
    // Apps
    // ----------------------------------------------------------------------- //

    private fun reconcileApps(apps: JSONArray): List<String> {
        val errors = mutableListOf<String>()

        for (index in 0 until apps.length()) {
            val app = apps.optJSONObject(index) ?: continue
            val packageName = app.optString("package_name")

            if (!app.optBoolean("available", false)) {
                errors += "$packageName: required but nothing uploaded for it"
                continue
            }

            val desiredVersion = app.optLong("version_code", -1)
            val installed = installer.installedVersionCode(packageName)
            if (installed != null && installed >= desiredVersion) continue

            val files = app.optJSONArray("files") ?: continue
            val parts = mutableListOf<File>()
            var downloadFailed = false

            // Base first: PackageInstaller needs it before the splits.
            val ordered = (0 until files.length())
                .mapNotNull { files.optJSONObject(it) }
                .sortedBy { if (it.optString("role") == "base") 0 else 1 }

            for (part in ordered) {
                if (part.optString("role") == "obb") continue
                val sha = part.optString("sha256")
                val target = File(cacheDir, sha)
                if (!downloadArtifact(sha, target)) {
                    errors += "$packageName: download of $sha failed verification"
                    downloadFailed = true
                    break
                }
                parts += target
            }
            if (downloadFailed) continue

            val result = installer.install(packageName, parts)
            if (result.success) {
                errors += policyApplier.grantRuntimePermissions(packageName)
            } else {
                errors += "$packageName: ${result.message}"
            }
        }
        return errors
    }

    // ----------------------------------------------------------------------- //
    // Files
    // ----------------------------------------------------------------------- //

    private fun reconcileFiles(files: JSONObject): List<String> {
        val errors = mutableListOf<String>()

        val required = files.optJSONArray("required") ?: JSONArray()
        for (index in 0 until required.length()) {
            required.optJSONObject(index)?.let { errors += applyFile(it, required = true) }
        }

        // Optional items are applied only where the user chose them (F4).
        val available = files.optJSONArray("available") ?: JSONArray()
        val selected = config.selectedOptionalFiles
        for (index in 0 until available.length()) {
            val entry = available.optJSONObject(index) ?: continue
            if (entry.optString("file_id") in selected) {
                errors += applyFile(entry, required = false)
            }
        }

        return errors
    }

    private fun applyFile(entry: JSONObject, required: Boolean): List<String> {
        val fileId = entry.optString("file_id")

        if (!entry.optBoolean("available", false)) {
            return if (required) listOf("$fileId: referenced by policy but not in the catalogue")
            else emptyList()
        }

        val sha = entry.optString("sha256")
        val key = deployer.stateKey(entry)
        // Already placed this exact content at this destination. Content addressing
        // makes "unchanged" cheap to determine and skips the download entirely.
        if (config.appliedFileHash(key) == sha) return emptyList()

        val payload = File(cacheDir, sha)
        if (!downloadArtifact(sha, payload)) {
            return listOf("$fileId: download failed verification")
        }

        val failures = deployer.deploy(entry, payload)
        if (failures.isEmpty()) config.recordAppliedFile(key, sha)
        return failures
    }

    private fun downloadArtifact(sha256: String, target: File): Boolean {
        if (target.exists() && ApiClient.sha256Of(target) == sha256.lowercase()) return true
        return runCatching { api.downloadArtifact(sha256, target) }.getOrElse {
            Log.e(TAG, "download of $sha256 failed", it)
            false
        }
    }

    // ----------------------------------------------------------------------- //
    // Long poll
    // ----------------------------------------------------------------------- //

    /** Blocks until the server rings the doorbell or the hold expires. */
    fun waitForChange(timeoutSeconds: Long): Boolean = runCatching {
        api.waitForChange(config.stateVersion, timeoutSeconds).optBoolean("should_checkin", false)
    }.getOrElse {
        Log.w(TAG, "wait failed: ${it.message}")
        false
    }

    companion object {
        private const val TAG = "Reconciler"
        const val AGENT_VERSION = "0.1.0"
    }
}
