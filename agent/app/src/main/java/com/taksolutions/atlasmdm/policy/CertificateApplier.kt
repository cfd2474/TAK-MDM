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

package com.taksolutions.atlasmdm.policy

import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import com.taksolutions.atlasmdm.admin.MdmDeviceAdminReceiver
import com.taksolutions.atlasmdm.core.AgentConfig
import com.taksolutions.atlasmdm.diag.AgentLog
import org.json.JSONArray

/**
 * Certificate authorities this device trusts (W112).
 *
 * ⚠️ **Removal is the dangerous half, and `uninstallAllUserCaCerts` is the trap.**
 * It is the convenient call in the API and it is the wrong one: it removes every
 * user-installed anchor, including ones a person added themselves for their own
 * reasons. This class removes **only what it installed**, recorded by sha256 —
 * the rule `hiddenByPolicy` already follows for packages, and for the same reason:
 * "everything currently trusted" is not the same set as "everything we trusted".
 *
 * ⚠️ **Absent means removed, and here that is a security property rather than
 * tidiness.** Everywhere else a policy that stops applying leaves a stale setting;
 * a trust anchor left behind is a device still trusting a CA the operator revoked.
 * So this runs on every reconcile and drives the set to exactly what policy says,
 * the way `applyPassword` drives its fields (R14).
 */
class CertificateApplier(
    private val context: Context,
    private val fetch: (String) -> ByteArray?,
) {

    private val config: AgentConfig by lazy { AgentConfig(context) }
    private val dpm: DevicePolicyManager? =
        context.getSystemService(DevicePolicyManager::class.java)
    private val admin = ComponentName(context, MdmDeviceAdminReceiver::class.java)

    /**
     * Make the installed anchors match [wanted], and report what could not be done.
     *
     * [wanted] is the `certificates` array from the desired state: objects with
     * `sha256`, `name` and `available`.
     */
    fun apply(wanted: JSONArray): List<String> {
        val manager = dpm ?: return listOf("certificates: no device policy service")
        if (!manager.isDeviceOwnerApp(context.packageName)) {
            return if (wanted.length() == 0) emptyList()
            else listOf("certificates: not device owner; cannot manage trust")
        }

        val failures = mutableListOf<String>()
        val desired = CertificatePlan.wanted(wanted)
        failures += CertificatePlan.unavailable(wanted)

        val installedByUs = config.caCertsInstalled.toMutableSet()

        // --- add what is missing ------------------------------------------- //
        for (entry in desired) {
            if (installedByUs.contains(entry.sha256)) continue

            val bytes = fetch(entry.sha256)
            if (bytes == null) {
                failures += "certificate ${entry.name}: could not be downloaded"
                continue
            }

            val ok = runCatching { manager.installCaCert(admin, bytes) }
                .onFailure { failures += "certificate ${entry.name}: ${it.message}" }
                .getOrDefault(false)

            if (ok) {
                installedByUs += entry.sha256
                config.rememberCaCert(entry.sha256, bytes)
                AgentLog.i(TAG, "trusted CA installed: ${entry.name}")
            } else if (failures.none { it.startsWith("certificate ${entry.name}") }) {
                // ⚠️ Returns false rather than throwing when the bytes cannot be
                // parsed — the same shape as setWifiEnabled (W72). Silence would
                // read as success.
                failures += "certificate ${entry.name}: the platform refused it " +
                    "(is it a PEM or DER certificate?)"
            }
        }

        // --- remove what we installed and policy no longer wants ------------ //
        val stillWanted = desired.map { it.sha256 }.toSet()
        for (sha in installedByUs.toList()) {
            if (stillWanted.contains(sha)) continue

            val bytes = config.rememberedCaCert(sha)
            if (bytes == null) {
                // ⚠️ Forgotten rather than guessed at. Without the original bytes
                // there is no way to name *which* anchor to remove, and the only
                // API that would work regardless removes everyone's.
                AgentLog.w(TAG, "cannot remove CA $sha: its bytes are no longer stored")
                installedByUs -= sha
                continue
            }

            runCatching { manager.uninstallCaCert(admin, bytes) }
                .onSuccess { AgentLog.i(TAG, "trusted CA removed: $sha") }
                .onFailure { failures += "removing a certificate: ${it.message}" }
            installedByUs -= sha
            config.forgetCaCert(sha)
        }

        config.caCertsInstalled = installedByUs
        return failures
    }

    companion object {
        private const val TAG = "CertificateApplier"
    }
}
