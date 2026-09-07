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

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ArtifactSweepPlanTest {

    private val atakSha = "a".repeat(64)
    private val splitSha = "b".repeat(64)
    private val chromeSha = "c".repeat(64)
    private val orphanSha = "d".repeat(64)
    private val wallpaperSha = "e".repeat(64)

    private val old = ArtifactSweepPlan.MIN_AGE_MILLIS * 10
    private val fresh = ArtifactSweepPlan.MIN_AGE_MILLIS / 2

    /** ATAK installed at 5 with a split; Chrome required but not yet installed. */
    private fun desired() = JSONObject(
        """
        {
          "apps": [
            {"package_name": "com.atakmap.app.civ", "version_code": 5, "files": [
              {"role": "base", "sha256": "$atakSha"},
              {"role": "split", "sha256": "$splitSha"}
            ]},
            {"package_name": "com.android.chrome", "version_code": 9, "files": [
              {"role": "base", "sha256": "$chromeSha"}
            ]}
          ],
          "policy": {"customizations": {"wallpaper": {"tablet": {"sha256": "$wallpaperSha"}}}}
        }
        """.trimIndent()
    )

    private fun sweep(
        names: List<String>,
        age: Long = old,
        installed: Map<String, Long> = mapOf("com.atakmap.app.civ" to 5L),
        keep: Set<String> = emptySet(),
    ) = ArtifactSweepPlan.sweep(
        names = names,
        ageMillis = { age },
        desired = desired(),
        installedVersionCode = { installed[it] },
        keep = keep,
    )

    @Test
    fun `an installed app's parts are spent, every one of them`() {
        // ⚠️ The backlog case, and the one an obvious implementation gets wrong:
        // these shas ARE named by the current policy. Testing "is it referenced?"
        // first would keep every APK on the device forever, which is the bug this
        // whole file exists to fix.
        assertEquals(
            listOf(atakSha, splitSha),
            sweep(listOf(atakSha, splitSha)),
        )
    }

    @Test
    fun `an app still waiting to be installed keeps its download`() {
        // Chrome is required and absent: this file is the install, not litter.
        assertTrue(sweep(listOf(chromeSha)).isEmpty())
    }

    @Test
    fun `a half-finished upgrade keeps its download`() {
        // ATAK on the device at 4, policy wants 5 — UPGRADE, so the APK is live.
        assertTrue(
            sweep(listOf(atakSha), installed = mapOf("com.atakmap.app.civ" to 4L)).isEmpty()
        )
    }

    @Test
    fun `an app pinned below the installed build is spent, not kept`() {
        // REFUSED_DOWNGRADE: the reconciler has decided it will never install
        // these, so holding them is worse than pointless.
        assertEquals(
            listOf(atakSha),
            sweep(listOf(atakSha), installed = mapOf("com.atakmap.app.civ" to 7L)),
        )
    }

    @Test
    fun `an artifact nothing mentions any more goes`() {
        // A removed app, or an agent build two updates ago.
        assertEquals(listOf(orphanSha), sweep(listOf(orphanSha)))
    }

    @Test
    fun `a wallpaper the bundle still names is kept`() {
        // ⚠️ Found by walking the bundle, not by reading "apps". A sweeper that
        // enumerated the fields it knew about would delete this, and the device
        // would re-download the wallpaper on every sync forever.
        assertTrue(sweep(listOf(wallpaperSha)).isEmpty())
    }

    @Test
    fun `nothing recent is touched, however spent it looks`() {
        // The store-install window: downloaded, verified, not yet handed to
        // PackageInstaller. No state visible here can see that happening.
        assertTrue(sweep(listOf(orphanSha, atakSha), age = fresh).isEmpty())
    }

    @Test
    fun `a partial download is swept on the same rules as the file`() {
        assertEquals(
            listOf("$orphanSha${ArtifactSweepPlan.PART_SUFFIX}"),
            sweep(listOf("$orphanSha${ArtifactSweepPlan.PART_SUFFIX}")),
        )
    }

    @Test
    fun `a partial download of something still wanted is kept`() {
        assertTrue(
            sweep(listOf("$chromeSha${ArtifactSweepPlan.PART_SUFFIX}")).isEmpty()
        )
    }

    @Test
    fun `the pending self-update survives, having no process left to defend it`() {
        assertTrue(sweep(listOf(orphanSha), keep = setOf(orphanSha)).isEmpty())
    }

    @Test
    fun `a file this cache did not name is left alone`() {
        // Not ours. A sweeper that deletes what it does not recognise is a
        // liability, and cacheDir is not guaranteed to be ours alone.
        assertTrue(sweep(listOf("something-else.txt", "notes")).isEmpty())
    }

    @Test
    fun `an empty bundle sweeps everything old rather than throwing`() {
        val swept = ArtifactSweepPlan.sweep(
            names = listOf(atakSha),
            ageMillis = { old },
            desired = JSONObject("{}"),
            installedVersionCode = { null },
            keep = emptySet(),
        )
        assertEquals(listOf(atakSha), swept)
    }
}
