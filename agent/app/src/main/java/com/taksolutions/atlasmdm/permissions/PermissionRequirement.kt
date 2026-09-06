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
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Environment
import android.os.PowerManager
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

    /** Losing this degrades the agent but does not stop it working. */
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
            Notifications,
            // Last, because it is the only one that is optional in practice - and
            // the only one that cannot be granted later, since a locked device
            // cannot open Android's settings to reach it (W72).
            PowerMenu,
        )

        /** Those needing a human. The rest a Device Owner grants for itself. */
        fun needingUserAction(context: Context): List<PermissionRequirement> =
            ALL.filter { it.grantIntent(context) != null && !it.isGranted(context) }

        /** Names of everything still missing, for reporting to the server. */
        fun outstanding(context: Context): List<String> =
            ALL.filterNot { it.isGranted(context) }.map { it.id }
    }
}
