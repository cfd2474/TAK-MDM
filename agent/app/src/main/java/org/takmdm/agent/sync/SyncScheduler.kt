package org.takmdm.agent.sync

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import java.util.concurrent.TimeUnit

object SyncScheduler {

    const val NOTIFICATION_CHANNEL = "takmdm_sync"
    private const val PERIODIC_WORK = "takmdm-periodic-sync"
    private const val TAG = "SyncScheduler"

    /**
     * The correctness floor.
     *
     * 15 minutes is WorkManager's minimum period, so anything lower is wishful. The
     * long-poll service makes propagation immediate in practice, but this is what
     * guarantees a device converges even if the service is killed, the doorbell is
     * missed, or the device was offline when a change landed (D7).
     */
    fun schedulePeriodic(context: Context) {
        val request = PeriodicWorkRequestBuilder<SyncWorker>(15, TimeUnit.MINUTES)
            .setConstraints(
                Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()
            )
            .build()

        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            PERIODIC_WORK,
            ExistingPeriodicWorkPolicy.KEEP,
            request
        )
    }

    fun startAll(context: Context) {
        schedulePeriodic(context)
        runCatching { SyncService.start(context) }
            .onFailure { Log.w(TAG, "could not start sync service", it) }
    }
}

class SyncWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        return runCatching {
            val outcome = Reconciler(applicationContext).sync()
            Log.i("SyncWorker", "periodic sync: state=${outcome.stateVersion}")
            Result.success()
        }.getOrElse {
            Log.e("SyncWorker", "periodic sync failed", it)
            Result.retry()
        }
    }
}

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED) {
            SyncScheduler.startAll(context)
        }
    }
}
