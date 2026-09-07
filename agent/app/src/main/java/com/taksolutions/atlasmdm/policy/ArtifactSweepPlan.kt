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
 * Which files in the artifact cache are spent, for the devices that filled it
 * before [InstallerCachePlan] existed (W89).
 *
 * W88 stopped the cache growing: an install discards what it consumed. It could
 * not touch what was already there — three fielded devices carrying every APK
 * they had ever been sent — because a device only revisits an app's files when it
 * has something to install, and an app already installed never gets that far.
 *
 * So this looks from the other end: rather than waiting for an install to clean
 * up after itself, it asks of each cached file *is there any remaining reason to
 * keep this?*
 *
 * ⚠️ **The dangerous mistake is deleting a file something is about to open**, and
 * every rule below is shaped by it. `installFromStore` downloads on the Apps
 * screen while a sync runs, so its parts are unreferenced, unspent, and very much
 * in use for the minute between the download verifying and `PackageInstaller`
 * opening them. [MIN_AGE_MILLIS] is what protects that window; nothing else here
 * can see it.
 */
object ArtifactSweepPlan {

    /**
     * How long a file is left alone regardless of what the rules say.
     *
     * ⚠️ Load-bearing, not a tidy default. A store install can hold a verified
     * download for as long as the user takes to confirm it, and no state visible
     * here says that is happening. Six hours is far beyond any real install and
     * costs nothing: the backlog this exists to clear is days or weeks old, so it
     * is eligible the first time the sweep runs.
     */
    const val MIN_AGE_MILLIS = 6L * 60 * 60 * 1000

    /** Suffix `ApiClient` gives a partial download it may resume. */
    const val PART_SUFFIX = ".part"

    private val SHA256 = Regex("[0-9a-f]{64}")

    /**
     * The files that can go, out of [names].
     *
     * @param names what is in the cache directory now.
     * @param ageMillis how long since each was last written.
     * @param desired the current desired-state bundle.
     * @param installedVersionCode the device's installed versionCode for a
     *   package, or null if absent.
     * @param keep shas that must survive whatever the rules say — the in-flight
     *   self-update, whose owning process is dead and cannot defend it.
     */
    fun sweep(
        names: List<String>,
        ageMillis: (String) -> Long,
        desired: JSONObject,
        installedVersionCode: (String) -> Long?,
        keep: Set<String>,
    ): List<String> {
        val referenced = referencedShas(desired)
        val spent = spentShas(desired, installedVersionCode)
        return names.filter { name ->
            val sha = name.removeSuffix(PART_SUFFIX)
            when {
                // Not a file this cache put here. Something else owns it, and a
                // sweeper that deletes what it does not recognise is a liability.
                !SHA256.matches(sha) -> false
                sha in keep -> false
                ageMillis(name) < MIN_AGE_MILLIS -> false
                // ⚠️ Before the `referenced` test, not after: a spent APK is still
                // named by the policy that installed it, so testing references
                // first would keep the entire backlog forever.
                sha in spent -> true
                else -> sha !in referenced
            }
        }
    }

    /**
     * Shas belonging to an app the device has already installed.
     *
     * Decided by [AppUpdatePlan], deliberately rather than by comparing version
     * codes again here: "the device already has this" is one idea, and two copies
     * of it would drift. Every outcome except INSTALL and UPGRADE means
     * there is nothing left to install from these files — including
     * REFUSED_DOWNGRADE and SKIP_PINNED, where the reconciler has decided it will
     * never install them, which makes keeping them worse than pointless.
     */
    private fun spentShas(desired: JSONObject, installedVersionCode: (String) -> Long?): Set<String> {
        val apps = desired.optJSONArray("apps") ?: return emptySet()
        val spent = mutableSetOf<String>()
        for (index in 0 until apps.length()) {
            val app = apps.optJSONObject(index) ?: continue
            val packageName = app.optString("package_name").takeIf { it.isNotBlank() } ?: continue
            val action = AppUpdatePlan.decide(
                installed = installedVersionCode(packageName),
                desired = app.optLong("version_code", -1),
                autoUpdate = app.optBoolean("auto_update", true),
            )
            if (action == AppUpdatePlan.Action.INSTALL || action == AppUpdatePlan.Action.UPGRADE) continue
            val files = app.optJSONArray("files") ?: continue
            for (fileIndex in 0 until files.length()) {
                files.optJSONObject(fileIndex)?.optString("sha256")
                    ?.lowercase()
                    ?.takeIf { SHA256.matches(it) }
                    ?.let { spent += it }
            }
        }
        return spent
    }

    /**
     * Every sha256 anywhere in the bundle, found by walking it rather than by
     * reading the fields we know about.
     *
     * ⚠️ Deliberately structure-blind. A sweeper that enumerated *"apps, files,
     * wallpaper…"* would quietly start deleting live artifacts the day the server
     * grew a new kind — and the failure would land on a fielded device as an app
     * that re-downloads forever. Collecting anything shaped like a sha cannot miss
     * one; at worst it keeps a file it did not have to.
     */
    fun referencedShas(node: Any?): Set<String> = when (node) {
        is JSONObject -> node.keys().asSequence()
            .flatMap { referencedShas(node.opt(it)).asSequence() }
            .toSet()
        is JSONArray -> (0 until node.length())
            .flatMap { referencedShas(node.opt(it)) }
            .toSet()
        is String -> if (SHA256.matches(node.lowercase())) setOf(node.lowercase()) else emptySet()
        else -> emptySet()
    }
}
