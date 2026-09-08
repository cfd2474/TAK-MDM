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

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import androidx.annotation.LayoutRes
import androidx.recyclerview.widget.RecyclerView

/**
 * The app tiles, for both the grid and the dock.
 *
 * ⚠️ **The two need different item layouts, and only the width differs** (W95).
 * A `GridLayoutManager` reads `match_parent` as one column, so the grid tile is
 * right to use it. The dock is a horizontal `LinearLayoutManager`, where
 * `match_parent` means the whole RecyclerView — which put the first favourite
 * across the entire dock and laid every other one off-screen. Nothing was lost
 * and nothing was logged; the apps were all there and only one was visible.
 *
 * The layout is a constructor argument rather than a branch inside
 * `onCreateViewHolder`, so a caller cannot forget which one it wanted.
 */
class AppAdapter(
    private var entries: List<AppEntry>,
    private val onOpen: (AppEntry) -> Unit,
    @LayoutRes private val itemLayout: Int = R.layout.item_app_tile,
) : RecyclerView.Adapter<AppAdapter.Tile>() {

    class Tile(view: View) : RecyclerView.ViewHolder(view) {
        val icon: ImageView = view.findViewById(R.id.icon)
        val label: TextView = view.findViewById(R.id.label)
    }

    fun submit(next: List<AppEntry>) {
        entries = next
        // The whole grid, deliberately: a kiosk shows a handful of apps and the
        // list changes only when a policy does. DiffUtil here would be machinery
        // for a case that never arises.
        notifyDataSetChanged()
    }

    override fun getItemCount(): Int = entries.size

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): Tile =
        Tile(LayoutInflater.from(parent.context).inflate(itemLayout, parent, false))

    override fun onBindViewHolder(holder: Tile, position: Int) {
        val entry = entries[position]
        holder.icon.setImageDrawable(entry.icon)
        holder.label.text = entry.label
        holder.itemView.contentDescription = entry.label
        holder.itemView.setOnClickListener { onOpen(entry) }
    }
}
