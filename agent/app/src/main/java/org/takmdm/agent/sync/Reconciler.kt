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
import org.takmdm.agent.policy.AllowlistPlan
import org.takmdm.agent.policy.AppUpdatePlan
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
                agentVersion = AGENT_VERSION,
                identifiers = reportedIdentifiers()
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

    /**
     * The identity the server matches a re-enrolling device against (D24).
     *
     * `Build.getSerial()` needs **both** Device Owner privilege and a granted
     * `READ_PHONE_STATE`; without the permission it throws
     * `SecurityException: the uid does not meet the requirements to access device
     * identifiers`, verified on `SM-X520`. With it, the real serial comes back.
     *
     * The `ANDROID_ID` fallback exists so enrolment can still complete, but it is a
     * **degraded** identity: Android documents that it changes on factory reset, and
     * a wipe-and-re-enrol is precisely the case D24 was written for. A device that
     * enrols on the fallback will therefore create a second record rather than
     * re-adopting its own, orphaning its history and its group membership.
     *
     * So the fallback is taken loudly. It used to be silent, which is how one tablet
     * ended up with two records and a manifest comment claiming the problem was
     * fixed.
     */
    private fun serialNumber(): String {
        val real = runCatching { Build.getSerial() }
            .onFailure { AgentLog.w(TAG, "Build.getSerial() refused: ${it.message}") }
            .getOrNull()
            ?.takeIf { it.isNotBlank() && it != Build.UNKNOWN }

        if (real != null) return real

        @Suppress("HardwareIds")
        val androidId = android.provider.Settings.Secure.getString(
            context.contentResolver, android.provider.Settings.Secure.ANDROID_ID
        )
        val fallback = "${Build.MODEL}-$androidId"
        AgentLog.w(
            TAG,
            "using the ANDROID_ID fallback identity '$fallback'. This changes on " +
                "factory reset, so re-enrolment will create a NEW device record " +
                "instead of re-adopting this one (D24). Grant READ_PHONE_STATE."
        )
        return fallback
    }

    /** True when this device is living on the unstable fallback identity. */
    private fun hasStableIdentity(): Boolean =
        runCatching { Build.getSerial() }.getOrNull()
            ?.let { it.isNotBlank() && it != Build.UNKNOWN } == true

    /**
     * Every identity this device can report, strongest first.
     *
     * Sent as a set so the server can match a re-enrolling device on **any** of them
     * (R13). A device whose `Build.getSerial()` was refused at first enrolment is
     * registered under its `ANDROID_ID`; once the permission is granted it reports
     * both, and the server re-adopts the existing record rather than forking a new
     * one. The fallback is included even when the real serial is available — that is
     * exactly what makes the transition work.
     */
    private fun reportedIdentifiers(): JSONArray {
        val identifiers = JSONArray()

        runCatching { Build.getSerial() }.getOrNull()
            ?.takeIf { it.isNotBlank() && it != Build.UNKNOWN }
            ?.let {
                identifiers.put(JSONObject().put("kind", "serial").put("value", it))
            }

        @Suppress("HardwareIds")
        val androidId = android.provider.Settings.Secure.getString(
            context.contentResolver, android.provider.Settings.Secure.ANDROID_ID
        )
        if (!androidId.isNullOrBlank()) {
            identifiers.put(
                JSONObject()
                    .put("kind", "android_id")
                    .put("value", "${Build.MODEL}-$androidId")
            )
        }

        return identifiers
    }

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
        // Before enrolment, because enrolment reads the device serial and
        // READ_PHONE_STATE is one of the permissions this grants. Every sync, not
        // just the first, because a permission added in a later agent build is
        // otherwise never granted on a device already in the field.
        policyApplier.ensureSelfPermissions()
            .forEach { AgentLog.w(TAG, "self-grant: $it") }

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
            // The numeric code as well as the display name: the server's
            // self-update gate compares versionCodes, which is also the only
            // thing Android's own upgrade rule looks at (W27).
            .put("agent_version_code", BuildConfig.VERSION_CODE)
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

        // The operator-assigned name, echoed on every check-in so the on-device
        // console can show it. `has` guards against an older server that omits it;
        // an explicit null legitimately clears a name that was removed. (Android's
        // optString returns the literal "null" for a JSON null, hence isNull.)
        if (response.has("name")) {
            config.deviceName =
                if (response.isNull("name")) null
                else response.optString("name").takeIf { it.isNotBlank() }
        }
        response.optJSONArray("policy_names")?.let { arr ->
            config.policyNames = (0 until arr.length()).mapNotNull { arr.optString(it).takeIf { s -> s.isNotBlank() } }
        }

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

        // Absolutely last, and only from a clean pass (W27). Installing over
        // ourselves kills this process mid-call, so anything after it would not
        // run — and swapping the agent on a device that is already failing to
        // apply its policy only makes the failure harder to read.
        if (errors.isEmpty()) {
            response.optJSONObject("agent_update")?.let { selfUpdate(it) }
        }

        return SyncOutcome(config.stateVersion, config.appliedStateVersion, errors)
    }

    /**
     * Replace this agent with the build the server has offered.
     *
     * The server decides eligibility — candidate builds reach canaries only — so
     * the only check here is that the offer really is newer, guarding against a
     * stale cached response.
     *
     * Nothing after the commit runs: Android kills this process to replace it.
     * The install still completes and `MY_PACKAGE_REPLACED` restarts the service
     * about four seconds later, at which point the reconciler sees itself already
     * at the wanted version and does nothing. There is therefore no success path
     * to report and no result callback to await — silence is success, and the
     * proof is the next check-in arriving with a higher versionCode.
     */
    private fun selfUpdate(offer: JSONObject) {
        val wanted = offer.optLong("version_code", -1)
        if (wanted <= BuildConfig.VERSION_CODE) return

        val sha = offer.optString("sha256").takeIf { it.isNotBlank() } ?: return
        val target = File(cacheDir, sha)
        if (!downloadArtifact(sha, target)) {
            AgentLog.w(TAG, "agent update $wanted: download failed verification")
            return
        }

        // The last line this process will ever write. If a device goes quiet after
        // an update, this is the entry that says it was deliberate.
        AgentLog.i(
            TAG,
            "agent update: replacing ${BuildConfig.VERSION_CODE} with $wanted " +
                "(${offer.optString("version_name")}); this process is about to be killed"
        )
        installer.install(context.packageName, listOf(target))
    }

    /**
     * Re-engage kiosk from the cached desired state, without waiting for a sync.
     *
     * Called at boot. A kiosk that stops being one until the next check-in is a
     * window in which a fielded device is simply a tablet, and the whole point of
     * F6 is that it is not.
     */
    fun reengageKioskIfConfigured(): List<String> {
        val cached = config.cachedDesiredState?.let { runCatching { JSONObject(it) }.getOrNull() }
            ?: return emptyList()
        val kiosk = cached.optJSONObject("policy")
            ?.optJSONObject("APP_CATALOG")
            ?.optString("kiosk_package")
            ?.takeIf { it.isNotBlank() }
            ?: return emptyList()

        AgentLog.i(TAG, "re-engaging kiosk on $kiosk after boot")
        return policyApplier.applyKiosk(kiosk)
    }

    fun applyDesiredState(desired: JSONObject): List<String> {
        val errors = mutableListOf<String>()
        // A revoked app-op degrades the agent silently otherwise: files stop being
        // placed, or the service is deferred, and it looks like a server fault.
        errors += PermissionRequirement.outstanding(context).map {
            "missing permission: $it (grant it in the agent)"
        }
        // Reported, not merely logged. A device on the fallback identity looks
        // perfectly healthy right up until it is wiped, at which point it silently
        // becomes a second record and loses its policy stack. The console should be
        // able to show which devices are in that state before it matters.
        if (!hasStableIdentity()) {
            errors += "unstable device identity: Build.getSerial() unavailable, " +
                "using the ANDROID_ID fallback. Re-enrolment after a factory reset " +
                "will create a duplicate record instead of re-adopting this one (D24)."
        }
        val policy = desired.optJSONObject("policy") ?: JSONObject()
        errors += policyApplier.apply(policy)
        errors += reconcileApps(desired.optJSONArray("apps") ?: JSONArray())
        // After installs, so a package that is both required and removed resolves
        // as removed rather than depending on which ran first. A policy saying both
        // is a mistake, and the guard below reports it instead of flip-flopping the
        // device on every check-in.
        errors += suppressUnwantedApps(
            policy.optJSONObject("APP_CATALOG") ?: JSONObject(),
            desired.optJSONArray("apps") ?: JSONArray()
        )
        errors += enforceAllowlist(
            policy.optJSONObject("APP_CATALOG") ?: JSONObject(),
            desired.optJSONArray("apps") ?: JSONArray()
        )
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

            // Said out loud because "installed", "upgraded" and "skipped, already
            // present" are indistinguishable otherwise, and the collectable log
            // exists to explain what the reconciler did on a device nobody can see.
            when (AppUpdatePlan.decide(installed, desiredVersion, app.optBoolean("auto_update", true))) {
                AppUpdatePlan.Action.SKIP_UP_TO_DATE -> {
                    AgentLog.d(TAG, "$packageName already at versionCode $installed (want $desiredVersion); skipping")
                    continue
                }
                AppUpdatePlan.Action.SKIP_PINNED -> {
                    AgentLog.i(
                        TAG,
                        "$packageName at $installed, newer ($desiredVersion) available but auto_update is off; leaving it"
                    )
                    continue
                }
                AppUpdatePlan.Action.INSTALL ->
                    AgentLog.i(TAG, "installing $packageName versionCode $desiredVersion")
                AppUpdatePlan.Action.UPGRADE ->
                    AgentLog.i(TAG, "upgrading $packageName from versionCode $installed to $desiredVersion")
            }

            val files = app.optJSONArray("files") ?: continue
            val parts = mutableListOf<File>()
            var downloadFailed = false

            // Base first: PackageInstaller needs it before the splits.
            val ordered = (0 until files.length())
                .mapNotNull { files.optJSONObject(it) }
                .sortedBy { if (it.optString("role") == "base") 0 else 1 }

            // R2: a normally-installed Device Owner cannot write another app's
            // Android/obb directory — verified EACCES on SM-X520, and it is a
            // deliberate scoped-storage restriction (not fixed by all-files
            // access). Report it rather than skipping silently: the APK installs
            // and the app then fails at runtime with its assets missing, which is
            // the worst kind of failure to diagnose.
            if (ordered.any { it.optString("role") == "obb" }) {
                AgentLog.w(TAG, "$packageName: OBB present but cannot be deployed (scoped storage, R2)")
                errors += "$packageName: ships an OBB expansion file, which a Device Owner " +
                    "cannot place on this device (Android blocks writing another app's " +
                    "Android/obb). The APK is installed WITHOUT it, so the app will be " +
                    "missing the assets it expects. Install the OBB by hand, or deploy a " +
                    "build that does not use one."
            }

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
                AgentLog.d(TAG, "$packageName: ${part.optString("role")} part verified (${target.length()} bytes)")
            }
            if (downloadFailed) continue

            val result = installer.install(packageName, parts)
            if (result.success) {
                AgentLog.i(
                    TAG,
                    "$packageName installed: versionCode " +
                        "${installer.installedVersionCode(packageName)} from ${parts.size} part(s)"
                )
                errors += policyApplier.grantRuntimePermissions(packageName)
            } else {
                AgentLog.e(TAG, "$packageName install failed: ${result.message}")
                errors += "$packageName: ${result.message}"
            }
        }
        return errors
    }

    /**
     * Make unwanted packages go away, by the strongest means each one allows.
     *
     * Two lists, two intents:
     *
     * * **`removed_packages` — strict.** Uninstall, and say so plainly if the app
     *   survives. For reclaiming storage or destroying data, where "it did not
     *   actually work" is something the operator must be told.
     * * **`blocked_packages` — the blacklist.** Make it unusable by whatever works:
     *   uninstall an ordinary app, hide one that ships with the device.
     *
     * **A system app cannot be uninstalled, and the platform does not say so.**
     * `PackageInstaller` returns `STATUS_SUCCESS` for what is really "the update was
     * removed", leaving the factory build installed and working. Verified on
     * `SM-X520`: uninstalling Gmail moved it from `/data/app/...` back to
     * `/product/app/Gmail2` and rolled its version backwards, and the agent reported
     * "removed" for an app the user could still open. So system apps are hidden
     * directly — skipping both the pointless downgrade and the false success — and
     * every uninstall is verified afterwards regardless.
     *
     * Convergent, not a one-shot (D5): a tablet dark for three weeks suppresses the
     * app when it returns.
     */
    private fun suppressUnwantedApps(catalog: JSONObject, apps: JSONArray): List<String> {
        val errors = mutableListOf<String>()
        val required = (0 until apps.length())
            .mapNotNull { apps.optJSONObject(it)?.optString("package_name") }
            .toSet()

        fun guard(packageName: String): String? = when {
            packageName == context.packageName ->
                // Android refuses anyway - a package with an active device admin
                // cannot be removed - but refusing here names the reason instead of
                // leaving an opaque platform failure to decode.
                "$packageName: refusing to suppress the agent itself"
            packageName in required ->
                // Contradictory policy. Acting on either half would install and
                // remove the same app on alternate check-ins.
                "$packageName: listed as both required and unwanted"
            else -> null
        }

        for (packageName in catalog.stringList("removed_packages")) {
            val problem = guard(packageName)
            if (problem != null) {
                errors += problem
                continue
            }
            if (!installer.isPresent(packageName)) continue

            AgentLog.i(TAG, "removing $packageName")
            val result = installer.uninstall(packageName)
            if (result.success) {
                AgentLog.i(TAG, "$packageName removed")
            } else {
                // Strict list: no fallback. Asking for removal and silently getting
                // "hidden" would be the same lie in a different place.
                AgentLog.e(TAG, "$packageName removal failed: ${result.message}")
                errors += "$packageName: could not be removed - ${result.message}"
            }
        }

        val blocked = catalog.stringList("blocked_packages").toSet()

        // Undo first, and only what we did. A desired state that can hide but never
        // unhide is not a desired state, it is a ratchet: removing a package from
        // the blocklist would leave every device that ever saw it still suppressing
        // it, with nothing in the policy to explain why.
        val stillHidden = mutableSetOf<String>()
        for (packageName in config.hiddenByPolicy) {
            if (packageName in blocked) {
                stillHidden += packageName
                continue
            }
            AgentLog.i(TAG, "no longer blocked, unhiding $packageName")
            val failure = policyApplier.setHidden(packageName, false)
            if (failure != null) {
                errors += "$packageName: could not be unhidden - $failure"
                stillHidden += packageName
            }
        }

        for (packageName in blocked) {
            val problem = guard(packageName)
            if (problem != null) {
                errors += problem
                continue
            }
            if (!installer.isPresent(packageName)) continue

            if (installer.isSystemApp(packageName)) {
                if (policyApplier.isHidden(packageName)) {
                    // Already done. Still recorded, or the next pass forgets we hid
                    // it and it could never be unhidden.
                    stillHidden += packageName
                    continue
                }
                AgentLog.i(TAG, "blocking $packageName: ships with the device, hiding it")
                val failure = policyApplier.setHidden(packageName, true)
                if (failure != null) errors += "$packageName: could not be hidden - $failure"
                else stillHidden += packageName
                continue
            }

            AgentLog.i(TAG, "blocking $packageName: uninstalling")
            val result = installer.uninstall(packageName)
            if (result.success) {
                AgentLog.i(TAG, "$packageName removed")
                continue
            }

            // Survived the uninstall. Hiding is the remaining lever, and it is what
            // "blacklisted" has to mean for anything that cannot be deleted.
            AgentLog.w(TAG, "$packageName could not be uninstalled (${result.message}); hiding instead")
            val failure = policyApplier.setHidden(packageName, true)
            if (failure != null) errors += "$packageName: neither uninstalled nor hidden - $failure"
            else stillHidden += packageName
        }

        config.hiddenByPolicy = stillHidden
        return errors
    }

    /**
     * `allowed_packages` — only these apps may run. Suspends every non-system user
     * app not on the list (required apps and the agent are implicitly allowed).
     *
     * Inert unless a non-empty allowlist is present: `allowed_packages` absent
     * means no restriction, and an *empty* list (an INTERSECT of two policies that
     * do not overlap, R4) is a stacking accident, not "suspend everything" — it is
     * reported and ignored. When the allowlist goes away, everything the agent
     * suspended is released.
     */
    private fun enforceAllowlist(catalog: JSONObject, apps: JSONArray): List<String> {
        val errors = mutableListOf<String>()

        val allowed: List<String>? =
            if (catalog.has("allowed_packages")) catalog.stringList("allowed_packages") else null
        val required = (0 until apps.length())
            .mapNotNull { apps.optJSONObject(it)?.optString("package_name") }
            .filter { it.isNotBlank() }
            .toSet()

        val userApps = installer.userInstalledPackages()
        val decision = AllowlistPlan.decide(
            userApps = userApps,
            allowed = allowed,
            required = required,
            agentPackage = context.packageName,
            previouslySuspended = config.suspendedByPolicy,
        )

        if (allowed != null) {
            AgentLog.i(
                TAG,
                "allowlist: ${userApps.size} user app(s), ${allowed.size} allowed, " +
                    "suspend ${decision.toSuspend.size}, release ${decision.toUnsuspend.size}"
            )
        }

        if (decision.emptyAndIgnored) {
            AgentLog.w(TAG, "allowlist resolved empty (stacked policies do not overlap); not enforcing")
            errors += "allowed_packages resolved to an empty list; allowlist not enforced"
        }

        if (decision.toUnsuspend.isNotEmpty()) {
            AgentLog.i(TAG, "allowlist: un-suspending ${decision.toUnsuspend.joinToString()}")
            errors += policyApplier.setSuspended(decision.toUnsuspend, suspended = false)
        }
        if (decision.toSuspend.isNotEmpty()) {
            AgentLog.i(TAG, "allowlist: suspending ${decision.toSuspend.joinToString()}")
            errors += policyApplier.setSuspended(decision.toSuspend, suspended = true)
        }

        val now = (config.suspendedByPolicy - decision.toUnsuspend) + decision.toSuspend
        config.suspendedByPolicy = now
        return errors
    }

    /** Read a JSON string array as a Kotlin list, tolerating absence. */
    private fun JSONObject.stringList(field: String): List<String> {
        val array = optJSONArray(field) ?: return emptyList()
        return (0 until array.length())
            .map { array.optString(it) }
            .filter { it.isNotBlank() }
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
        if (config.appliedFileHash(key) == sha) {
            // Already placed this content here. Whether to look at the disk depends
            // on what the policy asked for.
            //
            // **Deployment is write-only — the MDM never deletes a managed file.**
            // `persist` governs replacement only: on, the file is kept present and
            // is re-pushed if it goes missing or comes back the wrong size; off, it
            // was placed once and a user who removed it meant to, and can take it
            // again from the marketplace.
            val persist = entry.optBoolean("persist", true)
            if (!persist) {
                AgentLog.d(TAG, "$fileId already placed at ${entry.optString("dest_path")}; not persisted, leaving it")
                return emptyList()
            }
            if (deployer.isDeployed(entry, entry.optLong("size_bytes", -1))) {
                AgentLog.d(TAG, "$fileId already placed at ${entry.optString("dest_path")}; skipping")
                return emptyList()
            }
            AgentLog.w(
                TAG,
                "$fileId is persisted but missing or incomplete at " +
                    "${entry.optString("dest_path")}; replacing"
            )
        }
        AgentLog.i(TAG, "deploying $fileId to ${entry.optString("dest_path")}")

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
