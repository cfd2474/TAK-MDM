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

package org.takmdm.agent.policy

import android.app.admin.DevicePolicyManager
import android.content.Context
import android.content.pm.PackageManager
import android.os.UserManager
import android.util.Log
import org.json.JSONObject
import org.takmdm.agent.admin.MdmDeviceAdminReceiver

/**
 * Applies the AOSP-expressible parts of a desired state through
 * [DevicePolicyManager].
 *
 * Every method reports what failed rather than throwing: one unsupported
 * restriction must not abandon the rest of the policy. The collected failures go
 * back to the server as `apply_errors`, which is what turns a device DEGRADED
 * instead of silently non-compliant.
 */
class PolicyApplier(private val context: Context) {

    private val dpm: DevicePolicyManager =
        context.getSystemService(DevicePolicyManager::class.java)

    private val admin = MdmDeviceAdminReceiver.componentName(context)

    private val oem: OemPolicyApplier by lazy { OemPolicyApplier.forDevice(context) }

    val isDeviceOwner: Boolean
        get() = dpm.isDeviceOwnerApp(context.packageName)

    fun apply(policy: JSONObject): List<String> {
        if (!isDeviceOwner) {
            return listOf("not device owner; policy cannot be applied")
        }
        val failures = mutableListOf<String>()
        policy.optJSONObject("PASSWORD")?.let { failures += applyPassword(it) }
        policy.optJSONObject("RESTRICTIONS")?.let { failures += applyRestrictions(it) }
        policy.optJSONObject("APP_CATALOG")?.let { failures += applyAppCatalog(it) }
        return failures
    }

    // ----------------------------------------------------------------------- //
    // Passcode
    // ----------------------------------------------------------------------- //

    private fun applyPassword(spec: JSONObject): List<String> {
        val failures = mutableListOf<String>()

        runCatching {
            // Android 12 deprecated the granular setPasswordMinimum* family in
            // favour of complexity buckets. Mapping the server's numeric strength
            // onto a bucket keeps the policy meaningful on modern releases.
            val complexity = when {
                spec.optInt("min_length", 0) >= 12 -> DevicePolicyManager.PASSWORD_COMPLEXITY_HIGH
                spec.optInt("min_length", 0) >= 8 -> DevicePolicyManager.PASSWORD_COMPLEXITY_MEDIUM
                spec.has("min_length") || spec.has("quality") ->
                    DevicePolicyManager.PASSWORD_COMPLEXITY_LOW
                else -> DevicePolicyManager.PASSWORD_COMPLEXITY_NONE
            }
            if (complexity != DevicePolicyManager.PASSWORD_COMPLEXITY_NONE) {
                dpm.requiredPasswordComplexity = complexity
            }
        }.onFailure { failures += "password complexity: ${it.message}" }

        if (spec.has("max_failed_attempts_before_wipe")) {
            runCatching {
                dpm.setMaximumFailedPasswordsForWipe(
                    admin, spec.getInt("max_failed_attempts_before_wipe")
                )
            }.onFailure { failures += "max failed attempts: ${it.message}" }
        }

        if (spec.has("lock_timeout_seconds")) {
            runCatching {
                dpm.setMaximumTimeToLock(admin, spec.getInt("lock_timeout_seconds") * 1000L)
            }.onFailure { failures += "lock timeout: ${it.message}" }
        }

        if (spec.has("expiration_days")) {
            runCatching {
                dpm.setPasswordExpirationTimeout(
                    admin, spec.getInt("expiration_days") * 86_400_000L
                )
            }.onFailure { failures += "password expiry: ${it.message}" }
        }

        return failures
    }

    // ----------------------------------------------------------------------- //
    // Restrictions
    // ----------------------------------------------------------------------- //

    /**
     * Server field names are all phrased as "allow"; user restrictions are phrased
     * as "disallow". The inversion happens once, here, rather than at each call
     * site where a missed negation would quietly permit something.
     */
    private val restrictionMap = mapOf(
        "allow_usb_file_transfer" to UserManager.DISALLOW_USB_FILE_TRANSFER,
        "allow_factory_reset" to UserManager.DISALLOW_FACTORY_RESET,
        "allow_safe_mode" to UserManager.DISALLOW_SAFE_BOOT,
        "allow_developer_options" to UserManager.DISALLOW_DEBUGGING_FEATURES,
        "allow_install_unknown_sources" to UserManager.DISALLOW_INSTALL_UNKNOWN_SOURCES,
        "allow_outgoing_calls" to UserManager.DISALLOW_OUTGOING_CALLS,
        "allow_bluetooth" to UserManager.DISALLOW_BLUETOOTH,
        "allow_location_services" to UserManager.DISALLOW_SHARE_LOCATION
    )

