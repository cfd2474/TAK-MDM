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

package com.taksolutions.atlasmdm.policy

import org.json.JSONArray
import org.json.JSONObject

/**
 * Turns the Kiosk policy into what the ATLAS launcher should be told (W68).
 *
 * ⚠️ **This is one half of a wire format** — the other half is the launcher's
 * `res/xml/app_restrictions.xml`, and the two ship as separate APKs that update
 * independently. A device can therefore be running an old launcher with a new
 * agent, or the reverse, so nothing here may assume the other side is the same
 * version: unknown keys are simply not sent, and missing ones fall back.
 *
 * Pure, and separate from the applier, because the interesting failures are
 * shape failures — an app list sent as a scalar, a favourite naming an app that
 * is not permitted — and none of them need a device to find.
 */
object LauncherConfigPlan {

    /** One tile, as the launcher's `bundle_array` will carry it. */
    data class App(
        val packageName: String,
        val activity: String? = null,
        val favorite: Boolean = false,
    )

    data class Plan(
        val apps: List<App> = emptyList(),
        val columns: Int = DEFAULT_COLUMNS,
        val showSearch: Boolean = true,
        val showClock: Boolean = true,
        val clockZulu: Boolean = true,
        val orientation: String = "auto",
    ) {
        /** Every package the launcher may open — what lock task has to permit. */
        val packages: List<String> get() = apps.map { it.packageName }

        /**
         * The same plan with the ATLAS console guaranteed a tile (W70).
         *
         * ⚠️ **Separate from [from] on purpose.** `from` reports what the *policy*
         * asks for, and two other decisions read it: whether this is a multi-app
         * kiosk at all, and whether the launcher should be uninstalled. Appending
         * the agent inside `from` would make every single-app kiosk look like a
         * multi-app one and lock the device to a launcher nobody asked for.
         *
         * ⚠️ Appended, never moved. An operator who placed the console themselves
         * has said where they want it — and if they marked it a favourite, that
         * stands too.
         */
        fun withAgent(agentPackage: String): Plan {
            // The console tile is the agent with **no** activity. Matching the
            // package alone would see a Device Settings tile and conclude the
            // console was already there (W71).
            val already = apps.any { it.packageName == agentPackage && it.activity == null }
            if (already) return this
            return copy(apps = apps + App(agentPackage))
        }

        /**
         * A Device Settings tile, when the policy offers the user anything to
         * change (W71).
         *
         * ⚠️ Keyed on the **activity**, not the package. The console tile is the
         * same package, so a package-level de-duplication would drop whichever of
         * the two came second and the operator would lose one at random.
         */
        fun withDeviceSettings(agentPackage: String, activity: String): Plan {
            val already = apps.any {
                it.packageName == agentPackage && it.activity == activity
            }
            if (already) return this
            return copy(apps = apps + App(agentPackage, activity))
        }
    }

    const val DEFAULT_COLUMNS = 4
    const val MIN_COLUMNS = 2
    const val MAX_COLUMNS = 8

    const val KEY_APPS = "multi_app_packages"
    const val KEY_COLUMNS = "launcher_columns"
    const val KEY_SHOW_SEARCH = "launcher_show_search"
    const val KEY_SHOW_CLOCK = "launcher_show_clock"
    const val KEY_CLOCK_ZULU = "launcher_clock_zulu"
    const val KEY_ORIENTATION = "launcher_orientation"

    private val ORIENTATIONS = setOf("auto", "portrait", "landscape")

    fun from(kiosk: JSONObject): Plan = Plan(
        apps = apps(kiosk.optJSONArray(KEY_APPS)),
        columns = kiosk.optInt(KEY_COLUMNS, DEFAULT_COLUMNS).coerceIn(MIN_COLUMNS, MAX_COLUMNS),
        showSearch = kiosk.optBoolean(KEY_SHOW_SEARCH, true),
        showClock = kiosk.optBoolean(KEY_SHOW_CLOCK, true),
        clockZulu = kiosk.optBoolean(KEY_CLOCK_ZULU, true),
        orientation = kiosk.optString(KEY_ORIENTATION, "auto")
            .trim().lowercase()
            .takeIf { it in ORIENTATIONS } ?: "auto",
    )

