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

import android.accessibilityservice.AccessibilityService
import android.content.ComponentName
import android.content.Context
import android.provider.Settings
import android.view.accessibility.AccessibilityEvent
import com.taksolutions.atlasmdm.diag.AgentLog

/**
 * The only way an app can raise Android's power menu (W72).
 *
 * ⚠️ **It exists for exactly one call.** `performGlobalAction` is on
 * `AccessibilityService` and nowhere else, so a DPC that needs to offer "power
 * off" on a kiosk — where the side key may be mapped to the OEM's assistant and
 * no DPC can remap a hardware key — has to be an accessibility service to do it.
 *
 * ⚠️ **It observes nothing.** `accessibilityEventTypes` is `typeNotSet` and no
 * feedback type is requested, so this service receives no window content and no
 * keystrokes. An accessibility service on a managed device is a serious thing to
 * install; this one takes the narrowest shape that can still press the button.
 *
 * ⚠️ **The grant cannot be given from inside a kiosk.** Enabling an accessibility
 * service means visiting `com.android.settings`, which lock task blocks — so this
 * has to be switched on **before** the device is locked down. The Device Settings
 * screen says so rather than offering a button that would do nothing.
 */
class PowerMenuService : AccessibilityService() {

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
        AgentLog.i(TAG, "power menu service connected")
    }

    override fun onUnbind(intent: android.content.Intent?): Boolean {
        instance = null
        AgentLog.i(TAG, "power menu service unbound")
        return super.onUnbind(intent)
    }

    override fun onDestroy() {
        instance = null
        super.onDestroy()
    }

    /** Required by the base class; this service deliberately watches nothing. */
    override fun onAccessibilityEvent(event: AccessibilityEvent?) = Unit

    override fun onInterrupt() = Unit

    companion object {
        private const val TAG = "PowerMenuService"

        /**
         * ⚠️ Held statically because the system owns the instance and gives no
         * other handle on it. Cleared on unbind and destroy, so a stale reference
         * cannot outlive the service and report a power menu that is no longer
         * reachable.
         */
        @Volatile
        private var instance: PowerMenuService? = null

        /**
         * True when the service is enabled **and** running.
         *
         * ⚠️ Both, not either. `ENABLED_ACCESSIBILITY_SERVICES` can name a service
         * that has not bound yet, and a live instance can outlast the setting for
         * a moment — reporting the menu as available in either window would give
         * the user a row that does nothing when tapped.
         */
        fun isAvailable(context: Context): Boolean =
            instance != null && isEnabledInSettings(context)

        /** Whether the user has switched it on, regardless of binding state. */
        fun isEnabledInSettings(context: Context): Boolean {
            val wanted = ComponentName(context, PowerMenuService::class.java)
            val enabled = runCatching {
                Settings.Secure.getString(
                    context.contentResolver,
                    Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES,
                )
            }.getOrNull().orEmpty()
            // The setting is a colon-separated list of flattened component names,
            // and both the short and long forms appear in the wild.
            return enabled.split(':').any {
                it.equals(wanted.flattenToString(), ignoreCase = true) ||
                    it.equals(wanted.flattenToShortString(), ignoreCase = true)
            }
        }

        /**
         * Raise the power menu.
         *
         * @return false when the service is not available, so the caller can say
         *   why rather than appearing to do nothing.
         */
        fun show(): Boolean {
            val service = instance ?: run {
                AgentLog.w(TAG, "power menu asked for, but the service is not running")
                return false
            }
            return runCatching {
                service.performGlobalAction(GLOBAL_ACTION_POWER_DIALOG)
            }.getOrElse {
                AgentLog.w(TAG, "could not raise the power menu: ${it.message}")
                false
            }
        }
    }
}
