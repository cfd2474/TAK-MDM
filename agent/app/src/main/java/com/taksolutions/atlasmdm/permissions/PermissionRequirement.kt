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

package com.taksolutions.atlasmdm.permissions

import android.Manifest
import android.app.AppOpsManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Environment
import android.os.PowerManager
import android.os.Process
import android.provider.Settings
import androidx.core.content.ContextCompat

/**
 * A capability the agent needs, and how to obtain it.
 *
 * The important split is between what a Device Owner can grant itself and what it
 * cannot. Runtime permissions we simply take — asking the operator to tap through
 * something we could have granted silently wastes their time on every device in the
 * fleet. **App-ops** (`MANAGE_EXTERNAL_STORAGE`, overlay, battery exemption) are a
 * different mechanism that `setPermissionGrantState` does not reach, and those
 * genuinely need a human, once, at provisioning time.
 *
 * So the wizard only ever shows what actually requires a tap.
 */
sealed class PermissionRequirement {

    abstract val id: String
    abstract val title: String
    abstract val rationale: String

    /** Whether the capability is currently held. */
    abstract fun isGranted(context: Context): Boolean

    /**
     * The screen that grants it, or null when a Device Owner grants it silently.
     * A null intent means this requirement never appears in the wizard.
     */
    open fun grantIntent(context: Context): Intent? = null

    /**
     * True when the agent works without it.
     *
     * ⚠️ This decides whether a missing permission is reported as an **error** or
     * a warning, and an error marks the device DEGRADED - which
     * `agent_update.decide()` treats as "not applying its policy cleanly" and
     * refuses to send updates to. Getting it wrong on a permission no device has
     * shuts the agent-update channel fleet-wide.
     */
    open val optional: Boolean = false

    // ----------------------------------------------------------------------- //

    /**
     * All-files access, for writing to paths like `/sdcard/atak`, which is not a
     * MediaStore collection.
     *
     * An app-op, not a runtime permission, so a Device Owner cannot grant it to
     * itself — this is the one-time human step the whole wizard exists for.
     */
    data object AllFilesAccess : PermissionRequirement() {
        override val id = "all_files_access"
        override val title = "File access"
        override val rationale =
            "Lets managed files be placed in locations such as /sdcard/atak. " +
                "Android does not allow this to be granted automatically."

        override fun isGranted(context: Context) = Environment.isExternalStorageManager()

        override fun grantIntent(context: Context) = Intent(
            Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
            Uri.parse("package:${context.packageName}")
        )
    }

    /** Draw over other apps — needed for kiosk lockdown and compliance overlays. */
    data object DisplayOverOtherApps : PermissionRequirement() {
        override val id = "display_over_other_apps"
        override val title = "Display over other apps"
        override val rationale =
            "Lets the agent show lockdown and compliance messages over whatever " +
                "is on screen."

        override fun isGranted(context: Context) = Settings.canDrawOverlays(context)

        override fun grantIntent(context: Context) = Intent(
            Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
            Uri.parse("package:${context.packageName}")
        )
    }

    /**
     * Usage access, which is how the agent learns what is in front (W136).
     *
     * ⚠️ **An app-op, so a Device Owner cannot grant it to itself.**
     * `UsageStatsManager` is the only public way to know the foreground app,
     * and the device ID label needs it to stay on the home screen instead of
     * floating over ATAK's map.
     *
     * ⚠️ **The manifest has declared `PACKAGE_USAGE_STATS` since W44 and that
     * proves nothing.** It was declared as a *NetworkStats* fallback, which a
     * Device Owner is documented to get without a grant. That exemption is for
     * a different service; `queryEvents` has no such carve-out. Declaring the
     * permission is only what puts the agent in the Settings list.
     *
     * Optional: without it the label still shows, everywhere, and the warning
     * says so. A device that is labelled in the wrong place is a nuisance; a
     * device that is not labelled at all is the problem the label exists for.
     */
    data object UsageAccess : PermissionRequirement() {
        override val id = "usage_access"
        override val optional = true
        override val title = "Usage access"
        override val rationale =
            "Lets the agent tell when the home screen is in front, so the " +
                "device ID label appears there and not over whatever is running. " +
                "Without it the label shows over every app."

        override fun isGranted(context: Context): Boolean {
            val ops = context.getSystemService(AppOpsManager::class.java) ?: return false
            // ⚠️ MODE_ALLOWED only. MODE_DEFAULT means "fall back to the
            // permission", and PACKAGE_USAGE_STATS is signature-protected, so
            // the fallback is always a refusal — treating DEFAULT as granted
            // would make the watcher throw on every poll.
            val mode = runCatching {
                ops.unsafeCheckOpNoThrow(
                    AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), context.packageName
                )
            }.getOrDefault(AppOpsManager.MODE_ERRORED)
            return mode == AppOpsManager.MODE_ALLOWED
        }

