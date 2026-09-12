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

import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.os.Handler
import android.os.HandlerThread
import android.os.PowerManager
import com.taksolutions.atlasmdm.diag.AgentLog

/**
 * Says whether a launcher is currently in front (W136).
 *
 * ⚠️ **Polling, because Android offers no callback for this.**
 * `UsageStatsManager` is the only public way to learn the foreground app and it
 * is query-only. The cost is one binder call a second, and only while the
 * screen is on and something has actually asked to be told — the watcher is
 * started by the device ID label and by nothing else.
 *
 * ⚠️ **"Home" is resolved, not hardcoded.** Any package with an activity
 * answering `ACTION_MAIN` + `CATEGORY_HOME` counts, which covers the stock
 * launcher, whatever OEM shell replaced it, and the ATLAS launcher — the
 * operator asked for "native or the atlas launcher" and this is the one rule
 * that is both.
 */
object HomeScreenWatcher {

    private const val TAG = "HomeScreenWatcher"

    /** How often to ask. Fast enough to feel immediate, slow enough to ignore. */
    private const val POLL_MS = 1_000L

    /** Ordinary query window: a little wider than the poll, to never skip an event. */
    private const val WINDOW_MS = 10_000L

    /**
     * The first query after starting looks back much further.
     *
     * A tablet already sitting on its home screen has produced no recent event,
     * so a short first window finds nothing and the label would not appear until
     * the user touched something. Events are kept "for a few days", so one wide
     * query costs one iteration and settles it.
     */
    private const val SEED_MS = 24L * 60 * 60 * 1000

    private var thread: HandlerThread? = null
    private var handler: Handler? = null
    private var listener: ((Boolean) -> Unit)? = null
    private var receiver: BroadcastReceiver? = null
    private var homePackages: Set<String> = emptySet()
    private var interactive = true
    private var seeded = false
    private var appContext: Context? = null

    /** The last verdict, for a caller that needs to render before the first poll. */
    @Volatile
    var onHome: Boolean = false
        private set

    private val poll = object : Runnable {
        override fun run() {
            val context = appContext ?: return
            if (!interactive) return  // ACTION_SCREEN_ON restarts the loop
            val foreground = foregroundPackage(context)
            val next = DeviceIdLabelPlan.onHome(foreground, homePackages, onHome)
            if (next != onHome) {
                onHome = next
                listener?.invoke(next)
            }
            handler?.postDelayed(this, POLL_MS)
        }
    }

    /**
     * Begin watching, and call [onChange] whenever the answer changes.
     *
     * Idempotent: the reconcile calls this every couple of minutes, and a second
     * call must not start a second thread or a second poll loop.
     */
    @Synchronized
    fun start(context: Context, onChange: (Boolean) -> Unit) {
        val app = context.applicationContext
        appContext = app
        listener = onChange
        if (handler != null) return

        homePackages = homePackages(app)
        val t = HandlerThread("atlas-home-watch").also { it.start() }
        thread = t
        handler = Handler(t.looper)

        val screen = object : BroadcastReceiver() {
            override fun onReceive(c: Context, intent: Intent) {
                if (intent.action == Intent.ACTION_SCREEN_OFF) {
                    interactive = false
                    return
                }
                interactive = true
                // A launcher can be installed or replaced while the agent runs,
                // and once per unlock is cheap enough to keep that honest.
                homePackages = homePackages(app)
                restart()
            }
        }
        app.registerReceiver(
            screen,
            IntentFilter().apply {
                addAction(Intent.ACTION_SCREEN_ON)
                addAction(Intent.ACTION_SCREEN_OFF)
                addAction(Intent.ACTION_USER_PRESENT)
            },
            Context.RECEIVER_NOT_EXPORTED,
        )
        receiver = screen

        interactive = app.getSystemService(PowerManager::class.java)?.isInteractive ?: true
        AgentLog.i(TAG, "watching for the home screen; launchers: $homePackages")
        restart()
    }

    /** Stop watching and let the thread go. Safe to call when not running. */
    @Synchronized
    fun stop(context: Context) {
        receiver?.let { runCatching { context.applicationContext.unregisterReceiver(it) } }
        receiver = null
        handler?.removeCallbacks(poll)
        thread?.quitSafely()
        thread = null
        handler = null
        listener = null
        appContext = null
        onHome = false
        seeded = false
    }

    private fun restart() {
        handler?.removeCallbacks(poll)
        handler?.post(poll)
    }

    /**
     * The package whose activity resumed most recently, or null for "no answer".
     *
     * ⚠️ Null is returned for *both* "the query failed" and "nothing resumed in
     * the window", and [DeviceIdLabelPlan.onHome] treats them the same way on
     * purpose: hold the current answer. An untouched device produces no events.
     */
    private fun foregroundPackage(context: Context): String? {
        val usage = context.getSystemService(UsageStatsManager::class.java) ?: return null
        val now = System.currentTimeMillis()
        val begin = if (seeded) now - WINDOW_MS else now - SEED_MS
        // Returns null before the user's first unlock (Android R+), and throws
        // SecurityException when usage access is not granted — the caller is
        // expected to have checked, but a revoked app-op must not crash the
        // poll thread.
        val events = runCatching { usage.queryEvents(begin, now) }
            .onFailure { AgentLog.w(TAG, "usage events unavailable: ${it.message}") }
            .getOrNull() ?: return null
        seeded = true

        val event = UsageEvents.Event()
        var last: String? = null
        while (events.getNextEvent(event)) {
            if (event.eventType == UsageEvents.Event.ACTIVITY_RESUMED) {
                last = event.packageName
            }
        }
        return last
    }

    private fun homePackages(context: Context): Set<String> {
        val intent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME)
        return runCatching {
            context.packageManager
                .queryIntentActivities(intent, PackageManager.MATCH_ALL)
                .mapTo(mutableSetOf()) { it.activityInfo.packageName }
        }.getOrDefault(emptySet())
    }
}
