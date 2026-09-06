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

package com.taksolutions.atlaslauncher

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.ActivityInfo
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.text.Editable
import android.text.TextWatcher
import android.util.Log
import android.view.View
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.GridLayoutManager
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import java.time.Instant
import java.time.ZoneId

/**
 * The ATLAS kiosk home screen (W68).
 *
 * ⚠️ **This activity must never fail to draw something.** It is the home screen:
 * if it crashes, the device has nowhere to go, and on a wall-mounted tablet that
 * means physical recovery. So config is salvaged rather than validated, a missing
 * app is skipped rather than drawn, and every launch is guarded — the user should
 * see a message, never an empty screen or a dialog they cannot dismiss.
 *
 * ⚠️ **Night mode is not here.** It lives in the agent, which already holds
 * `SYSTEM_ALERT_WINDOW` and can therefore tint ATAK and everything else — which is
 * the entire point of night mode on a TAK device. A tint drawn by this activity
 * would stop at its own edges and vanish the moment a user opened the app they
 * are trying to read by.
 */
class HomeActivity : AppCompatActivity() {

    private lateinit var grid: RecyclerView
    private lateinit var dock: RecyclerView
    private lateinit var empty: LinearLayout
    private lateinit var clock: TextView
    private lateinit var search: EditText
    private lateinit var gridAdapter: AppAdapter
    private lateinit var dockAdapter: AppAdapter

    private val catalog by lazy { AppCatalog(this) }
    private val ticker = Handler(Looper.getMainLooper())

    /** Everything policy permits, before the search box narrows it. */
    private var all: List<AppEntry> = emptyList()
    private var config: LauncherConfig = LauncherConfig()