        // ⚠️ No `package:` data. Some OEMs deep-link from it and some do not
        // resolve the intent at all when it carries a Uri, and an unresolvable
        // intent on the provisioning screen is a dead button on a screen that
        // cannot be revisited without a factory reset.
        override fun grantIntent(context: Context) = Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS)
    }

    /**
     * The accessibility service behind the kiosk power menu (W72).
     *
     * ⚠️ **Grant this before locking a device down.** The switch lives in
     * `com.android.settings`, which lock task blocks, so a kiosk cannot be talked
     * through enabling it afterwards — the device would have to leave kiosk first.
     *
     * Optional in the sense that everything else works without it; the Power off
     * row then explains itself instead of appearing to fail.
     */
    data object PowerMenu : PermissionRequirement() {
        override val id = "power_menu"

        /**
         * ⚠️ **Optional, and that is load-bearing.** Everything else here is
         * needed for the agent to do its job, so its absence is a policy failure.
         * This one only adds a Power off row, and reporting it as a failure marks
         * the device DEGRADED - which `agent_update.decide()` treats as "not
         * applying its policy cleanly" and refuses to send updates to.
         *
         * Agent 79 did exactly that: it shut its own update channel on every
         * device that had not been granted an accessibility service.
         */
        override val optional = true
        override val title = "ATLAS power menu"
        override val rationale =
            "Lets a kiosk user reach the power menu, which the side key may not " +
                "raise. Grant it before the device is locked down - a kiosk " +
                "cannot open Android's settings to switch it on later."

        override fun isGranted(context: Context) =
            com.taksolutions.atlasmdm.ui.PowerMenuService.isEnabledInSettings(context)

        override fun grantIntent(context: Context) =
            Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)
    }

    /**
     * Battery optimization exemption.
     *
     * Without it the system will eventually defer the sync service and the
     * long-poll, which turns immediate policy propagation into "sometime later" —
     * the failure is silent and looks like a server problem.
     */
    data object BatteryExemption : PermissionRequirement() {
        override val id = "battery_exemption"
        override val title = "Unrestricted battery use"
        override val rationale =
            "Stops Android suspending the agent, which would delay policy and " +
                "remote commands."

        override fun isGranted(context: Context): Boolean {
            val power = context.getSystemService(PowerManager::class.java)
            return power?.isIgnoringBatteryOptimizations(context.packageName) == true
        }

        @android.annotation.SuppressLint("BatteryLife")
        override fun grantIntent(context: Context) = Intent(
            Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
            Uri.parse("package:${context.packageName}")
        )
    }

    /**
     * Location. A runtime permission, so a Device Owner grants it silently — it is
     * listed only so the operator can see it was handled.
     */
    data object Location : PermissionRequirement() {
        override val id = "location"
        override val title = "Location"
        override val rationale = "Needed to answer a locate command."

        override fun isGranted(context: Context) =
            ContextCompat.checkSelfPermission(
                context, Manifest.permission.ACCESS_FINE_LOCATION
            ) == PackageManager.PERMISSION_GRANTED
    }

    /**
     * Background location, for periodic reporting while the screen is off (W106).
     *
     * ⚠️ **Listed separately from [Location] because it fails separately.** With
     * foreground location alone, tracking works perfectly for as long as someone is
     * looking at the tablet and stops the moment they are not — which reads as a
     * flaky agent rather than as a missing permission. Showing it as its own line
     * is the difference between diagnosing that in a minute and in an afternoon.
     *
     * A Device Owner self-grants it like any other `dangerous` permission. That is
     * assembled from the permission's protection level plus Android's enterprise
     * notes rather than stated outright anywhere, so this row is also how a device
     * tells us the assembly was wrong.
     */
    data object BackgroundLocation : PermissionRequirement() {
        override val id = "background_location"
        override val title = "Background location"
        override val rationale =
            "Needed to record location while the screen is off. Without it, " +
                "tracking works only while the device is in use."
        override val optional = true

        override fun isGranted(context: Context) =
            ContextCompat.checkSelfPermission(
                context, Manifest.permission.ACCESS_BACKGROUND_LOCATION
            ) == PackageManager.PERMISSION_GRANTED
    }

    /** Notifications, for the foreground service. Runtime, granted silently. */
    data object Notifications : PermissionRequirement() {
        override val id = "notifications"
        override val title = "Notifications"
        override val rationale = "Required for the agent's ongoing status notice."
        override val optional = true

        override fun isGranted(context: Context) =
            ContextCompat.checkSelfPermission(
                context, Manifest.permission.POST_NOTIFICATIONS
            ) == PackageManager.PERMISSION_GRANTED
    }

    companion object {
        /** Every requirement, in the order the wizard should present them. */
        val ALL: List<PermissionRequirement> = listOf(
            AllFilesAccess,
            DisplayOverOtherApps,
            BatteryExemption,
            Location,
            BackgroundLocation,
            Notifications,
            UsageAccess,
            // Last, because it is the only one that is optional in practice - and
            // the only one that cannot be granted later, since a locked device
            // cannot open Android's settings to reach it (W72).
            PowerMenu,
        )

        /** Those needing a human. The rest a Device Owner grants for itself. */
        fun needingUserAction(context: Context): List<PermissionRequirement> =
            ALL.filter { it.grantIntent(context) != null && !it.isGranted(context) }

        /**
         * Names of the **required** permissions still missing.
         *
         * ⚠️ Required only. The caller reports these as errors, and an error puts
         * the device in DEGRADED - which stops the agent-update channel offering
         * it anything. A missing optional permission must never do that.
         */
        fun outstanding(context: Context): List<String> =
            ALL.filterNot { it.optional }.filterNot { it.isGranted(context) }.map { it.id }

        /** Missing optional permissions, for reporting as warnings. */
        fun outstandingOptional(context: Context): List<PermissionRequirement> =
            ALL.filter { it.optional }.filterNot { it.isGranted(context) }
    }
}
