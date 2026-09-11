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

package com.taksolutions.atlasmdm.sync

import android.content.Context
import android.graphics.Bitmap
import android.os.Build
import java.io.File
import org.json.JSONArray
import org.json.JSONObject
import com.taksolutions.atlasmdm.BuildConfig
import com.taksolutions.atlasmdm.R
import com.taksolutions.atlasmdm.command.ClearAppDataCommandHandler
import com.taksolutions.atlasmdm.command.CollectLogsCommandHandler
import com.taksolutions.atlasmdm.command.CommandDispatcher
import com.taksolutions.atlasmdm.command.LocateCommandHandler
import com.taksolutions.atlasmdm.command.LockCommandHandler
import com.taksolutions.atlasmdm.command.PingCommandHandler
import com.taksolutions.atlasmdm.command.RebootCommandHandler
import com.taksolutions.atlasmdm.command.ScreenshotCommandHandler
import com.taksolutions.atlasmdm.command.WipeCommandHandler
import com.taksolutions.atlasmdm.core.AgentConfig
import com.taksolutions.atlasmdm.core.HardwareFacts
import com.taksolutions.atlasmdm.core.BundleVerifier
import com.taksolutions.atlasmdm.diag.AgentLog
import com.taksolutions.atlasmdm.diag.Redactor
import com.taksolutions.atlasmdm.diag.RingFileLogSink
import com.taksolutions.atlasmdm.files.FileDeployer
import com.taksolutions.atlasmdm.install.AppInstaller
import com.taksolutions.atlasmdm.net.ApiClient
import com.taksolutions.atlasmdm.net.DeviceIdentity
import com.taksolutions.atlasmdm.permissions.PermissionRequirement
import com.taksolutions.atlasmdm.policy.AllowlistPlan
import com.taksolutions.atlasmdm.policy.AppUpdatePlan
import com.taksolutions.atlasmdm.policy.DataUsageTracker
import com.taksolutions.atlasmdm.policy.ArtifactSweepPlan
import com.taksolutions.atlasmdm.policy.InstallerCachePlan
import com.taksolutions.atlasmdm.policy.InstallRetryPlan
import com.taksolutions.atlasmdm.policy.LauncherConfigPlan
import com.taksolutions.atlasmdm.policy.GeofencePlan
import com.taksolutions.atlasmdm.policy.LocationSamplingPlan
import com.taksolutions.atlasmdm.policy.LocationTracker
import com.taksolutions.atlasmdm.policy.PolicyApplier
import com.taksolutions.atlasmdm.ui.InstallNotifier
import com.taksolutions.atlasmdm.policy.DeviceIdLabel
import com.taksolutions.atlasmdm.policy.WallpaperPlan

/** Outcome of one reconciliation pass. */
data class SyncOutcome(
    val stateVersion: Int,
    val appliedStateVersion: Int?,
    val errors: List<String>,
    val warnings: List<String> = emptyList(),
)

/**
 * What one pass over the desired state produced (W50).
 *
 * Errors and warnings are separate facts and cannot share a list. An error means
 * the device failed to apply something; a warning means it applied everything and
 * there is still something the operator should know — a policy naming an older
 * build than the device already carries, say. Folding the second into the first
 * marks healthy devices DEGRADED, and a DEGRADED device is refused agent updates.
 */
