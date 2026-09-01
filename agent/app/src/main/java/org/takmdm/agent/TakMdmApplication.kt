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

package org.takmdm.agent

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import java.io.File
import org.takmdm.agent.core.AgentConfig
import org.takmdm.agent.diag.AgentLog
import org.takmdm.agent.diag.Redactor
import org.takmdm.agent.diag.RingFileLogSink
import org.takmdm.agent.sync.Reconciler
import org.takmdm.agent.sync.SyncScheduler

class TakMdmApplication : Application() {

    override fun onCreate() {
        super.onCreate()

        // First, so that everything after it is recorded. The log is what an
        // operator collects from a device they cannot plug a cable into.
        AgentLog.install(RingFileLogSink(File(filesDir, "diag")))

        // Registered before any code can log it. The enrollment token is the one
        // live secret the agent holds in a form that could reach a log line, and
        // these logs now leave the device.
        Redactor.protect(AgentConfig(this).enrollmentToken)

        AgentLog.i(TAG, "agent starting (v${Reconciler.AGENT_VERSION})")

        val channel = NotificationChannel(
            SyncScheduler.NOTIFICATION_CHANNEL,
            getString(R.string.sync_channel_name),
            // Low: the agent should be visible, as a foreground service must be, but
            // it has nothing to interrupt anyone about.
            NotificationManager.IMPORTANCE_LOW
        )
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)

        SyncScheduler.schedulePeriodic(this)
    }

    private companion object {
        const val TAG = "Application"
    }
}
