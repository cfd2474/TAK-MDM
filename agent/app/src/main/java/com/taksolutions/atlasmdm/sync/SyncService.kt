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

package com.taksolutions.atlasmdm.sync

import android.Manifest
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.os.IBinder
import androidx.core.content.ContextCompat
import com.taksolutions.atlasmdm.diag.AgentLog
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import com.taksolutions.atlasmdm.core.AgentConfig
import com.taksolutions.atlasmdm.policy.LocationTracker
import com.taksolutions.atlasmdm.ui.AgentNotification

/**
 * Foreground service holding the long-poll doorbell.
 *
 * The loop is: sync, then park on `/device/wait` until the server releases it or
 * the hold expires. That gives near-immediate propagation (F3) without a persistent
 * broker or any Google dependency.
 *
 * The periodic [SyncWorker] runs regardless. This service is an accelerator; the
 * worker is the guarantee. If the process is killed, policy still converges — just
 * more slowly.
 */
class SyncService : Service() {

    private val job = SupervisorJob()
    private val scope = CoroutineScope(Dispatchers.IO + job)
    private var loop: Job? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForeground(NOTIFICATION_ID, AgentNotification.idle(this), foregroundTypes())
        // ⚠️ Tells InstallNotifier that resting on this id is safe. Without a
        // foreground service holding it, an ongoing notification cannot be
        // dismissed by anyone.
        AgentNotification.serviceIsForeground = true
        if (loop?.isActive != true) loop = scope.launch { runLoop() }
        // STICKY: on a managed device this should come back after a process kill.
        return START_STICKY
    }

    /**
     * The foreground service types this service may legally claim *right now*.
     *
     * ⚠️ **Computed, never constant.** Android throws `SecurityException` when a
     * declared type's runtime prerequisites are unmet, and the documentation is
     * explicit that this "might cause a running foreground service to be removed
     * from the foreground process state, and might cause your app to crash". This
     * is the service that manages the device: claiming `location` before the
     * Device Owner has self-granted the permission would take the whole agent down
     * at boot, on every device, to add a feature most fleets will not enable.
     *
     * So `specialUse` is unconditional and `location` is added only once a fix is
     * actually permitted. `startForeground` is called again when that changes.
     */
    private fun foregroundTypes(): Int {
        var types = ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE
        val granted = ContextCompat.checkSelfPermission(
            this, Manifest.permission.ACCESS_FINE_LOCATION
        ) == PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(
                this, Manifest.permission.ACCESS_COARSE_LOCATION
            ) == PackageManager.PERMISSION_GRANTED
        if (granted) types = types or ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION
        return types
    }

    private suspend fun runLoop() {
        val reconciler = Reconciler(applicationContext)
        val config = AgentConfig(applicationContext)
        val locations = LocationTracker(applicationContext)
        var backoffSeconds = 5L
        var claimedLocationType = false

        while (scope.isActive) {
            // ⚠️ Sampling lives here rather than inside `sync()`, and that is the
            // point of it: a device with no network still records its track. Put
            // in the reconcile, an offline tablet would buffer nothing and come
            // back from an outage with a gap exactly where the track mattered.
            runCatching { locations.sampleIfDue() }
                .onFailure { AgentLog.w(TAG, "location sample failed: ${it.message}") }

            // The permission usually arrives after this service has already
            // started - the Device Owner self-grants on the first reconcile - so
            // the claim is upgraded once rather than assumed at startup.
            if (!claimedLocationType && locations.isEnabled()) {
                val types = foregroundTypes()
                if (types and ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION != 0) {
                    runCatching {
                        startForeground(NOTIFICATION_ID, AgentNotification.idle(this), types)
                        claimedLocationType = true
                        AgentLog.i(TAG, "foreground service now claims the location type")
                    }.onFailure {
                        // Never fatal: losing the type costs tracking, throwing
                        // here would cost the device its management.
                        AgentLog.w(TAG, "could not claim location FGS type: ${it.message}")
                    }
                }
            }

            val ok = runCatching {
                val outcome = reconciler.sync()
                AgentLog.i(
                    TAG,
                    "sync: state=${outcome.stateVersion} applied=${outcome.appliedStateVersion} " +
                        "errors=${outcome.errors.size}"
                )
                outcome.errors.forEach { AgentLog.w(TAG, "  $it") }
                true
            }.getOrElse {
                AgentLog.e(TAG, "sync failed", it)
                false
            }

            if (!ok) {
                // Exponential backoff so an unreachable server does not become a
                // battery drain or a request flood when it returns.
                delay(backoffSeconds * 1000)
                backoffSeconds = (backoffSeconds * 2).coerceAtMost(MAX_BACKOFF_SECONDS)
                continue
            }
            backoffSeconds = 5L

            if (!config.isEnrolled) {
                delay(30_000)
                continue
            }

            // Parks server-side; returns early only when something actually changed.
            reconciler.waitForChange(WAIT_SECONDS)
        }
    }

    override fun onDestroy() {
        AgentNotification.serviceIsForeground = false
        scope.cancel()
        super.onDestroy()
    }

    companion object {
        private const val TAG = "SyncService"
        // ⚠️ The only id the agent posts to. A second notification from this
        // app collapses the One UI status bar onto the launcher icon, which
        // is how the download arrow got replaced by the ATLAS wordmark.
        private val NOTIFICATION_ID = AgentNotification.ID
        private const val WAIT_SECONDS = 120L
        private const val MAX_BACKOFF_SECONDS = 300L

        fun start(context: Context) {
            val intent = Intent(context, SyncService::class.java)
            context.startForegroundService(intent)
        }
    }
}
