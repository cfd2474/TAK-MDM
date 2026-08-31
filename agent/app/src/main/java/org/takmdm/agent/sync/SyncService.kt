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

package org.takmdm.agent.sync

import android.app.Notification
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.IBinder
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.takmdm.agent.R
import org.takmdm.agent.core.AgentConfig
import org.takmdm.agent.ui.MainActivity

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
        startForeground(
            NOTIFICATION_ID,
            buildNotification(),
            ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE
        )
        if (loop?.isActive != true) loop = scope.launch { runLoop() }
        // STICKY: on a managed device this should come back after a process kill.
        return START_STICKY
    }

    private suspend fun runLoop() {
        val reconciler = Reconciler(applicationContext)
        val config = AgentConfig(applicationContext)
        var backoffSeconds = 5L

        while (scope.isActive) {
            val ok = runCatching {
                val outcome = reconciler.sync()
                Log.i(
                    TAG,
                    "sync: state=${outcome.stateVersion} applied=${outcome.appliedStateVersion} " +
                        "errors=${outcome.errors.size}"
                )
                outcome.errors.forEach { Log.w(TAG, "  $it") }
                true
            }.getOrElse {
                Log.e(TAG, "sync failed", it)
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

    private fun buildNotification(): Notification {
        val open = android.app.PendingIntent.getActivity(
            this, 0,
            Intent(this, MainActivity::class.java),
            android.app.PendingIntent.FLAG_IMMUTABLE
        )
        return Notification.Builder(this, SyncScheduler.NOTIFICATION_CHANNEL)
            .setContentTitle(getString(R.string.sync_notification_title))
            .setContentText(getString(R.string.sync_notification_text))
            .setSmallIcon(android.R.drawable.stat_sys_download_done)
            .setContentIntent(open)
            .setOngoing(true)
            .build()
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }

    companion object {
        private const val TAG = "SyncService"
        private const val NOTIFICATION_ID = 1001
        private const val WAIT_SECONDS = 120L
        private const val MAX_BACKOFF_SECONDS = 300L

        fun start(context: Context) {
            val intent = Intent(context, SyncService::class.java)
            context.startForegroundService(intent)
        }
    }
}
