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

/**
 * What the agent is doing to the device's apps, while it is doing it (W75).
 *
 * ⚠️ **It replaces the service's notice rather than adding a second one** (W87).
 * A second notification from the same app collapses the One UI status bar to one
 * entry showing the **app's launcher icon** — the full-colour logo with its
 * wordmark — so the download arrow appeared for an instant and was then replaced.
 * With one notification there is nothing to collapse.
 *
 * The worry that drove the original split — a progress bar stuck on screen at
 * 100% forever — is [clear]'s job: it puts the resting notice back.
 */
object InstallNotifier {

    /** The foreground service's own id: this replaces that notification. */
    private const val NOTIFICATION_ID = AgentNotification.ID

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

        post(context, AgentNotification.downloading(context, label, percent, total <= 0))
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
        post(context, AgentNotification.installing(context, label))
    }

    /** Back to the resting state — see [AgentNotification.rest]. */
    fun clear(context: Context) {
        lastPercent = -1
        lastPostedAt = 0L
        AgentNotification.rest(context)
    }

    private fun post(context: Context, notification: Notification) {
        val notifications = context.getSystemService(NotificationManager::class.java) ?: return
        runCatching { notifications.notify(NOTIFICATION_ID, notification) }
    }
}
