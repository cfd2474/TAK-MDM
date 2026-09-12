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

package com.taksolutions.atlasmdm.ui

import android.content.Context
import com.taksolutions.atlasmdm.diag.AgentLog
import com.taksolutions.atlasmdm.permissions.PermissionRequirement

/**
 * Holds the device ID label together: policy, moment, and window (W136).
 *
 * Three objects rather than one, because they fail for different reasons and
 * only one of them can be tested. [DeviceIdLabelPlan] decides, [HomeScreenWatcher]
 * observes, [DeviceIdOverlay] draws, and this says who talks to whom.
 *
 * The reconcile calls [set] and nothing else — it knows what the label *says*
 * and has no business knowing when a launcher is in front.
 */
object DeviceIdLabelController {

    private const val TAG = "DeviceIdLabel"

    private var label: String? = null
    private var warnedUngated = false

    /** What the policy wants shown, or null to take the label away. */
    @Synchronized
    fun set(context: Context, name: String?) {
        val app = context.applicationContext
        label = name?.takeIf { it.isNotBlank() }

        if (label == null) {
            HomeScreenWatcher.stop(app)
            DeviceIdOverlay.set(app, null)
            warnedUngated = false
            return
        }

        if (PermissionRequirement.UsageAccess.isGranted(app)) {
            warnedUngated = false
            HomeScreenWatcher.start(app) { onHome -> render(app, onHome, gated = true) }
            // The watcher reports only on a *change*, so the state it is already
            // in has to be read once here. Without this a policy re-applied
            // while the watcher is running would leave the window as it was.
            render(app, HomeScreenWatcher.onHome, gated = true)
        } else {
            // Said once, not every two minutes: the reconcile already reports
            // the missing permission to the console as a warning, and this is
            // only here for someone reading a device's log.
            if (!warnedUngated) {
                AgentLog.w(
                    TAG,
                    "usage access is not granted, so the device ID label cannot be " +
                        "limited to the home screen; showing it everywhere"
                )
                warnedUngated = true
            }
            HomeScreenWatcher.stop(app)
            render(app, onHome = false, gated = false)
        }
    }

    private fun render(context: Context, onHome: Boolean, gated: Boolean) {
        val name = label
        DeviceIdOverlay.set(
            context,
            if (DeviceIdLabelPlan.visible(name, onHome, gated)) name else null,
        )
    }
}
