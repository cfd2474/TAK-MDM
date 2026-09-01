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
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.takmdm.agent.R
import org.takmdm.agent.core.AgentConfig
import org.takmdm.agent.permissions.PermissionRequirement
import org.takmdm.agent.policy.PolicyApplier
import org.takmdm.agent.sync.Reconciler
import org.takmdm.agent.sync.SyncScheduler

/**
 * The last step of provisioning: grant what Android will not let us grant, then
 * enrol.
 *
 * **Required from Android 12, and it replaces `onProfileProvisioningComplete`** —
 * on a modern device it is this activity, not the receiver, that runs.
 *
 * This is the one moment the operator is already holding the device and expecting
 * to interact with it. Everything requiring a human tap is collected here, so a
 * deployed tablet never later turns out to be silently missing a capability.
 *
 * Runtime permissions are granted first, silently, using Device Owner privilege.
 * Only app-ops — which `setPermissionGrantState` cannot reach — are put in front of
 * the operator. Prompting for things we could grant ourselves would waste a tap on
 * every device in the fleet.
 */
class PolicyComplianceActivity : AppCompatActivity() {

    private lateinit var config: AgentConfig
    private lateinit var status: TextView
    private lateinit var steps: LinearLayout
    private lateinit var continueButton: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_policy_compliance)

        config = AgentConfig(this)
        status = findViewById(R.id.compliance_status)
        steps = findViewById(R.id.permission_steps)
        continueButton = findViewById(R.id.compliance_continue)

        val extras = intent.getParcelableExtra(
            DevicePolicyManager.EXTRA_PROVISIONING_ADMIN_EXTRAS_BUNDLE,
            PersistableBundle::class.java
        )
        config.seedFromProvisioning(extras)

        Log.i(
            TAG,
            "policy compliance: server=${config.serverUrl} " +
                "deviceOwner=${MdmDeviceAdminReceiver.isDeviceOwner(this)}"
        )

        // Take what we are entitled to before asking for anything.
        grantWhatWeCan()

        continueButton.setOnClickListener { finishProvisioning() }
    }

    override fun onResume() {
        super.onResume()
        // Re-read on every return: the operator has just come back from a Settings
        // screen and the state has probably changed.
        renderSteps()
    }

    private fun grantWhatWeCan() {
        val applier = PolicyApplier(this)
        if (!applier.isDeviceOwner) {
            Log.w(TAG, "not device owner; runtime permissions cannot be pre-granted")
            return
        }
        // Note this respects R9: our own manifest declares MANAGE_EXTERNAL_STORAGE,
        // so the legacy storage permissions are deliberately skipped for us too.
        val failures = applier.grantRuntimePermissions(packageName)
        failures.forEach { Log.w(TAG, "self-grant: $it") }
    }

    private fun renderSteps() {
        steps.removeAllViews()
        val outstanding = PermissionRequirement.needingUserAction(this)

        if (outstanding.isEmpty()) {
            status.setText(R.string.compliance_all_set)
            continueButton.setText(R.string.compliance_finish)
            return
        }

        status.setText(R.string.compliance_grant_intro)
        continueButton.setText(R.string.compliance_skip_rest)

        for (requirement in PermissionRequirement.ALL) {
            if (requirement.grantIntent(this) == null) continue  // granted silently
            steps.addView(buildRow(requirement))
        }
    }

    private fun buildRow(requirement: PermissionRequirement): View {
        val row = layoutInflater.inflate(R.layout.item_permission_step, steps, false)
        val granted = requirement.isGranted(this)

        row.findViewById<TextView>(R.id.step_title).text = requirement.title
        row.findViewById<TextView>(R.id.step_rationale).text = requirement.rationale

        val action = row.findViewById<Button>(R.id.step_action)
        val state = row.findViewById<TextView>(R.id.step_state)

        if (granted) {
            state.setText(R.string.compliance_granted)
            state.visibility = View.VISIBLE
            action.visibility = View.GONE
        } else {
            state.visibility = View.GONE
            action.visibility = View.VISIBLE
            action.setOnClickListener {
                // No result handling: onResume re-reads the real state, which is
                // more reliable than trusting a result code from a Settings screen.
                runCatching { startActivity(requirement.grantIntent(this)) }
                    .onFailure { Log.e(TAG, "could not open grant screen", it) }
            }
        }
        return row
    }

    /**
     * Enrol and return to setup.
     *
     * Always finishes with `RESULT_OK`, even when something went wrong.
     * Provisioning cannot be repeated without another factory reset, so a network
     * blip or a declined permission must not undo it. Whatever is missing is
     * reported to the server instead, where it shows as a compliance gap.
     */
    private fun finishProvisioning() {
        continueButton.isEnabled = false
        val missing = PermissionRequirement.outstanding(this)
        if (missing.isNotEmpty()) Log.w(TAG, "continuing without: $missing")

        if (config.serverUrl.isNullOrBlank()) {
            status.setText(R.string.compliance_no_server)
            finishOk()
            return
        }

        status.setText(R.string.compliance_enrolling)
        lifecycleScope.launch {
            val outcome = withContext(Dispatchers.IO) {
                runCatching { Reconciler(applicationContext).sync() }
            }
            outcome.onSuccess {
                Log.i(TAG, "enrolled: state=${it.stateVersion} errors=${it.errors}")
            }.onFailure {
                Log.e(TAG, "enrollment failed; the agent will retry", it)
                status.setText(R.string.compliance_retry)
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
