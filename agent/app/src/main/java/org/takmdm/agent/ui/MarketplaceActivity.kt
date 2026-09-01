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

package org.takmdm.agent.ui

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import org.takmdm.agent.R
import org.takmdm.agent.core.AgentConfig
import org.takmdm.agent.files.FileDeployer
import org.takmdm.agent.sync.Reconciler

/**
 * The marketplace (F4).
 *
 * The admin curates what is *available*; the user decides what is installed. The
 * selection is stored locally and reported at the next check-in, so the console can
 * show what was actually taken rather than only what was offered.
 */
class MarketplaceActivity : AppCompatActivity() {

    private lateinit var config: AgentConfig
    private lateinit var adapter: OfferAdapter

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_marketplace)
        config = AgentConfig(this)

        adapter = OfferAdapter(::toggle)
        findViewById<RecyclerView>(R.id.offers).apply {
            layoutManager = LinearLayoutManager(this@MarketplaceActivity)
            adapter = this@MarketplaceActivity.adapter
        }

        render()
    }

    private fun render() {
        val desired = config.cachedDesiredState?.let { JSONObject(it) }
        val available = desired?.optJSONObject("files")?.optJSONArray("available")

        val offers = buildList {
            for (index in 0 until (available?.length() ?: 0)) {
                available?.optJSONObject(index)?.let { add(it) }
            }
        }

        findViewById<TextView>(R.id.empty).visibility =
            if (offers.isEmpty()) View.VISIBLE else View.GONE

        adapter.submit(offers, config.selectedOptionalFiles)
    }

    private fun toggle(offer: JSONObject) {
        val fileId = offer.optString("file_id")
        val selected = config.selectedOptionalFiles.toMutableSet()

        if (fileId in selected) {
            selected.remove(fileId)
            // Forget that we placed it, but leave the file alone: deployment is
            // write-only and removing it is the user's business, not ours. Dropping
            // the record is what lets them take it again later — otherwise the
            // agent would remember placing it and skip the re-push forever.
            config.forgetAppliedFile(FileDeployer.stateKeyFor(offer))
        } else {
            selected.add(fileId)
        }
        config.selectedOptionalFiles = selected
        render()

        // Apply immediately rather than waiting for the next cycle: the user just
        // asked for this and should see it happen.
        lifecycleScope.launch {
            val result = withContext(Dispatchers.IO) {
                runCatching { Reconciler(applicationContext).sync() }
            }
            result.onSuccess { outcome ->
                val message = if (outcome.errors.isEmpty()) "Updated"
                else outcome.errors.first()
                Toast.makeText(this@MarketplaceActivity, message, Toast.LENGTH_LONG).show()
            }.onFailure {
                Toast.makeText(
                    this@MarketplaceActivity, "Failed: ${it.message}", Toast.LENGTH_LONG
                ).show()
            }
        }
    }
}

private class OfferAdapter(
    private val onToggle: (JSONObject) -> Unit
) : RecyclerView.Adapter<OfferAdapter.Holder>() {

    private var offers: List<JSONObject> = emptyList()
    private var selected: Set<String> = emptySet()

    fun submit(offers: List<JSONObject>, selected: Set<String>) {
        this.offers = offers
        this.selected = selected
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): Holder =
        Holder(
            LayoutInflater.from(parent.context).inflate(R.layout.item_offer, parent, false)
        )

    override fun getItemCount(): Int = offers.size

    override fun onBindViewHolder(holder: Holder, position: Int) {
        val offer = offers[position]
        val isSelected = offer.optString("file_id") in selected

        holder.title.text = offer.optString("title").ifBlank { offer.optString("name") }
        holder.detail.text = buildString {
            offer.optString("description").takeIf { it.isNotBlank() }?.let { appendLine(it) }
            val bytes = offer.optLong("size_bytes", 0)
            // Integer KB rounded anything under 1 KB down to "0 KB", which reads as
            // "there is nothing to download" for exactly the small config files this
            // catalogue mostly carries.
            if (bytes > 0) append("${humanSize(bytes)} → ${offer.optString("dest_path")}")
        }
        holder.action.setText(
            if (isSelected) R.string.remove else R.string.install
        )
        holder.action.setOnClickListener { onToggle(offer) }
    }

    /** Bytes for tiny files, KB, then MB — never a misleading "0 KB". */
    private fun humanSize(bytes: Long): String = when {
        bytes < 1024 -> "$bytes bytes"
        bytes < 1024 * 1024 -> "${bytes / 1024} KB"
        else -> String.format(java.util.Locale.US, "%.1f MB", bytes / (1024.0 * 1024.0))
    }

    class Holder(view: View) : RecyclerView.ViewHolder(view) {
        val title: TextView = view.findViewById(R.id.offer_title)
        val detail: TextView = view.findViewById(R.id.offer_detail)
        val action: Button = view.findViewById(R.id.offer_action)
    }
}