    /**
     * Managed configuration can change while the launcher is running — the agent
     * pushes it on a two-minute cycle — and the platform says so with a broadcast.
     * Without this the grid would be whatever it was at the last cold start, and
     * an operator's change would appear to have done nothing.
     */
    private val configChanged = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) = reload()
    }

    private val tick = object : Runnable {
        override fun run() {
            clock.text = Clock.format(Instant.now(), config.clockZulu, ZoneId.systemDefault())
            ticker.postDelayed(this, 1_000L)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_home)

        grid = findViewById(R.id.grid)
        dock = findViewById(R.id.dock)
        empty = findViewById(R.id.empty)
        clock = findViewById(R.id.clock)
        search = findViewById(R.id.search)

        gridAdapter = AppAdapter(emptyList(), ::open)
        dockAdapter = AppAdapter(emptyList(), ::open)
        grid.adapter = gridAdapter
        dock.adapter = dockAdapter
        dock.layoutManager = LinearLayoutManager(this, RecyclerView.HORIZONTAL, false)

        search.addTextChangedListener(object : TextWatcher {
            override fun afterTextChanged(s: Editable?) = showMatching()
            override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) = Unit
            override fun onTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) = Unit
        })

        registerReceiver(
            configChanged,
            IntentFilter(Intent.ACTION_APPLICATION_RESTRICTIONS_CHANGED),
            RECEIVER_NOT_EXPORTED,
        )
        reload()
    }

    override fun onResume() {
        super.onResume()
        // Policy may have changed while another app was in front, and the grid
        // must not still be showing an app that has since been removed.
        reload()
        if (config.showClock) ticker.post(tick)
    }

    override fun onPause() {
        // A clock nobody can see does not need to tick. It is one wake-up a
        // second on a device that is often on mains but not always.
        ticker.removeCallbacks(tick)
        super.onPause()
    }

    override fun onDestroy() {
        ticker.removeCallbacks(tick)
        runCatching { unregisterReceiver(configChanged) }
        super.onDestroy()
    }

    /**
     * ⚠️ Back does nothing on purpose. On a home screen there is nowhere behind,
     * and the default would finish the activity — leaving the kiosk looking at
     * whatever the system draws when no home app is showing.
     */
    @Deprecated("Deprecated in Java")
    override fun onBackPressed() = Unit

    private fun reload() {
        config = BundleSource.read(this)
        all = catalog.resolve(config.apps)

        applyOrientation(config.orientation)

        grid.layoutManager = GridLayoutManager(this, config.columns)
        dockAdapter.submit(catalog.resolve(config.favorites))
        dock.visibility = if (config.favorites.isEmpty()) View.GONE else View.VISIBLE

        // Hidden when there is nothing to search *or* nothing worth searching: a
        // filter box above four tiles is furniture.
        search.visibility =
            if (config.showSearch && all.size > SEARCH_WORTH_IT) View.VISIBLE else View.GONE
        if (search.visibility == View.GONE) search.setText("")

        clock.visibility = if (config.showClock) View.VISIBLE else View.GONE
        ticker.removeCallbacks(tick)
        if (config.showClock) ticker.post(tick)

        showMatching()
    }

    private fun showMatching() {
        val shown = Filtering.matching(all, search.text?.toString())
        gridAdapter.submit(shown)

        // Two different empty states, because they mean different things. Nothing
        // configured is a device waiting for policy; nothing matching is a search
        // that found nothing, and hiding the box would trap the user with it.
        val nothingConfigured = all.isEmpty()
        empty.visibility = if (nothingConfigured) View.VISIBLE else View.GONE
        grid.visibility = if (nothingConfigured) View.GONE else View.VISIBLE
    }

    /**
     * ⚠️ Two mechanisms, because one is not enough and the other is not always
     * available.
     *
     * `setRequestedOrientation` always works and pins **this activity**. It does
     * nothing for the kiosk app the user spends their time in, so on its own a
     * "landscape" kiosk would rotate the moment ATAK opened.
     *
     * The system rotation settings pin every app, and need `WRITE_SETTINGS` —
     * a special permission a **person** grants through Settings. No Device Owner
     * can grant it: `setPermissionGrantState` does not reach app-ops. So it is
     * attempted and its absence is logged rather than treated as a failure; the
     * launcher is still pinned, which is the visible half.
     */
    private fun applyOrientation(orientation: LauncherConfig.Orientation) {
        requestedOrientation = when (orientation) {
            LauncherConfig.Orientation.AUTO -> ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
            LauncherConfig.Orientation.PORTRAIT -> ActivityInfo.SCREEN_ORIENTATION_PORTRAIT
            LauncherConfig.Orientation.LANDSCAPE -> ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE
        }

        if (!Settings.System.canWrite(this)) {
            if (orientation != LauncherConfig.Orientation.AUTO) {
                Log.i(TAG, "orientation: no WRITE_SETTINGS, so only the launcher is pinned")
            }
            return
        }
        runCatching {
            val auto = orientation == LauncherConfig.Orientation.AUTO
            Settings.System.putInt(
                contentResolver, Settings.System.ACCELEROMETER_ROTATION, if (auto) 1 else 0,
            )
            if (!auto) {
                Settings.System.putInt(
                    contentResolver,
                    Settings.System.USER_ROTATION,
                    if (orientation == LauncherConfig.Orientation.PORTRAIT) ROTATION_0
                    else ROTATION_90,
                )
            }
        }.onFailure { Log.w(TAG, "could not pin the system rotation: ${it.message}") }
    }

    private fun open(entry: AppEntry) {
        val intent = Intent(entry.intent).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        runCatching { startActivity(intent) }.onFailure {
            // A tile whose app has just been removed, or one lock task refuses.
            // Said out loud: silence here is indistinguishable from a frozen
            // device, which is what a user reports instead of the real fault.
            Log.w(TAG, "could not open ${entry.ref.packageName}: ${it.message}")
            Toast.makeText(this, R.string.cannot_open, Toast.LENGTH_SHORT).show()
        }
    }

    private companion object {
        const val TAG = "AtlasLauncher"

        /** Below this many tiles, everything is on screen and search is clutter. */
        const val SEARCH_WORTH_IT = 8

        const val ROTATION_0 = 0
        const val ROTATION_90 = 1
    }
}
