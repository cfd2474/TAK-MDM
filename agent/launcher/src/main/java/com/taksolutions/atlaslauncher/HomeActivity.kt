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
import android.os.Bundle
import android.util.Log
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.GridLayoutManager
import androidx.recyclerview.widget.RecyclerView

/**
 * The ATLAS kiosk home screen (W68, Chunk 1).
 *
 * ⚠️ **This activity must never fail to draw something.** It is the home screen:
 * if it crashes, the device has nowhere to go, and on a wall-mounted tablet that
 * means physical recovery. So config is salvaged rather than validated, a missing
 * app is skipped rather than drawn, and every launch is guarded — the user should
 * see a message, never an empty screen or a dialog they cannot dismiss.
 */
class HomeActivity : AppCompatActivity() {

    private lateinit var grid: RecyclerView
    private lateinit var empty: LinearLayout
    private lateinit var clock: TextView
    private lateinit var adapter: AppAdapter

    private val catalog by lazy { AppCatalog(this) }

    /**
     * Managed configuration can change while the launcher is running — the agent
     * pushes it on a two-minute cycle — and the platform says so with a broadcast.
     * Without this the grid would be whatever it was at the last cold start, and
     * an operator's change would appear to have done nothing.
     */
    private val configChanged = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) = render()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_home)

        grid = findViewById(R.id.grid)
        empty = findViewById(R.id.empty)
        clock = findViewById(R.id.clock)

        adapter = AppAdapter(emptyList(), ::open)
        grid.adapter = adapter

        registerReceiver(
            configChanged,
            IntentFilter(Intent.ACTION_APPLICATION_RESTRICTIONS_CHANGED),
            RECEIVER_NOT_EXPORTED,
        )
        render()
    }

    /** Policy may have changed while another app was in front. */
    override fun onResume() {
        super.onResume()
        render()
    }

    override fun onDestroy() {
        runCatching { unregisterReceiver(configChanged) }
        super.onDestroy()
    }

    /**
     * ⚠️ Back does nothing on purpose. On a home screen there is nowhere behind,
     * and the default would finish the activity — leaving the kiosk looking at
     * whatever the system draws when no home app is showing.
     */
    override fun onBackPressed() = Unit

    private fun render() {
        val config = BundleSource.read(this)
        val entries = catalog.resolve(config.apps)

        grid.layoutManager = GridLayoutManager(this, config.columns)
        adapter.submit(entries)

        val nothing = entries.isEmpty()
        empty.visibility = if (nothing) View.VISIBLE else View.GONE
        grid.visibility = if (nothing) View.GONE else View.VISIBLE

        // Chunk 2 fills these in; the views exist now so the layout is settled.
        clock.visibility = View.GONE
    }

    private fun open(entry: AppEntry) {
        val intent = Intent(entry.intent).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        runCatching { startActivity(intent) }.onFailure {
            // A tile whose app has just been removed, or one lock task refuses.
            // Said out loud: silence here is indistinguishable from a frozen
            // device, which is what a user reports instead of the real fault.
            Log.w(TAG, "could not open ${entry.ref}: ${it.message}")
            Toast.makeText(this, R.string.cannot_open, Toast.LENGTH_SHORT).show()
        }
    }

    private companion object {
        const val TAG = "AtlasLauncher"
    }
}