    private fun applyRestrictions(spec: JSONObject): List<String> {
        val failures = mutableListOf<String>()

        for ((allowKey, restriction) in restrictionMap) {
            if (!spec.has(allowKey)) continue
            val allowed = spec.optBoolean(allowKey, true)
            runCatching {
                if (allowed) dpm.clearUserRestriction(admin, restriction)
                else dpm.addUserRestriction(admin, restriction)
            }.onFailure { failures += "$allowKey: ${it.message}" }
        }

        if (spec.has("allow_camera")) {
            runCatching {
                dpm.setCameraDisabled(admin, !spec.getBoolean("allow_camera"))
            }.onFailure { failures += "camera: ${it.message}" }
        }

        if (spec.has("allow_screen_capture")) {
            runCatching {
                dpm.setScreenCaptureDisabled(admin, !spec.getBoolean("allow_screen_capture"))
            }.onFailure { failures += "screen capture: ${it.message}" }
        }

        failures += oem.applyRestrictions(context, spec)
        return failures
    }

    // ----------------------------------------------------------------------- //
    // Apps: blocklist and kiosk
    // ----------------------------------------------------------------------- //

    private fun applyAppCatalog(spec: JSONObject): List<String> {
        val failures = mutableListOf<String>()

        spec.optJSONArray("blocked_packages")?.let { blocked ->
            for (index in 0 until blocked.length()) {
                val packageName = blocked.optString(index)
                runCatching {
                    dpm.setApplicationHidden(admin, packageName, true)
                }.onFailure { failures += "block $packageName: ${it.message}" }
            }
        }

        // Kiosk is opt-in (F6). No kiosk_package means the agent stays a background
        // service and leaves the home screen alone.
        val kioskPackage = spec.optString("kiosk_package").takeIf { it.isNotBlank() }
        runCatching {
            if (kioskPackage != null) {
                dpm.setLockTaskPackages(admin, arrayOf(kioskPackage, context.packageName))
            } else {
                dpm.setLockTaskPackages(admin, emptyArray())
            }
        }.onFailure { failures += "kiosk: ${it.message}" }

        return failures
    }

    // ----------------------------------------------------------------------- //
    // Permission pre-granting
    // ----------------------------------------------------------------------- //

    /**
     * Pre-grant runtime permissions to a managed app.
     *
     * **R9:** on Android 11+, granting `WRITE_EXTERNAL_STORAGE` to an app
     * permanently prevents it from requesting `MANAGE_EXTERNAL_STORAGE`. An app that
     * needs all-files access — ATAK does — must therefore be denied the legacy
     * storage permissions, not given them. The obvious "grant everything it asks
     * for" loop breaks exactly the apps that matter, and does it silently.
     */
    fun grantRuntimePermissions(packageName: String): List<String> {
        if (!isDeviceOwner) return listOf("not device owner")
        val failures = mutableListOf<String>()

        val info = runCatching {
            context.packageManager.getPackageInfo(
                packageName, PackageManager.GET_PERMISSIONS
            )
        }.getOrNull() ?: return listOf("$packageName not installed")

        val requested = info.requestedPermissions?.toList().orEmpty()
        val wantsAllFiles = requested.contains(PERMISSION_MANAGE_EXTERNAL_STORAGE)

        runCatching {
            dpm.setPermissionPolicy(admin, DevicePolicyManager.PERMISSION_POLICY_AUTO_GRANT)
        }.onFailure { failures += "permission policy: ${it.message}" }

        for (permission in requested) {
            if (wantsAllFiles && permission in LEGACY_STORAGE_PERMISSIONS) {
                Log.i(
                    TAG,
                    "skipping $permission for $packageName: granting it would lock the " +
                        "app out of MANAGE_EXTERNAL_STORAGE (R9)"
                )
                continue
            }
            if (!isDangerous(permission)) continue

            runCatching {
                dpm.setPermissionGrantState(
                    admin, packageName, permission,
                    DevicePolicyManager.PERMISSION_GRANT_STATE_GRANTED
                )
            }.onFailure { failures += "$permission: ${it.message}" }
        }

        if (wantsAllFiles && !oem.grantAllFilesAccess(context, packageName)) {
            // Not a failure: no AOSP path exists, so this is a fact to report rather
            // than an error to retry.
            Log.i(TAG, "$packageName needs all-files access; requires a manual grant")
        }

        return failures
    }

    private fun isDangerous(permission: String): Boolean = runCatching {
        val info = context.packageManager.getPermissionInfo(permission, 0)
        (info.protection and android.content.pm.PermissionInfo.PROTECTION_DANGEROUS) != 0
    }.getOrDefault(false)

    companion object {
        private const val TAG = "PolicyApplier"
        private const val PERMISSION_MANAGE_EXTERNAL_STORAGE =
            "android.permission.MANAGE_EXTERNAL_STORAGE"
        private val LEGACY_STORAGE_PERMISSIONS = setOf(
            "android.permission.READ_EXTERNAL_STORAGE",
            "android.permission.WRITE_EXTERNAL_STORAGE"
        )
    }
}
