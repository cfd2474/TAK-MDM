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

import android.content.Context
import android.content.RestrictionsManager
import android.os.Bundle

/**
 * [LauncherConfig.Companion.Source] over the managed configuration the Device
 * Owner set for this app.
 *
 * The whole Android side of reading config: everything else is in the parser,
 * which is why this file has no rules in it worth testing and the parser has all
 * of them.
 */
class BundleSource(private val bundle: Bundle) : LauncherConfig.Companion.Source {

    override val isEmpty: Boolean get() = bundle.isEmpty

    /**
     * ⚠️ Accepts a lone `Bundle` as well as an array of them.
     * `setApplicationRestrictions` carries whatever the sender put in, and a
     * one-element list written as a bare bundle is exactly the mistake that
     * produces an empty home screen with nothing logged — the same shape as the
     * agent's multi-select-sent-as-a-scalar bug.
     */
    override fun bundles(key: String): List<LauncherConfig.Companion.Source>? {
        bundle.getParcelableArray(key, Bundle::class.java)?.let { array ->
            return array.map { BundleSource(it) }
        }
        bundle.getBundle(key)?.let { return listOf(BundleSource(it)) }
        return null
    }

    /** Tolerates an integer sent as a string, for the same reason. */
    override fun int(key: String, fallback: Int): Int = when {
        bundle.get(key) is Int -> bundle.getInt(key, fallback)
        else -> bundle.getString(key)?.trim()?.toIntOrNull() ?: fallback
    }

    override fun bool(key: String, fallback: Boolean): Boolean = when {
        bundle.get(key) is Boolean -> bundle.getBoolean(key, fallback)
        else -> when (bundle.getString(key)?.trim()?.lowercase()) {
            "true", "1", "yes" -> true
            "false", "0", "no" -> false
            else -> fallback
        }
    }

    override fun string(key: String): String? = bundle.getString(key)

    companion object {
        /** This app's managed configuration, or an empty config if it has none. */
        fun read(context: Context): LauncherConfig {
            val manager = context.getSystemService(RestrictionsManager::class.java)
            val bundle = runCatching { manager?.applicationRestrictions }.getOrNull()
            return LauncherConfig.from(bundle?.let(::BundleSource))
        }
    }
}
