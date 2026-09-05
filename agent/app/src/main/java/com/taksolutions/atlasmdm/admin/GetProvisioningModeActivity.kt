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

package com.taksolutions.atlasmdm.admin

import android.app.Activity
import android.app.admin.DevicePolicyManager
import android.content.Intent
import android.os.Bundle
import com.taksolutions.atlasmdm.diag.AgentLog

/**
 * Answers the system's `GET_PROVISIONING_MODE` question during provisioning.
 *
 * **Required from Android 12.** Without a handler for this action the system
 * downloads the DPC, installs it, launches this intent, finds nothing, and aborts
 * with a bare "something went wrong" — no logs, after a factory reset. Three
 * failed enrolments were this.
 *
 * There is no UI: the answer is always the same, so showing a screen would only
 * add a tap to every device rollout.
 */
class GetProvisioningModeActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val allowed = intent
            .getIntegerArrayListExtra(EXTRA_ALLOWED_PROVISIONING_MODES)
            ?.toList()
            .orEmpty()

        // Fully managed is what this product is for. Honour the system's list when
        // it supplies one rather than asserting a mode it has already ruled out —
        // an unsupported answer fails provisioning just as surely as no answer.
        val mode = when {
            allowed.isEmpty() ||
                DevicePolicyManager.PROVISIONING_MODE_FULLY_MANAGED_DEVICE in allowed ->
                DevicePolicyManager.PROVISIONING_MODE_FULLY_MANAGED_DEVICE
            else -> allowed.first()
        }

        AgentLog.i(TAG, "provisioning mode: $mode (allowed=$allowed)")

        val result = Intent().putExtra(
            DevicePolicyManager.EXTRA_PROVISIONING_MODE, mode
        )

        // Pass the admin extras through so PolicyComplianceActivity receives the
        // server URL and enrollment token the QR carried.
        intent.getParcelableExtra(
            DevicePolicyManager.EXTRA_PROVISIONING_ADMIN_EXTRAS_BUNDLE,
            android.os.PersistableBundle::class.java
        )?.let {
            result.putExtra(DevicePolicyManager.EXTRA_PROVISIONING_ADMIN_EXTRAS_BUNDLE, it)
        }

        setResult(RESULT_OK, result)
        // Deliberately nothing else: the documentation is explicit that a DPC must
        // not start activities or background services before returning to setup.
        finish()
    }

    companion object {
        private const val TAG = "GetProvisioningMode"
        private const val EXTRA_ALLOWED_PROVISIONING_MODES =
            "android.app.extra.PROVISIONING_ALLOWED_PROVISIONING_MODES"
    }
}