data class ApplyReport(
    val errors: List<String> = emptyList(),
    val warnings: List<String> = emptyList(),
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
            PingCommandHandler(context),
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

    fun enrollIfNeeded(): Boolean = synchronized(ENROLL_LOCK) { enrollIfNeededLocked() }

    /**
     * ⚠️ **Must only be called under [ENROLL_LOCK].**
     *
     * Enrolling twice at once leaves the device holding one attempt's certificate
     * and the other attempt's private key, because both steps write to fixed
     * slots: `generateKeyPair` replaces the keystore entry and `installCertificate`
     * replaces the certificate. The TLS handshake then fails with "bad signature"
     * - the certificate's public key cannot verify what the private key signed -
     * and the device can never check in again.
     *
     * Observed on `SM-G736U1`: two `POST /api/v1/enroll` calls in the same second
     * at provisioning, two certificates issued, the first revoked by the second,
     * and every subsequent handshake refused.
     */
    private fun enrollIfNeededLocked(): Boolean {
        // Re-checked inside the lock: the caller that waited here may find the
        // one that held it has already enrolled, and must not do it again.
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
        // The one installer file nothing else can clean up: see below.
        discardFinishedSelfUpdate()

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
            // Which ATAK is actually on the device. An ATAK plugin only loads in
            // the build it was compiled against, and a mismatch is invisible here
            // — the plugin installs and simply never appears — so the server is
            // the only place that can tell an operator (W32).
            .apply {
                installer.installedAtak()?.let { (pkg, version) ->
                    put("atak_package", pkg)
                    put("atak_version", version)
                }
            }
            .put("os_version", Build.VERSION.RELEASE)
            // What this device can actually run (W96). Reported in the platform's
            // own preference order, because "which of these builds suits it best"
            // is a question that order answers. RELEASE above is a marketing name
            // ("14"); comparing an APK's minSdk needs the API level as a number.
            .put("supported_abis", JSONArray(Build.SUPPORTED_ABIS.toList()))
            .put("sdk_int", Build.VERSION.SDK_INT)
            .put("applied_optional_files", JSONArray(config.selectedOptionalFiles.toList()))
            // Without this the server cannot tell a healthy device from one that
            // is failing to apply anything: it reported "compliant" while the
            // tablet was stuck a version behind.
            .put("apply_errors", JSONArray(config.lastApplyErrors))
            // Separate from apply_errors on purpose: these never move
            // compliance_status (W50).
            .put("apply_warnings", JSONArray(config.lastApplyWarnings))
            // Outcomes of commands run since the last check-in. Carried on the
            // request, so a result is reported exactly one cycle after execution.
            .put("results", JSONArray(config.pendingCommandResults.map { JSONObject(it) }))

        // Battery, IMEIs and line number (W108). Added here rather than inline
        // above because `has_telephony` has to be sent even when every value
        // below it fails to read — that flag is what lets the console tell
        // "no cellular radio" apart from "could not read the IMEI".
        HardwareFacts.addTo(request, context)

        // Positions buffered since the last accepted check-in, oldest first and
        // capped below the server's own limit — which rejects an oversized batch
        // outright rather than trimming it, so a long backlog drains over several
        // cycles instead of failing every one of them (W106).
        val locationBatch = LocationSamplingPlan.nextBatch(config.pendingLocations)
        if (locationBatch.isNotEmpty()) {
            request.put("locations", LocationSamplingPlan.toJsonArray(locationBatch))
        }

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

        // ⚠️ Drop exactly what was sent, not the whole buffer. The sampler runs on
        // the same loop and may have added points while this request was in
        // flight; clearing wholesale would discard fixes the server never saw.
        if (locationBatch.isNotEmpty()) {
            config.pendingLocations =
                LocationSamplingPlan.remaining(config.pendingLocations, locationBatch.size)
        }

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

        val report = applyDesiredState(desired)
        val errors = report.errors
        config.lastApplyErrors = errors
        config.lastApplyWarnings = report.warnings

        // Advance regardless of errors. acked_state_version means "this version has
        // been processed", not "processed perfectly" — quality is what
        // compliance_status is for (D28). Conflating them pinned the device a
        // version behind forever over a single missing permission, and made a
        // genuinely stuck device indistinguishable from a slightly degraded one.
        config.appliedStateVersion = config.stateVersion

        // Before the self-update, which never returns. Also after applying, so a
        // file this pass downloaded and installed is judged on what the device
        // holds now rather than on what it held when the sync started.
        sweepArtifactCache(desired)

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
        // The agent is ~20 MB, and a device that goes quiet mid-download with
        // nothing on screen is indistinguishable from one that has hung (W75).
        val label = context.getString(R.string.app_name)
        val totalBytes = offer.optLong("size_bytes", 0L)
        if (!downloadArtifact(sha, target) { read, _ ->
                InstallNotifier.downloading(context, label, read, totalBytes)
            }
        ) {
            InstallNotifier.clear(context)
            AgentLog.w(TAG, "agent update $wanted: download failed verification")
            return
        }
        // ⚠️ Not cleared afterwards, deliberately: `install` replaces this process
        // and nothing here runs again. The notification goes when the new build
        // starts and its own reconcile clears it - leaving it up is the honest
        // state, because the install really is still happening.
        InstallNotifier.installing(context, label)

        // Written before the install for the same reason (W88): this process is
        // about to be killed, so the only chance to say which file to throw away
        // is now. The build that starts next reads it in [discardFinishedSelfUpdate].
        config.recordPendingSelfUpdate(sha, wanted)

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

    fun applyDesiredState(desired: JSONObject): ApplyReport {
        val errors = mutableListOf<String>()
        val warnings = mutableListOf<String>()
        // A revoked app-op degrades the agent silently otherwise: files stop being
        // placed, or the service is deferred, and it looks like a server fault.
        errors += PermissionRequirement.outstanding(context).map {
            "missing permission: $it (grant it in the agent)"
        }
        // ⚠️ A *warning*, not an error. An optional permission reported as an
        // error marks the device DEGRADED, and agent_update.decide() refuses to
        // offer an update to a device that is not applying its policy cleanly -
        // so a missing nice-to-have would shut the update channel that fixes it.
        warnings += PermissionRequirement.outstandingOptional(context).map {
            "optional permission not granted: $it (some Device Settings controls " +
                "will explain themselves instead of working)"
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

        // ⚠️ A geofence's password requirement is folded into the PASSWORD spec
        // rather than applied separately, so there stays exactly one writer of the
        // password setters. A second writer would be undone by the next reconcile
        // — `applyPassword` drives every field to a definite value each time, R14 —
        // minutes later and without a word. Folding also makes the release
        // automatic: when no fence asks, the floor is simply not added.
        val fenceLock = GeofencePlan.lockFromName(config.geofenceLock)
        if (fenceLock != GeofencePlan.Lock.NONE) {
            policy.put(
                "PASSWORD",
                GeofencePlan.passwordSpecWithFence(policy.optJSONObject("PASSWORD"), fenceLock),
            )
        }

        errors += policyApplier.apply(policy)

        // ⚠️ After `apply`, never before. The constraints have to be released in
        // the same reconcile before the passcode can be cleared — AOSP refuses the
        // clear while a quality or length rule is still in force, and says so only
        // by returning false.
        if (fenceLock == GeofencePlan.Lock.OFF) {
            errors += policyApplier.clearPasscodeForTrustedArea()
        }
        val appReport = reconcileApps(desired.optJSONArray("apps") ?: JSONArray())
        errors += appReport.errors
        warnings += appReport.warnings
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
        // ⚠️ After the installs, and that ordering is the whole point (W63). A
        // kiosk policy names an app to lock to; the server makes that app a
        // required install; and locking to something the device has not installed
        // yet cannot work. Run before `reconcileApps` this failed on the very sync
        // that installed the app.
        errors += policyApplier.applyKioskPolicy(
            policy.optJSONObject("KIOSK") ?: JSONObject(),
            policy.optJSONObject("APP_CATALOG") ?: JSONObject(),
            policy.optJSONObject("RESTRICTIONS") ?: JSONObject(),
        )
        errors += removeLauncherIfNoLongerAKiosk(
            policy.optJSONObject("KIOSK") ?: JSONObject(),
            desired.optJSONArray("apps") ?: JSONArray(),
        )
        errors += reconcileFiles(desired.optJSONObject("files") ?: JSONObject())
        errors += reconcileWallpaper(desired.optJSONObject("wallpaper") ?: JSONObject())
        // Last, and reading-only: usage thresholds describe what the device has
        // already done, so nothing else in the reconcile depends on the answer.
        // Runs unconditionally — with no section, tracking is off and the tracker's
        // job is to forget any warnings it was remembering (W44).
        errors += DataUsageTracker(context)
            .reconcile(policy.optJSONObject("NETWORK_DATA_USE") ?: JSONObject())
        // Unconditional, like the tracker above: with no section, tracking is off,
        // and the point of running anyway is that *removing* the policy has to
        // stop the sampler rather than leave the last interval running for ever.
        errors += LocationTracker(context)
            .reconcile(policy.optJSONObject("TRACKING_FENCING"))
        return ApplyReport(errors, warnings)
    }

    /**
     * Set the wallpaper the policy asks for, choosing by this device's own screen.
     *
     * The choice happens here rather than on the server (D46) — only sha256
     * references travel, and the chosen image alone is downloaded.
     */
    private fun reconcileWallpaper(wallpaper: JSONObject): List<String> {
        val tablet = wallpaper.optJSONObject("tablet")
        val phone = wallpaper.optJSONObject("phone")
        // ⚠️ The label is an instruction in its own right (W129). A policy that
        // asks only for it names no image, and treating that as "no wallpaper
        // policy" would clear the screen instead of labelling it.
        val wantsLabel = wallpaper.optBoolean("device_id_label", false)

        // Handled before the early return, and reached because the section is
        // applied even when absent — the same lesson as R14/R19: "no policy says
        // anything" is a state to converge on, not an absence of work.
        if (WallpaperPlan.shouldClear(
                policyNamesAnyImage = tablet != null || phone != null || wantsLabel,
                previouslyApplied = config.appliedWallpaperSha != null,
            )
        ) {
            AgentLog.i(TAG, "no policy sets a wallpaper; restoring the device default")
            val failure = policyApplier.clearWallpaper()
                ?: run { config.appliedWallpaperSha = null; return emptyList() }
            return listOf("wallpaper: could not restore the default — $failure")
        }
        if (tablet == null && phone == null && !wantsLabel) return emptyList()

        val errors = mutableListOf<String>()
        // A slot pointing at a file that has left the library. Reported rather than
        // treated as "no image", so a broken policy looks broken.
        for ((label, slot) in listOf("tablet" to tablet, "phone" to phone)) {
            if (slot != null && !slot.optBoolean("available", false)) {
                errors += "wallpaper: the $label image is no longer in the library"
            }
        }

        val usableTablet = tablet?.takeIf { it.optBoolean("available", false) }
        val usablePhone = phone?.takeIf { it.optBoolean("available", false) }
        val width = context.resources.configuration.smallestScreenWidthDp
        val choice = WallpaperPlan.choose(
            hasTablet = usableTablet != null,
            hasPhone = usablePhone != null,
            smallestWidthDp = width,
        )
        val chosen = when (choice) {
            WallpaperPlan.Choice.TABLET -> usableTablet
            WallpaperPlan.Choice.PHONE -> usablePhone
            WallpaperPlan.Choice.NONE -> null
        }
        if (chosen == null && !wantsLabel) return errors

        val sha = chosen?.optString("sha256")?.takeIf { it.isNotBlank() }
        if (chosen != null && sha == null) {
            return errors + "wallpaper: the chosen image has no artifact"
        }

        val label = if (wantsLabel) config.deviceName?.takeIf { it.isNotBlank() } else null
        if (wantsLabel && label == null) {
            // Reported rather than drawn as "unnamed": a wallpaper reading
            // "unnamed" on every tablet is worse than none, and the fix is to
            // name the device.
            errors += "wallpaper: the device ID label is on but this device has no name"
        }

        // ⚠️ The identity of what is on screen, not of the file it came from
        // (W129). Keyed on the sha alone, renaming a device in the console would
        // redraw nothing — the image is unchanged, so the reconcile would decide
        // it had nothing to do and the tablet would keep the old name for ever.
        val screen = "${'$'}{context.resources.displayMetrics.widthPixels}x" +
            "${'$'}{context.resources.displayMetrics.heightPixels}"
        val identity = listOfNotNull(sha ?: "none", label?.let { "label:${'$'}it" }, screen)
            .joinToString("|")

        // Re-setting a wallpaper is visible to the user as a flicker, so an
        // idempotent reconcile must genuinely do nothing.
        if (config.appliedWallpaperSha == identity) return errors

        var target: File? = null
        if (sha != null) {
            val file = File(cacheDir, sha)
            if (!downloadArtifact(sha, file)) {
                return errors + "wallpaper: download of ${'$'}sha failed verification"
            }
            target = file
        }

        if (label != null) {
            val metrics = context.resources.displayMetrics
            val composed = DeviceIdLabel.render(
                source = target,
                name = label,
                width = metrics.widthPixels,
                height = metrics.heightPixels,
            ) ?: return errors + "wallpaper: could not draw the device ID label"

            val out = File(cacheDir, "labelled.png")
            val written = runCatching {
                out.outputStream().use { composed.compress(Bitmap.CompressFormat.PNG, 100, it) }
            }.isSuccess
            composed.recycle()
            if (!written) return errors + "wallpaper: could not write the labelled image"
            target = out
        }

        val image = target ?: return errors

        AgentLog.i(
            TAG,
            "applying ${'$'}choice wallpaper (smallestScreenWidthDp=${'$'}width)" +
                (if (sha != null) " from ${'$'}{sha.take(12)}…" else " (generated)") +
                (if (label != null) " with device ID label" else "")
        )
        val applied = policyApplier.setWallpaper(
            image = image,
            alsoLockScreen = wallpaper.optBoolean("lock_screen", false),
            preventUserChange = wallpaper.optBoolean("prevent_user_change", false),
        )
        if (applied != null) return errors + "wallpaper: ${'$'}applied"

        config.appliedWallpaperSha = identity
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

    private fun reconcileApps(apps: JSONArray): ApplyReport {
        val errors = mutableListOf<String>()
        val warnings = mutableListOf<String>()

        for (index in 0 until apps.length()) {
            val app = apps.optJSONObject(index) ?: continue
            val packageName = app.optString("package_name")

            if (!app.optBoolean("available", false)) {
                // The server says why. Falling back to the old wording only for a
                // server too old to send one — "nothing uploaded" is now just one
                // of the ways this happens, and the least alarming of them: a
                // policy pinned to a build that has left the library reads very
                // differently to an app nobody has uploaded yet.
                val reason = app.str("reason") ?: "nothing uploaded for it"
                errors += "$packageName: required but $reason"
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
                AppUpdatePlan.Action.REFUSED_DOWNGRADE -> {
                    // A **warning**, not an error (W50). The newer build satisfies
                    // the requirement — the app is present and usable — so the
                    // device has converged and must not be marked DEGRADED for it.
                    //
                    // That distinction is load-bearing twice over: it stops a
                    // healthy fleet reading as broken, and a DEGRADED device is
                    // refused agent updates, so filing this as an error would cut
                    // the device off from every future agent build over a version
                    // mismatch nobody intends to act on.
                    //
                    // Still reported rather than logged: the operator learns from
                    // the console, not by walking up to the device.
                    AgentLog.w(
                        TAG,
                        "$packageName is at versionCode $installed but the policy wants " +
                            "$desiredVersion; keeping the newer build"
                    )
                    warnings += "$packageName: the device has versionCode $installed, newer " +
                        "than the $desiredVersion this policy installs. The newer build " +
                        "satisfies the requirement and was kept — Android refuses a downgrade, " +
                        "and removing it first would erase the app's data."
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

            // ⚠️ A build that cannot install on this device is not downloaded
            // again (W96, R19). An ABI or minSdk mismatch fails identically
            // forever, and re-attempting it cost one tablet a multi-megabyte
            // download and a failed install on every single reconcile.
            //
            // Still reported, every cycle: the app really is missing and the
            // device really is non-compliant. What stops is the work, not the
            // telling — a fault that goes quiet is a fault nobody fixes.
            val retryKey = InstallRetryPlan.keyFor(
                packageName,
                ordered.firstOrNull { it.optString("role") == "base" }
                    ?.optString("sha256").orEmpty(),
            )
            if (retryKey in config.unusableBuilds) {
                AgentLog.w(TAG, "$packageName: skipping, this build cannot install here")
                errors += "$packageName: this build cannot install on this device, so it " +
                    "is no longer being retried. Upload a build that supports this " +
                    "device, or remove the app from the policy."
                continue
            }

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

            // Whoever is holding the device sees what is happening to it (W75).
            // The label rather than the package: "Downloading ATAK" is what a user
            // can act on, and com.atakmap.app.civ is not.
            val label = app.str("label") ?: packageName
            // ⚠️ Progress is aggregated across parts, not per part. A split app
            // downloading three parts would otherwise show the bar fill and reset
            // three times, which reads as three failed attempts.
            val totalBytes = (0 until ordered.size).sumOf { i ->
                ordered[i].optLong("size_bytes", 0L)
            }
            var completedBytes = 0L

            for (part in ordered) {
                if (part.optString("role") == "obb") continue
                val sha = part.optString("sha256")
                val target = File(cacheDir, sha)
                val partBytes = part.optLong("size_bytes", 0L)
                val startedAt = completedBytes
                if (!downloadArtifact(sha, target) { read, _ ->
                        InstallNotifier.downloading(context, label, startedAt + read, totalBytes)
                    }
                ) {
                    errors += "$packageName: download of $sha failed verification"
                    downloadFailed = true
                    break
                }
                completedBytes = startedAt + partBytes
                parts += target
                AgentLog.d(TAG, "$packageName: ${part.optString("role")} part verified (${target.length()} bytes)")
            }
            if (downloadFailed) {
                InstallNotifier.clear(context)
                continue
            }

            InstallNotifier.installing(context, label)
            val result = installer.install(packageName, parts)
            InstallNotifier.clear(context)
            if (InstallerCachePlan.discardAfterInstall(result.success)) {
                discardInstallerFiles(packageName, parts)
            }
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
                // Unknown failures are retried; only the ones that are properties
                // of the build itself are remembered. See InstallRetryPlan for why
                // the default leans that way.
                if (!InstallRetryPlan.shouldRetry(result.message)) {
                    AgentLog.w(TAG, "$packageName: will not retry this build")
                    config.unusableBuilds = config.unusableBuilds + retryKey
                }
            }
        }
        return ApplyReport(errors, warnings)
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

    /**
     * A string field, or null when absent, JSON-null, or blank.
     *
     * `optString` cannot be used bare: for a JSON null it returns the literal
     * four characters `"null"`, which has reached a user-facing screen once
     * already on this project.
     */
    private fun JSONObject.str(field: String): String? =
        if (isNull(field)) null else optString(field).takeIf { it.isNotBlank() }

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

    /**
     * Take the ATLAS launcher off a device that is no longer a multi-app kiosk
     * (W69).
     *
     * ⚠️ **Clearing the HOME preference is not enough on its own.** With the
     * launcher still installed the device has *two* home apps and no default, so
     * pressing HOME raises Android's "Complete action using…" chooser rather than
     * going to the stock launcher. The operator removed a policy and expects the
     * device back as it was, not a device asking them which launcher they meant.
     *
     * ⚠️ Uninstalled rather than hidden. A hidden package still exists but reads
     * as missing to `getPackageInfo`, so the reconciler would decide it needed
     * installing again on the very next kiosk — a limbo state where the device
     * disagrees with itself. Gone is a state both halves can agree on, and
     * re-entry re-downloads it through the required-app path that exists for
     * exactly that.
     *
     * The decision itself is [LauncherConfigPlan.shouldRemoveLauncher], which is
     * pure and tested; this is the part that needs a device.
     */
    private fun removeLauncherIfNoLongerAKiosk(
        kiosk: JSONObject,
        desiredApps: JSONArray,
    ): List<String> {
        val launcher = PolicyApplier.LAUNCHER_PACKAGE
        val required = buildList {
            for (i in 0 until desiredApps.length()) {
                desiredApps.optJSONObject(i)?.optString("package_name")
                    ?.takeIf { it.isNotBlank() }?.let(::add)
            }
        }
        if (!LauncherConfigPlan.shouldRemoveLauncher(kiosk, required)) return emptyList()
        if (!policyApplier.isInstalled(launcher)) return emptyList()

        AgentLog.i(TAG, "kiosk: no multi-app kiosk any more; removing $launcher")
        val result = installer.uninstall(launcher)
        return if (result.success) emptyList()
        else listOf("kiosk: could not remove the ATLAS launcher - ${result.message}")
    }

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

    /**
     * Install an app the user chose from the ATLAS store (W56).
     *
     * Returns null on success, or a reason to show them.
     *
     * ⚠️ Called from the Apps screen, never from [sync]. A store entry is an
     * **offer**: the reconciler reads `apps` and must go on reading only `apps`,
     * or listing something in the store would silently install it on every device
     * — which is the opposite of what the store is for.
     *
     * Deliberately not folded into [reconcileApps]. That function carries the
     * downgrade, pinning and OBB rules that make a *required* app converge, and
     * none of them apply to a user tapping install; sharing the path would mean
     * one of the two callers is always being told rules it should not obey.
     * The duplication here is a dozen lines of download-and-install.
     */
    /** Which half of a store install is running, so the UI can say (W58). */
    enum class InstallPhase { DOWNLOADING, INSTALLING }

    /**
     * How a store install ended.
     *
     * ⚠️ Three outcomes, not two. A user who pressed Cancel has not suffered a
     * failure, and reporting one would be a lie the screen then has to show them.
     */
    sealed interface StoreInstall {
        data object Done : StoreInstall
        data object Cancelled : StoreInstall
        data class Failed(val reason: String) : StoreInstall
    }

    /**
     * Install an app the user chose from the ATLAS store (W56).
     *
     * ⚠️ Called from the Apps screen, never from [sync]. A store entry is an
     * **offer**: the reconciler reads `apps` and must go on reading only `apps`,
     * or listing something in the store would silently install it on every device
     * — which is the opposite of what the store is for.
     *
     * Deliberately not folded into [reconcileApps]. That function carries the
     * downgrade, pinning and OBB rules that make a *required* app converge, and
     * none of them apply to a user tapping install; sharing the path would mean
     * one of the two callers is always being told rules it should not obey.
     *
     * [isCancelled] is honoured **only while downloading**. Once
     * `PackageInstaller` is committing, Android is mutating the package and there
     * is nothing safe left to abandon (W58).
     */
    fun installFromStore(
        entry: JSONObject,
        onProgress: ((InstallPhase, Long, Long) -> Unit)? = null,
        isCancelled: (() -> Boolean)? = null,
    ): StoreInstall {
        val packageName = entry.optString("package_name")
        if (packageName.isBlank()) return StoreInstall.Failed("this app has no package name")

        val files = entry.optJSONArray("files") ?: return StoreInstall.Failed("nothing to install")
        // Base first — PackageInstaller needs it before the splits — and OBB parts
        // dropped, which a Device Owner cannot place anyway (R2).
        val ordered = (0 until files.length())
            .mapNotNull { files.optJSONObject(it) }
            .filter { it.optString("role") != "obb" }
            .sortedBy { if (it.optString("role") == "base") 0 else 1 }

        // Progress spans every part, so the bar measures the install rather than
        // whichever file happens to be in flight.
        val totalBytes = ordered.sumOf { it.optLong("size_bytes", 0L) }
        var doneBytes = 0L

        val parts = mutableListOf<File>()
        for (part in ordered) {
            val sha = part.optString("sha256")
            val target = File(cacheDir, sha)
            val partBytes = part.optLong("size_bytes", 0L)
            val startedAt = doneBytes

            val ok = try {
                api.downloadArtifact(
                    sha,
                    target,
                    onProgress = { read, _ ->
                        onProgress?.invoke(InstallPhase.DOWNLOADING, startedAt + read, totalBytes)
                    },
                    isCancelled = isCancelled,
                )
            } catch (_: ApiClient.TransferCancelled) {
                AgentLog.i(TAG, "store install $packageName: cancelled by the user")
                return StoreInstall.Cancelled
            } catch (e: Exception) {
                AgentLog.w(TAG, "store install $packageName: ${e.message}")
                return StoreInstall.Failed(e.message ?: "the download failed")
            }

            if (!ok) {
                AgentLog.w(TAG, "store install $packageName: $sha failed verification")
                return StoreInstall.Failed("the download could not be verified")
            }
            doneBytes = startedAt + partBytes
            parts += target
        }
        if (parts.isEmpty()) return StoreInstall.Failed("nothing to install")

        // Last chance to stop: past this the installer owns the outcome.
        if (isCancelled?.invoke() == true) return StoreInstall.Cancelled

        onProgress?.invoke(InstallPhase.INSTALLING, totalBytes, totalBytes)
        val result = installer.install(packageName, parts)
        AgentLog.i(
            TAG,
            "store install $packageName: " +
                if (result.success) "installed versionCode ${installer.installedVersionCode(packageName)}"
                else "failed — ${result.message}"
        )
        if (InstallerCachePlan.discardAfterInstall(result.success)) {
            discardInstallerFiles(packageName, parts)
        }
        return if (result.success) StoreInstall.Done else StoreInstall.Failed(result.message)
    }

    /**
     * Clear cached artifacts nothing needs any more (W89).
     *
     * W88 stops the cache growing from here on, but could not touch what the
     * fielded devices had already accumulated: an app that is installed never
     * reaches the code that would discard its APK. This sweep asks the question
     * from the other side — *is there a remaining reason to keep this file?* — so
     * the backlog goes on the first sync after the upgrade.
     *
     * ⚠️ **`lastModified` is 0 for a file the agent cannot stat**, and an age of
     * "now" would then look like a file written in 1970 — comfortably older than
     * the guard, and deleted. Anything without a usable timestamp is treated as
     * brand new instead, which at worst keeps it another cycle.
     *
     * Best-effort throughout: this reclaims disk, and no part of it is worth
     * failing a converged reconcile over.
     */
    private fun sweepArtifactCache(desired: JSONObject) {
        runCatching {
            val now = System.currentTimeMillis()
            val present = cacheDir.listFiles()?.filter { it.isFile } ?: return
            val byName = present.associateBy { it.name }
            val doomed = ArtifactSweepPlan.sweep(
                names = present.map { it.name },
                ageMillis = { name ->
                    val modified = byName[name]?.lastModified() ?: 0L
                    if (modified <= 0L) 0L else now - modified
                },
                desired = desired,
                installedVersionCode = { installer.installedVersionCode(it) },
                keep = setOfNotNull(config.pendingSelfUpdateSha),
            )
            if (doomed.isEmpty()) return
            var freed = 0L
            for (name in doomed) {
                val file = byName[name] ?: continue
                val size = file.length()
                if (file.delete()) freed += size
                else AgentLog.w(TAG, "cache sweep: could not delete $name")
            }
            AgentLog.i(
                TAG,
                "cache sweep: reclaimed ${freed / 1024} KB from ${doomed.size} spent artifact(s)"
            )
        }.onFailure { AgentLog.w(TAG, "cache sweep failed: ${it.message}") }
    }

    /**
     * Throw away the APK the *previous* build of the agent installed (W88).
     *
     * ⚠️ **This is the one install nobody can clean up after themselves.**
     * `selfUpdate` hands the agent's own APK to `PackageInstaller` and the process
     * is killed part-way through, so no line after that call ever runs. It is also
     * the largest file the agent writes — about 21 MB, one per build shipped —
     * which on a device that has taken a few updates is the bulk of the cache.
     *
     * The previous build recorded the sha before dying. Reaching here at or above
     * the version it was fetching means the install landed, so the file is spent.
     * Reaching here *below* it means the update did not take, and the download is
     * kept for the retry.
     */
    private fun discardFinishedSelfUpdate() {
        val sha = config.pendingSelfUpdateSha ?: return
        val wanted = config.pendingSelfUpdateVersionCode
        if (!InstallerCachePlan.selfUpdateFinished(BuildConfig.VERSION_CODE.toLong(), wanted)) {
            AgentLog.d(
                TAG,
                "agent update to $wanted did not take (running ${BuildConfig.VERSION_CODE}); " +
                    "keeping its download"
            )
            return
        }
        discardInstallerFiles(context.packageName, listOf(File(cacheDir, sha)))
        config.clearPendingSelfUpdate()
    }

    /**
     * Throw away the installer files for an app that is now installed (W88).
     *
     * `PackageInstaller` copies what it is given into the system's own store, so
     * once the install succeeds our copy is dead weight — and an APK is the
     * largest thing the agent ever writes. A fleet on a 32 GB tablet was
     * accumulating one copy of every app it had ever been sent.
     *
     * ⚠️ **Only after a success, and never on a failure.** The cache is what a
     * retry resumes from: a download that verified is byte-correct, so re-fetching
     * it over a field connection would buy nothing. A failed install is retried
     * next sync and finds its parts still there.
     *
     * ⚠️ **Only files this install owns.** Deleting by sweeping the cache would
     * race [installFromStore], which downloads on the Apps screen while a sync
     * runs — the parts would go between the download verifying and
     * `PackageInstaller` opening them.
     *
     * Failure to delete is logged and otherwise ignored. The app is installed;
     * the disk not being reclaimed is not worth failing a converged reconcile.
     */
    private fun discardInstallerFiles(packageName: String, parts: List<File>) {
        var freed = 0L
        for (part in parts) {
            val size = part.length()
            if (part.delete()) freed += size
            else AgentLog.w(TAG, "$packageName: could not discard installer file ${part.name}")
        }
        if (freed > 0) {
            AgentLog.d(TAG, "$packageName: discarded ${freed / 1024} KB of installer files")
        }
    }

    private fun downloadArtifact(
        sha256: String,
        target: File,
        onProgress: ((Long, Long) -> Unit)? = null,
    ): Boolean {
        // ⚠️ The cache hit reports completion before returning. Without it an app
        // already in the cache shows no notification at all, and the device looks
        // idle through the part where it is about to install something.
        if (target.exists() && ApiClient.sha256Of(target) == sha256.lowercase()) {
            onProgress?.invoke(target.length(), target.length())
            return true
        }
        return runCatching { api.downloadArtifact(sha256, target, onProgress) }.getOrElse {
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
         * Serialises enrollment across every `Reconciler` in the process.
         *
         * ⚠️ Class-level, not per-instance, and that is the whole point: at
         * provisioning `PolicyComplianceActivity` runs a sync directly while
         * `MdmDeviceAdminReceiver` starts the scheduler, and each builds its own
         * `Reconciler`. An instance lock would have serialised nothing.
         */
        private val ENROLL_LOCK = Any()

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
