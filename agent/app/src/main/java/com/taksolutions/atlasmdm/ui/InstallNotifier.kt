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

package com.taksolutions.atlasmdm.ui

import android.app.Notification
import android.app.NotificationManager
import android.content.Context
import android.os.SystemClock
import com.taksolutions.atlasmdm.R
import com.taksolutions.atlasmdm.sync.SyncScheduler

/**
 * What the agent is doing to the device's apps, while it is doing it (W75).
 *
 * ⚠️ **Separate from the ongoing service notice.** That one says the agent is
 * alive; this one says work is happening and will go away when it stops. Folding
 * them together would leave a progress bar on screen permanently at 100%, or a
 * device that looks busy when it is idle.
 *
 * ⚠️ **The download symbol here, the ATLAS mark there.** The operator's point was
 * that a permanent notice showing a download arrow reads as a stuck download.
 * This notification *is* a download, so the arrow is right — and the two being
 * different is what makes them tellable apart in the status bar.
 */
object InstallNotifier {

    /** Distinct from the foreground service's, or one would replace the other. */
    private const val NOTIFICATION_ID = 1002

    /**
     * ⚠️ Android drops notification updates posted more often than about five a
     * second, and a fast local download can call back far quicker than that. The
     * throttle is what stops a progress bar that jumps and stalls rather than
     * moving — and it costs nothing, since a person cannot read faster either.
     */
    private const val MIN_UPDATE_MILLIS = 250L

    private var lastPostedAt = 0L
    private var lastPercent = -1

    /** Downloading [label], [done] of [total] bytes. */
    fun downloading(context: Context, label: String, done: Long, total: Long) {
        val percent = if (total > 0) ((done * 100) / total).toInt().coerceIn(0, 100) else 0
        val now = SystemClock.elapsedRealtime()
        // Always let the last percent through, so a download does not finish
        // showing 97% and then vanish.
        if (percent != 100 && percent == lastPercent) return
        if (percent != 100 && now - lastPostedAt < MIN_UPDATE_MILLIS) return
        lastPostedAt = now
        lastPercent = percent

        post(
            context,
            title = context.getString(R.string.notify_downloading, label),
            text = context.getString(R.string.notify_percent, percent),
            progress = percent,
            indeterminate = total <= 0,
        )
    }

    /**
     * Installing [label].
     *
     * Indeterminate on purpose: `PackageInstaller` reports a session progress
     * that jumps to near-complete immediately and then sits there, so a bar
     * driven by it looks stuck at 90% for the part that actually takes time.
     */
    fun installing(context: Context, label: String) {
        lastPercent = -1
        post(
            context,
            title = context.getString(R.string.notify_installing, label),
            text = null,
            progress = 0,
            indeterminate = true,
        )
    }

    /** Take it away. Safe to call when nothing was ever shown. */
    fun clear(context: Context) {
        lastPercent = -1
        lastPostedAt = 0L
        runCatching {
            context.getSystemService(NotificationManager::class.java)?.cancel(NOTIFICATION_ID)
        }
    }

    private fun post(
        context: Context,
        title: String,
        text: String?,
        progress: Int,
        indeterminate: Boolean,
    ) {
        val notifications = context.getSystemService(NotificationManager::class.java) ?: return
        val builder = Notification.Builder(context, SyncScheduler.NOTIFICATION_CHANNEL)
            .setContentTitle(title)
            .setSmallIcon(android.R.drawable.stat_sys_download)
            .setProgress(100, progress, indeterminate)
            // Ongoing while it runs: this is work in progress, not an alert, and
            // a user swiping it away mid-install would be told nothing when it
            // finished or failed.
            .setOngoing(true)
            .setOnlyAlertOnce(true)
        text?.let { builder.setContentText(it) }
        runCatching { notifications.notify(NOTIFICATION_ID, builder.build()) }
    }
}
