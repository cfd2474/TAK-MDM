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

package com.taksolutions.atlaslauncher

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.drawable.Drawable
import android.util.Log

/** One tile: what to draw, and what to start. */
data class AppEntry(
    val ref: LauncherConfig.AppRef,
    val label: String,
    val icon: Drawable?,
    val intent: Intent,
)

/**
 * Turns the configured references into things that can actually be drawn and
 * started (W68).
 *
 * ⚠️ **A configured app that is not installed is dropped, not drawn dead.** The
 * agent installs the kiosk's apps and this launcher separately, so there is a
 * real window in which policy names an app the device does not have yet. A tile
 * that does nothing when tapped is worse than no tile: the user cannot tell it
 * from a frozen device, and the next check-in fixes it anyway.
 *
 * ⚠️ Everything here depends on the manifest's `<queries>`. Without it
 * `getLaunchIntentForPackage` returns null for every package on Android 11+ and
 * this class quietly reports an empty device.
 */
class AppCatalog(private val context: Context) {

    private val pm: PackageManager get() = context.packageManager

    /** The configured apps that exist on this device, in the configured order. */
    fun resolve(refs: List<LauncherConfig.AppRef>): List<AppEntry> =
        refs.mapNotNull(::entryFor)

    private fun entryFor(ref: LauncherConfig.AppRef): AppEntry? {
        val intent = intentFor(ref) ?: run {
            Log.i(TAG, "${ref.packageName} is configured but not installed; skipping")
            return null
        }
        return runCatching {
            val info = pm.getApplicationInfo(ref.packageName, 0)
            AppEntry(
                ref = ref,
                // The app's own name, not the package: a grid of package names is
                // what the console looked like before it read labels, and it was
                // unusable for exactly the same reason.
                label = pm.getApplicationLabel(info).toString(),
                icon = runCatching { pm.getApplicationIcon(info) }.getOrNull(),
                intent = intent,
            )
        }.getOrNull()
    }

    private fun intentFor(ref: LauncherConfig.AppRef): Intent? {
        if (ref.activity != null) {
            // An explicit component: the kiosk screen may deliberately not be the
            // app's default entry, and some are not exported as launchers at all.
            val intent = Intent(Intent.ACTION_MAIN)
                .setClassName(ref.packageName, ref.activity)
            // Asked, not assumed — starting a component that does not resolve
            // throws, and this runs while drawing the home screen.
            return if (intent.resolveActivity(pm) != null) intent else null
        }
        return pm.getLaunchIntentForPackage(ref.packageName)
    }

    private companion object {
        const val TAG = "AppCatalog"
    }
}
