package org.takmdm.agent

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import org.takmdm.agent.sync.SyncScheduler

class TakMdmApplication : Application() {

    override fun onCreate() {
        super.onCreate()

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
}
