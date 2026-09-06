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

/**
 * What the Device Owner has told this launcher to show (W68).
 *
 * ⚠️ **Every field has a usable default, and parsing never throws.** This app is
 * the home screen: a device whose config is missing, empty or malformed must
 * still get a working screen, because there is nowhere else for the user to go.
 * The failure mode of a launcher that refuses to start is a device that needs
 * physical recovery, so the parser's job is to salvage, not to validate.
 *
 * ⚠️ It reads a [Source], not a `Bundle`, and that is not ceremony. Under plain
 * JVM unit tests `Bundle` is a stub whose getters return defaults, so a test
 * written against one would pass no matter what this parser did — the salvage
 * rules would be exactly the code that is never exercised. The interface is what
 * makes them testable off-device.
 */
data class LauncherConfig(
    /** Ordered, as the operator arranged them. */
    val apps: List<AppRef> = emptyList(),
    val columns: Int = DEFAULT_COLUMNS,
    val showSearch: Boolean = true,
    val showClock: Boolean = true,
    val clockZulu: Boolean = true,
    val nightMode: Boolean = false,
    val nightHue: NightHue = NightHue.RED,
    /** 0 = no dimming, 100 = as dark as the overlay goes. */
    val nightLevel: Int = DEFAULT_NIGHT_LEVEL,
    val orientation: Orientation = Orientation.AUTO,
) {

    /** One tile: a package, optionally a specific screen, optionally pinned. */
    data class AppRef(
        val packageName: String,
        val activity: String? = null,
        val favorite: Boolean = false,
    )

    /** The pinned subset, in the same order. Cannot disagree with [apps]. */
    val favorites: List<AppRef> get() = apps.filter { it.favorite }

    enum class NightHue(val key: String, val color: Int) {
        // Red first because it is the default and the reason the feature exists:
        // it preserves dark adaptation in a way amber and green do not.
        RED("red", 0xFFFF0000.toInt()),
        AMBER("amber", 0xFFFFBF00.toInt()),
        GREEN("green", 0xFF00FF00.toInt()),
        ;

        companion object {
            fun from(value: String?): NightHue =
                entries.firstOrNull { it.key.equals(value?.trim(), ignoreCase = true) } ?: RED
        }
    }

    enum class Orientation(val key: String) {
        AUTO("auto"),
        PORTRAIT("portrait"),
        LANDSCAPE("landscape"),
        ;

        companion object {
            fun from(value: String?): Orientation =
                entries.firstOrNull { it.key.equals(value?.trim(), ignoreCase = true) } ?: AUTO
        }
    }

    companion object {
        const val DEFAULT_COLUMNS = 4
        const val DEFAULT_NIGHT_LEVEL = 50

        /**
         * ⚠️ Clamped, not rejected. A column count of 0 divides by zero in a grid
         * and a count of 40 gives tiles too small to hit; either would be a broken
         * home screen delivered by a policy that looked like it saved cleanly.
         * The console refuses silly values too — this is the second line, for a
         * config that arrives from an older or hand-edited source.
         */
        const val MIN_COLUMNS = 2
        const val MAX_COLUMNS = 8

        const val KEY_APPS = "apps"
        const val KEY_APP_PACKAGE = "package"
        const val KEY_APP_ACTIVITY = "activity"
        const val KEY_APP_FAVORITE = "favorite"
        const val KEY_COLUMNS = "columns"
        const val KEY_SHOW_SEARCH = "show_search"
        const val KEY_SHOW_CLOCK = "show_clock"
        const val KEY_CLOCK_ZULU = "clock_zulu"
        const val KEY_NIGHT_MODE = "night_mode"
        const val KEY_NIGHT_HUE = "night_hue"
        const val KEY_NIGHT_LEVEL = "night_level"
        const val KEY_ORIENTATION = "orientation"

        /**
         * Where the values come from. Implemented over a `Bundle` on a device and
         * over a map in tests.
         */
        interface Source {
            val isEmpty: Boolean
            fun int(key: String, fallback: Int): Int
            fun bool(key: String, fallback: Boolean): Boolean
            fun string(key: String): String?

            /** A `bundle_array` member, each read as a nested source. */
            fun bundles(key: String): List<Source>?
        }

        /**
         * An empty source gives the defaults, which is the state of a launcher
         * installed but not yet configured — a real moment on every device,
         * between the install finishing and the next policy push.
         */
        fun from(source: Source?): LauncherConfig {
            if (source == null || source.isEmpty) return LauncherConfig()

            return LauncherConfig(
                apps = refs(source.bundles(KEY_APPS)),
                columns = source.int(KEY_COLUMNS, DEFAULT_COLUMNS)
                    .coerceIn(MIN_COLUMNS, MAX_COLUMNS),
                showSearch = source.bool(KEY_SHOW_SEARCH, true),
                showClock = source.bool(KEY_SHOW_CLOCK, true),
                clockZulu = source.bool(KEY_CLOCK_ZULU, true),
                nightMode = source.bool(KEY_NIGHT_MODE, false),
                nightHue = NightHue.from(source.string(KEY_NIGHT_HUE)),
                nightLevel = source.int(KEY_NIGHT_LEVEL, DEFAULT_NIGHT_LEVEL)
                    .coerceIn(0, 100),
                orientation = Orientation.from(source.string(KEY_ORIENTATION)),
            )
        }

        /**
         * Read the app records, keeping the order given and dropping what cannot
         * be a tile.
         *
         * ⚠️ Duplicates are removed. The same app twice is always a mistake — a
         * merge of two policies, or an operator adding it from search and from
         * the list — and two identical tiles look like a rendering fault. The
         * first wins, so the operator's first placement stands.
         */
        private fun refs(raw: List<Source>?): List<AppRef> {
            if (raw == null) return emptyList()
            val out = LinkedHashMap<String, AppRef>()
            for (entry in raw) {
                val pkg = entry.string(KEY_APP_PACKAGE)?.trim().orEmpty()
                // A record with no package cannot open anything, and a tile that
                // does nothing when tapped is indistinguishable from a frozen
                // device.
                if (pkg.isEmpty() || pkg.contains('/') || pkg.contains(' ')) continue

                val activity = entry.string(KEY_APP_ACTIVITY)?.trim().orEmpty()
                out.putIfAbsent(
                    pkg,
                    AppRef(
                        packageName = pkg,
                        // A leading dot is Android's shorthand for "relative to
                        // the package", the same trap the agent's kiosk launch
                        // handles.
                        activity = when {
                            activity.isEmpty() -> null
                            activity.startsWith(".") -> pkg + activity
                            else -> activity
                        },
                        favorite = entry.bool(KEY_APP_FAVORITE, false),
                    ),
                )
            }
            return out.values.toList()
        }
    }
}