    /**
     * Should the ATLAS launcher be taken off this device (W69)?
     *
     * ⚠️ Clearing the HOME preference is not enough on its own: with the launcher
     * still installed the device has *two* home apps and no default, so pressing
     * HOME raises Android's "Complete action using…" chooser instead of going to
     * the stock launcher. An operator who removed a policy expects the device back
     * as it was, not one asking them which launcher they meant.
     *
     * Pure so the rule can be tested; the uninstall itself lives with the
     * installer.
     *
     * @param kiosk the KIOSK section of the effective policy.
     * @param requiredPackages every package the policy asks the device to have —
     *   an operator who puts the launcher there by hand means it, and this must
     *   not fight them.
     */
    fun shouldRemoveLauncher(kiosk: JSONObject, requiredPackages: Collection<String>): Boolean =
        from(kiosk).apps.isEmpty() && ATLAS_LAUNCHER !in requiredPackages

    /** Must match the server's `ATLAS_LAUNCHER_PACKAGE`; one contract, two languages. */
    const val ATLAS_LAUNCHER = "com.taksolutions.atlaslauncher"

    /**
     * Read the app list, which arrives as **either** plain package names or
     * objects carrying an activity and a favourite flag.
     *
     * ⚠️ Both forms on purpose. The console sends objects; a hand-written or older
     * policy sends strings, and refusing those would turn a policy that used to
     * work into a kiosk with no apps — which looks like the launcher is broken,
     * not like the policy is old.
     */
    private fun apps(raw: JSONArray?): List<App> {
        if (raw == null) return emptyList()
        val out = LinkedHashMap<String, App>()
        for (i in 0 until raw.length()) {
            val app = when (val item = raw.opt(i)) {
                is JSONObject -> fromObject(item)
                is String -> fromString(item)
                else -> null
            } ?: continue
            // ⚠️ Keyed on package *and* activity (W71). One app meant one tile
            // until the agent needed two — its console and its Device Settings
            // screen are the same package — and a package-level key dropped
            // whichever came second with nothing said. The same component twice
            // is still a merge artefact, and first wins.
            out.putIfAbsent("${app.packageName}/${app.activity.orEmpty()}", app)
        }
        return out.values.toList()
    }

    private fun fromObject(item: JSONObject): App? {
        val pkg = item.optString("package_name").ifBlank { item.optString("package") }.trim()
        if (!looksLikeAPackage(pkg)) return null
        val activity = item.optString("activity").trim()
        return App(
            packageName = pkg,
            activity = qualify(pkg, activity),
            favorite = item.optBoolean("favorite", false),
        )
    }

    /** `package` or `package/activity`, the same form the kiosk app field uses. */
    private fun fromString(item: String): App? {
        val value = item.trim()
        val slash = value.indexOf('/')
        // `slash == 0` is "no package", not "no activity" — an entry that could
        // never open anything.
        if (slash == 0) return null
        if (slash < 0) return if (looksLikeAPackage(value)) App(value) else null
        val pkg = value.substring(0, slash)
        if (!looksLikeAPackage(pkg)) return null
        return App(pkg, qualify(pkg, value.substring(slash + 1).trim()))
    }

    /**
     * A leading dot is Android's shorthand for "relative to the package" — the
     * same trap the kiosk launch and the console's `component_class()` handle.
     */
    private fun qualify(pkg: String, activity: String): String? = when {
        activity.isEmpty() -> null
        activity.startsWith(".") -> pkg + activity
        else -> activity
    }

    private fun looksLikeAPackage(value: String): Boolean =
        value.isNotEmpty() && !value.contains(' ') && !value.contains('/')
}
