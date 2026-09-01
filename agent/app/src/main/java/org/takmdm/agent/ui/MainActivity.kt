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

package org.takmdm.agent.ui

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.Environment
import android.provider.Settings
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.takmdm.agent.R
import org.takmdm.agent.admin.MdmDeviceAdminReceiver
import org.takmdm.agent.admin.PolicyComplianceActivity
import org.takmdm.agent.core.AgentConfig
import org.takmdm.agent.permissions.PermissionRequirement
import org.takmdm.agent.sync.Reconciler
import org.takmdm.agent.sync.SyncScheduler

/**
 * Status screen.
 *
 * Deliberately not a launcher and not a kiosk shell — the agent stays out of the
 * way unless a policy asks for lockdown (F6). Its one interactive job is the
 * all-files-access grant, which Android does not permit a Device Owner to give
 * itself.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var config: AgentConfig
    private lateinit var status: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        config = AgentConfig(this)
        status = findViewById(R.id.status)

        findViewById<Button>(R.id.sync_now).setOnClickListener { syncNow() }
        findViewById<Button>(R.id.open_marketplace).setOnClickListener {
            startActivity(Intent(this, MarketplaceActivity::class.java))
        }
        findViewById<Button>(R.id.grant_storage).setOnClickListener {
            // Reuses the provisioning wizard: permissions can be revoked long after
            // setup, and there should be one place that knows how to restore them.
            startActivity(Intent(this, PolicyComplianceActivity::class.java))
        }

        SyncScheduler.startAll(this)
    }

    override fun onResume() {
        super.onResume()
        render()
    }

    private fun render() {
        val enrolled = config.isEnrolled
        val storageOk = Environment.isExternalStorageManager()

        status.text = buildString {
            appendLine(if (enrolled) getString(R.string.status_enrolled) else getString(R.string.status_not_enrolled))
            appendLine("Device owner: ${MdmDeviceAdminReceiver.isDeviceOwner(this@MainActivity)}")
            appendLine("Server: ${config.serverUrl ?: "not configured"}")
            appendLine("Device id: ${config.deviceId ?: "-"}")
            appendLine("State version: ${config.stateVersion} (applied ${config.appliedStateVersion})")
            appendLine("All-files access: $storageOk")
            val missing = PermissionRequirement.outstanding(this@MainActivity)
            appendLine("Missing permissions: ${if (missing.isEmpty()) "none" else missing.joinToString()}")
            appendLine("Last sync: " + if (config.lastSyncAt == 0L) "never" else
                java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss", java.util.Locale.US)
                    .format(java.util.Date(config.lastSyncAt)))
            appendLine()
            // The whole point of this screen when a device will not enrol: the
            // reason, readable without USB debugging.
            appendLine("Last error:")
            appendLine(config.lastError ?: "none")
        }

        findViewById<Button>(R.id.grant_storage).isEnabled =
            PermissionRequirement.outstanding(this).isNotEmpty()
    }

    private fun syncNow() {
        lifecycleScope.launch {
            val outcome = withContext(Dispatchers.IO) {
                runCatching { Reconciler(applicationContext).sync() }
            }
            outcome.onSuccess { result ->
                val message = if (result.errors.isEmpty()) {
                    "Synced. State ${result.stateVersion}."
                } else {
                    "Synced with ${result.errors.size} problem(s): ${result.errors.first()}"
                }
                Toast.makeText(this@MainActivity, message, Toast.LENGTH_LONG).show()
                render()
            }.onFailure {
                Toast.makeText(this@MainActivity, "Sync failed: ${it.message}", Toast.LENGTH_LONG)
                    .show()
            }
        }
    }

    private fun requestAllFilesAccess() {
        // A Device Owner cannot grant this to itself: it is an app-op, not a runtime
        // permission. One tap here is the supported route on stock Android (R1).
        startActivity(
            Intent(
                Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
                Uri.parse("package:$packageName")
            )
        )
    }
}
