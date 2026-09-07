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
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import com.taksolutions.atlasmdm.R
import com.taksolutions.atlasmdm.sync.SyncScheduler

/**
 * The agent's one notification, in whichever state it is currently in (W85).
 *
 * ⚠️ **One notification, not two, and that is the whole point of this file.**
 * The agent used to post a second one for downloads. On One UI a second
 * notification from the same app collapses the status bar to a single entry
 * showing the **app's launcher icon** — the full-colour ATLAS logo with its
 * wordmark — so the download arrow appeared for an instant and was then replaced
 * by a picture that says nothing at 24dp.
 *
 * With one notification there is nothing to collapse: the icon in the bar is
 * always the one this file chose.
 *
 * ⚠️ **Always [ID].** It is the foreground service's notification, so cancelling
 * it would take the service out of the foreground. Finishing a download posts
 * [idle] over it rather than cancelling.
 */
object AgentNotification {

    /** The foreground service's id. Everything here replaces that notification. */
    const val ID = 1001

    /**
     * Whether [com.taksolutions.atlasmdm.sync.SyncService] is currently holding
     * [ID] in the foreground. Set by the service at both ends of its life.
     *
     * ⚠️ [rest] needs this. The resting notice is `ongoing`, which makes it
     * undismissable — fine while a foreground service owns it, since the service
     * takes it away when it stops, but a stranded one could not be swiped off. A
     * download driven by `SyncWorker` alone therefore ends in a cancel, not a
     * rest.
     */
    @Volatile
    @JvmField
    var serviceIsForeground = false

    /** Nothing happening: the agent is alive and watching. */
    fun idle(context: Context): Notification =
        base(context)
            .setContentTitle(context.getString(R.string.sync_notification_title))
            .setContentText(context.getString(R.string.sync_notification_text))
            // ⚠️ The ATLAS mark, not a download arrow. This notice is permanent,
            // and a download glyph on a permanent notification reads as a
            // transfer that never finishes.
            .setSmallIcon(R.drawable.ic_stat_atlas)
            .build()

    /** Fetching [label], [percent] of the way there. */
    fun downloading(context: Context, label: String, percent: Int, indeterminate: Boolean) =
        base(context)
            .setContentTitle(context.getString(R.string.notify_downloading, label))
            .setContentText(context.getString(R.string.notify_percent, percent))
            .setSmallIcon(R.drawable.ic_stat_download)
            .setProgress(100, percent.coerceIn(0, 100), indeterminate)
            .build()

    /**
     * Installing [label].
     *
     * Indeterminate on purpose: `PackageInstaller` reports a session progress
     * that jumps to near-complete immediately and then sits there, so a bar
     * driven by it looks stuck at 90% for the part that actually takes time.
     */
    fun installing(context: Context, label: String): Notification =
        base(context)
            .setContentTitle(context.getString(R.string.notify_installing, label))
            .setSmallIcon(R.drawable.ic_stat_download)
            .setProgress(100, 0, true)
            .build()

    /**
     * Work is over: put the resting notice back, or take the notification away.
     *
     * ⚠️ **Not a plain cancel.** [ID] is the foreground service's notification,
     * and cancelling it while the service holds it would drop the service out of
     * the foreground — which Android then kills. When the service is not holding
     * it ([serviceIsForeground] false, i.e. a `SyncWorker`-only download) there is
     * nothing to keep alive, and cancelling is right: an ongoing notice with no
     * service behind it cannot be dismissed by hand.
     */
    fun rest(context: Context) {
        val notifications = context.getSystemService(NotificationManager::class.java) ?: return
        runCatching {
            if (serviceIsForeground) notifications.notify(ID, idle(context))
            else notifications.cancel(ID)
        }
    }

    private fun base(context: Context): Notification.Builder {
        val open = PendingIntent.getActivity(
            context,
            0,
            Intent(context, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE,
        )
        return Notification.Builder(context, SyncScheduler.NOTIFICATION_CHANNEL)
            .setContentIntent(open)
            // Ongoing throughout: this is the foreground service's notification,
            // and a user who swiped it away would take the service's foreground
            // status with it.
            .setOngoing(true)
            .setOnlyAlertOnce(true)
    }
}
