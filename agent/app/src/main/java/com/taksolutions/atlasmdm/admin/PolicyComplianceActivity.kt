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

import android.app.admin.DevicePolicyManager
import android.content.Intent
import android.os.Bundle
import android.os.PersistableBundle
import com.taksolutions.atlasmdm.diag.AgentLog
import android.view.View
import android.app.AlertDialog
import android.text.InputFilter
import android.text.InputType
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import com.taksolutions.atlasmdm.R
import com.taksolutions.atlasmdm.core.AgentConfig
import com.taksolutions.atlasmdm.net.ApiClient
import com.taksolutions.atlasmdm.permissions.PermissionRequirement
import com.taksolutions.atlasmdm.policy.PolicyApplier
import com.taksolutions.atlasmdm.sync.Reconciler
import com.taksolutions.atlasmdm.sync.SyncScheduler

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
    private lateinit var overrideButton: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_policy_compliance)

        config = AgentConfig(this)
        status = findViewById(R.id.compliance_status)
        steps = findViewById(R.id.permission_steps)
        continueButton = findViewById(R.id.compliance_continue)
        overrideButton = findViewById(R.id.compliance_override)

        val extras = intent.getParcelableExtra(
            DevicePolicyManager.EXTRA_PROVISIONING_ADMIN_EXTRAS_BUNDLE,
            PersistableBundle::class.java
        )
        config.seedFromProvisioning(extras)

        AgentLog.i(
            TAG,
            "policy compliance: server=${config.serverUrl} " +
                "deviceOwner=${MdmDeviceAdminReceiver.isDeviceOwner(this)}"
        )

        // Take what we are entitled to before asking for anything.
        grantWhatWeCan()

        continueButton.setOnClickListener { finishProvisioning() }
        overrideButton.setOnClickListener { confirmOverride() }
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
            AgentLog.w(TAG, "not device owner; runtime permissions cannot be pre-granted")
            return
        }
        // Note this respects R9: our own manifest declares MANAGE_EXTERNAL_STORAGE,
        // so the legacy storage permissions are deliberately skipped for us too.
        val failures = applier.grantRuntimePermissions(packageName)
        failures.forEach { AgentLog.w(TAG, "self-grant: $it") }
    }

    /**
     * ⚠️ **The continue button is blocked while a *required* permission is
     * missing** (operator, 2026-09-09: a device was provisioned without granting
     * everything, and nothing stopped it).
     *
     * Blocked on the required set only, not on everything. `PermissionRequirement`
     * already draws that line and the reasons hold here: background location and
     * notifications are genuinely optional, and the power menu is optional *by
     * design* on a device that will not be locked down. Blocking on those would
     * strand setup over something nobody needs.
     *
     * ⚠️ **There is still a way through, because there has to be.** Provisioning
     * cannot be repeated without another factory reset, so a required permission
     * that cannot be granted on some future OEM — a missing Settings screen, an
     * intent that resolves to nothing — must not trap the operator on this screen
     * with a dead button and no recourse. The override is secondary, plain, and
     * behind a dialog that names what will break.
     */
    private fun renderSteps() {
        steps.removeAllViews()
        val outstanding = PermissionRequirement.needingUserAction(this)
        val missingRequired = PermissionRequirement.outstanding(this)

        if (outstanding.isEmpty()) {
            status.setText(R.string.compliance_all_set)
            continueButton.setText(R.string.compliance_finish)
            continueButton.isEnabled = true
            overrideButton.visibility = View.GONE
            return
        }

        if (missingRequired.isEmpty()) {
            // Only optional ones left. Proceeding here is a legitimate choice, so
            // it stays a plain enabled button rather than something to argue with.
            status.setText(R.string.compliance_grant_intro)
            continueButton.setText(R.string.compliance_skip_rest)
            continueButton.isEnabled = true
            overrideButton.visibility = View.GONE
        } else {
            status.text = getString(R.string.compliance_required_intro, missingRequired.size)
            continueButton.setText(R.string.compliance_blocked)
            continueButton.isEnabled = false
            overrideButton.visibility = View.VISIBLE
        }

        for (requirement in PermissionRequirement.ALL) {
            if (requirement.grantIntent(this) == null) continue  // granted silently
            steps.addView(buildRow(requirement))
        }
    }

    /**
     * Ask for the master bypass code, and let the operator past only if the
     * server agrees (W117).
     *
     * ⚠️ **The code is checked by the server, never here.** It is six digits and
     * fixed for the life of an install, so anything shipped to the device —
     * the code itself, or a hash of it in the provisioning extras — would be
     * brute-forced the moment a QR was photographed or a tablet was read. What
     * this activity holds is the enrollment token, which is what authorizes the
     * question.
     *
     * ⚠️ **Three outcomes, deliberately distinguished.** "Wrong code" and "could
     * not reach the server" look identical if both are reported as failure, and
     * the operator can act on one and not the other. Anything but an explicit
     * `accepted` leaves the block in place.
     */
    private fun confirmOverride() {
        val missing = PermissionRequirement.outstanding(this)
        if (missing.isEmpty()) {
            finishProvisioning()
            return
        }

        val token = config.enrollmentToken
        val server = config.serverUrl
        if (token.isNullOrBlank() || server.isNullOrBlank()) {
            // Nothing to ask, and nobody to ask. Say so rather than showing a
            // code box that can never succeed.
            AlertDialog.Builder(this)
                .setTitle(R.string.compliance_override_title)
                .setMessage(R.string.compliance_override_no_server)
                .setPositiveButton(R.string.compliance_override_cancel, null)
                .show()
            return
        }

        val input = EditText(this).apply {
            inputType = InputType.TYPE_CLASS_NUMBER
            filters = arrayOf(InputFilter.LengthFilter(BYPASS_PIN_LENGTH))
            hint = getString(R.string.compliance_override_hint)
        }

        val dialog = AlertDialog.Builder(this)
            .setTitle(R.string.compliance_override_title)
            .setMessage(
                getString(R.string.compliance_override_body, missing.joinToString(", "))
            )
            .setView(input)
            .setPositiveButton(R.string.compliance_override_confirm, null)
            .setNegativeButton(R.string.compliance_override_cancel, null)
            .create()

        // The click listener is attached after show() so a wrong code can leave
        // the dialog open; the Builder's own listener always dismisses.
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                submitBypassPin(dialog, input, token, missing)
            }
        }
        dialog.show()
    }

    private fun submitBypassPin(
        dialog: AlertDialog,
        input: EditText,
        token: String,
        missing: List<String>,
    ) {
        val pin = input.text.toString().trim()
        if (pin.length != BYPASS_PIN_LENGTH) {
            input.error = getString(R.string.compliance_override_hint)
            return
        }

        val positive = dialog.getButton(AlertDialog.BUTTON_POSITIVE)
        positive.isEnabled = false
        status.setText(R.string.compliance_override_checking)

        lifecycleScope.launch {
            val answer = withContext(Dispatchers.IO) {
                ApiClient(config).checkBypassPin(token, pin)
            }
            positive.isEnabled = true

            when {
                answer == null -> {
                    // Could not ask. Not the same as being told no.
                    input.error = getString(R.string.compliance_override_unreachable)
                    renderSteps()
                }
                answer.accepted -> {
                    AgentLog.w(
                        TAG,
                        "bypass code accepted; continuing without: $missing"
                    )
                    dialog.dismiss()
                    finishProvisioning()
                }
                answer.attemptsRemaining <= 0 -> {
                    input.error = getString(R.string.compliance_override_locked)
                    renderSteps()
                }
                else -> {
                    AgentLog.w(TAG, "bypass code rejected by the server")
                    input.error = getString(
                        R.string.compliance_override_wrong, answer.attemptsRemaining
                    )
                    renderSteps()
                }
            }
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
                    .onFailure { AgentLog.e(TAG, "could not open grant screen", it) }
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
        overrideButton.visibility = View.GONE
        val missing = PermissionRequirement.outstanding(this)
        if (missing.isNotEmpty()) AgentLog.w(TAG, "continuing without: $missing")

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
                AgentLog.i(TAG, "enrolled: state=${it.stateVersion} errors=${it.errors}")
            }.onFailure {
                AgentLog.e(TAG, "enrollment failed; the agent will retry", it)
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

        /** Matches `bypass_pin.DIGITS` on the server. */
        private const val BYPASS_PIN_LENGTH = 6
    }
}
