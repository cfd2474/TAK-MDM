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

package org.takmdm.agent.admin

import android.app.admin.DevicePolicyManager
import android.content.Intent
import android.os.Bundle
import android.os.PersistableBundle
import android.util.Log
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.takmdm.agent.R
import org.takmdm.agent.core.AgentConfig
import org.takmdm.agent.sync.Reconciler
import org.takmdm.agent.sync.SyncScheduler

/**
 * The last step of provisioning, and where this agent actually starts.
 *
 * **Required from Android 12, and it replaces `onProfileProvisioningComplete`.**
 * The documentation is explicit that a DPC must stop relying on that broadcast:
 * on a modern device it is this activity, not the receiver, that runs.
 *
 * Enrollment happens here because this is the first moment the agent has both the
 * admin extras and Device Owner privilege.
 */
class PolicyComplianceActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_policy_compliance)

        val status = findViewById<TextView>(R.id.compliance_status)
        val config = AgentConfig(this)

        val extras = intent.getParcelableExtra(
            DevicePolicyManager.EXTRA_PROVISIONING_ADMIN_EXTRAS_BUNDLE,
            PersistableBundle::class.java
        )
        config.seedFromProvisioning(extras)

        Log.i(
            TAG,
            "policy compliance: server=${config.serverUrl} " +
                "token=${config.enrollmentToken?.take(8)}… " +
                "deviceOwner=${MdmDeviceAdminReceiver.isDeviceOwner(this)}"
        )

        if (config.serverUrl.isNullOrBlank()) {
            // Provisioning still succeeded; the device is managed. Say so rather
            // than failing, and let it be configured later.
            status.text = getString(R.string.compliance_no_server)
            finishOk()
            return
        }

        status.text = getString(R.string.compliance_enrolling)

        lifecycleScope.launch {
            val outcome = withContext(Dispatchers.IO) {
                runCatching { Reconciler(applicationContext).sync() }
            }

            outcome.onSuccess {
                Log.i(TAG, "enrolled at provisioning: state=${it.stateVersion} errors=${it.errors}")
                status.text = getString(R.string.compliance_done)
            }.onFailure {
                // Deliberately not fatal. Provisioning has succeeded and cannot be
                // repeated without another factory reset, so a network blip here
                // must not undo it — the agent retries on its own schedule.
                Log.e(TAG, "enrollment during provisioning failed; will retry", it)
                status.text = getString(R.string.compliance_retry)
            }

            SyncScheduler.startAll(applicationContext)
            finishOk()
        }
    }

    private fun finishOk() {
        setResult(RESULT_OK, Intent())
        finish()
    }

    companion object {
        private const val TAG = "PolicyCompliance"
    }
}
