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
import java.io.File
import org.json.JSONArray
import org.json.JSONObject
import org.takmdm.agent.BuildConfig
import org.takmdm.agent.command.ClearAppDataCommandHandler
import org.takmdm.agent.command.CollectLogsCommandHandler
import org.takmdm.agent.command.CommandDispatcher
import org.takmdm.agent.command.LocateCommandHandler
import org.takmdm.agent.command.LockCommandHandler
import org.takmdm.agent.command.RebootCommandHandler
import org.takmdm.agent.command.ScreenshotCommandHandler
import org.takmdm.agent.command.WipeCommandHandler
import org.takmdm.agent.core.AgentConfig
import org.takmdm.agent.core.BundleVerifier
import org.takmdm.agent.diag.AgentLog
import org.takmdm.agent.diag.Redactor
import org.takmdm.agent.diag.RingFileLogSink
import org.takmdm.agent.files.FileDeployer
import org.takmdm.agent.install.AppInstaller
import org.takmdm.agent.net.ApiClient
import org.takmdm.agent.net.DeviceIdentity
import org.takmdm.agent.permissions.PermissionRequirement
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

    /**
     * Composition root for command handling.
     *
     * Built here because this is where the collaborators the handlers need already
     * live. Registration is a list, so a new command type is one entry and no edit
     * to the dispatcher (D88).
     */
    private val dispatcher = CommandDispatcher(
        listOf(
            LockCommandHandler(context),
            RebootCommandHandler(context),
            WipeCommandHandler(context),
            LocateCommandHandler(context),
            ClearAppDataCommandHandler(context),
            ScreenshotCommandHandler(),
            CollectLogsCommandHandler(
                readLogs = { AgentLog.dump() },
                uploadLogs = { text, commandId ->
                    api.uploadLogs(
                        content = text,
                        commandId = commandId,
                        agentVersion = AGENT_VERSION,
                        // The ring buffer rotates rather than trims, so reaching one
                        // full generation means older entries have already been
                        // dropped. The reader needs to know the record starts
                        // mid-story.
                        truncated = text.length >= RingFileLogSink.DEFAULT_MAX_BYTES
                    )
                },
                clearLogs = { AgentLog.clear() }
            )
        )
    )

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
            // The silent path: without provisioning extras the agent simply does
            // nothing and makes no network request, which looks identical to a
            // server that is ignoring it. Say so loudly instead.
            val detail = buildString {
                append("not configured - ")
                append(if (serverUrl.isNullOrBlank()) "server URL missing" else "server URL ok")
                append(", ")
                append(if (token.isNullOrBlank()) "enrollment token missing" else "token ok")
                append(". The provisioning extras did not arrive.")
            }
            config.lastError = detail
            AgentLog.w(TAG, detail)
            return false
        }

        // Before anything can log it, and before the network code that carries it
        // has a chance to appear in a stack trace.
        Redactor.protect(token)

        // Each step below is a candidate for silent failure, so name the one in
        // progress: a stack trace alone does not say how far enrollment got.
        config.lastError = "enrolling: generating hardware-backed key…"

        return runCatching {
            val serial = serialNumber()
            val keyPair = DeviceIdentity.generateKeyPair()

            config.lastError = "enrolling: building CSR…"
            val csr = DeviceIdentity.createCsrPem(keyPair, serial)

            config.lastError = "enrolling: contacting $serverUrl…"

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
            Redactor.forget(token)

            config.lastError = null
            AgentLog.i(TAG, "enrolled as ${config.deviceId}")
            true
        }.getOrElse {
            // Record the class name too: "null" or an empty message is common and
            // tells the reader nothing on its own.
            val detail = "${it.javaClass.simpleName}: ${it.message ?: "no message"}"
            config.lastError = "enrollment failed - $detail"
            AgentLog.e(TAG, "enrollment failed", it)
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

    fun sync(): SyncOutcome = runCatching { syncInner() }
        .onSuccess {
            config.lastSyncAt = System.currentTimeMillis()
            config.lastError = it.errors.firstOrNull()
        }
        .getOrElse {
            val detail = "${it.javaClass.simpleName}: ${it.message ?: "no message"}"
            config.lastError = "sync failed - $detail"
            AgentLog.e(TAG, "sync failed", it)
            throw it
        }

    private fun syncInner(): SyncOutcome {
        if (!enrollIfNeeded()) {
            return SyncOutcome(
                config.stateVersion, null,
                listOf(config.lastError ?: "not enrolled")
            )
        }

        val request = JSONObject()
            .put("state_version", config.stateVersion)
            .put("applied_state_version", config.appliedStateVersion)
            .put("agent_version", AGENT_VERSION)
            .put("os_version", Build.VERSION.RELEASE)
            .put("applied_optional_files", JSONArray(config.selectedOptionalFiles.toList()))
            // Without this the server cannot tell a healthy device from one that
            // is failing to apply anything: it reported "compliant" while the
            // tablet was stuck a version behind.
            .put("apply_errors", JSONArray(config.lastApplyErrors))
            // Outcomes of commands run since the last check-in. Carried on the
            // request, so a result is reported exactly one cycle after execution.
            .put("results", JSONArray(config.pendingCommandResults.map { JSONObject(it) }))

        val response = api.checkin(request)

        // The server considers a reported result final, so only clear the queue
        // once it has actually been accepted. Clearing on send would lose the
        // outcome of a wipe or a log collection to one dropped response.
        config.pendingCommandResults = emptyList()

        runCommands(response.optJSONArray("commands") ?: JSONArray())
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
        config.lastApplyErrors = errors

        // Advance regardless of errors. acked_state_version means "this version has
        // been processed", not "processed perfectly" — quality is what
        // compliance_status is for (D28). Conflating them pinned the device a
        // version behind forever over a single missing permission, and made a
        // genuinely stuck device indistinguishable from a slightly degraded one.
        config.appliedStateVersion = config.stateVersion

        return SyncOutcome(config.stateVersion, config.appliedStateVersion, errors)
    }

    fun applyDesiredState(desired: JSONObject): List<String> {
        val errors = mutableListOf<String>()
        // A revoked app-op degrades the agent silently otherwise: files stop being
        // placed, or the service is deferred, and it looks like a server fault.
        errors += PermissionRequirement.outstanding(context).map {
            "missing permission: $it (grant it in the agent)"
        }
        errors += policyApplier.apply(desired.optJSONObject("policy") ?: JSONObject())
        errors += reconcileApps(desired.optJSONArray("apps") ?: JSONArray())
        errors += reconcileFiles(desired.optJSONObject("files") ?: JSONObject())
        return errors
    }

    // ----------------------------------------------------------------------- //
    // Commands
    // ----------------------------------------------------------------------- //

    /**
     * Execute the transient commands this check-in delivered.
     *
     * Results are normally carried on the *next* check-in request, one cycle later.
     * Two commands cannot wait that long: a reboot kills the process and a wipe
     * destroys the device, so the cycle that would report them never arrives. Those
     * handlers return their effect instead of performing it, and it runs here only
     * after an immediate check-in has actually delivered the result.
     *
     * Without that ordering the server never sees an outcome, redelivers the
     * command, and the device reboots again on the next check-in — a loop that ends
     * only when the queue exhausts its attempts.
     */
    private fun runCommands(commands: JSONArray) {
        if (commands.length() == 0) return

        val dispatched = dispatcher.dispatch(commands)
        if (dispatched.results.isNotEmpty()) {
            config.pendingCommandResults =
                config.pendingCommandResults + dispatched.results.map { it.toJson().toString() }
        }

        if (dispatched.deferredEffects.isEmpty()) return

        if (!flushCommandResults()) {
            // Could not tell the server. Running the effect now would lose the
            // outcome and earn a redelivery, so leave the result queued and let the
            // command be executed on a later cycle instead.
            AgentLog.w(TAG, "deferring ${dispatched.deferredEffects.size} effect(s): results not delivered")
            return
        }

        for (effect in dispatched.deferredEffects) {
            runCatching { effect() }
                .onFailure { AgentLog.e(TAG, "deferred command effect failed", it) }
        }
    }

    /** Post queued results on their own, ahead of the normal cycle. */
    private fun flushCommandResults(): Boolean {
        val queued = config.pendingCommandResults
        if (queued.isEmpty()) return true

        return runCatching {
            api.checkin(
                JSONObject()
                    .put("state_version", config.stateVersion)
                    .put("applied_state_version", config.appliedStateVersion)
                    .put("agent_version", AGENT_VERSION)
                    .put("results", JSONArray(queued.map { JSONObject(it) }))
            )
            config.pendingCommandResults = emptyList()
            true
        }.getOrElse {
            AgentLog.e(TAG, "failed to flush command results", it)
            false
        }
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
            AgentLog.e(TAG, "download of $sha256 failed", it)
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
        AgentLog.w(TAG, "wait failed: ${it.message}")
        false
    }

    companion object {
        private const val TAG = "Reconciler"

        /**
         * Read from the build rather than written here.
         *
         * The literal that used to sit in this slot said `0.1.0` while the build was
         * at `0.2.4`, so every device in the console reported a version it was not
         * running — and "which build is this tablet on?" is the first question asked
         * of a device that is misbehaving. A constant that must be remembered
         * separately is one that will not be.
         */
        const val AGENT_VERSION = BuildConfig.VERSION_NAME
    }
}
