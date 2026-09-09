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

/**
 * Reading the desired state's certificate list (W112).
 *
 * Pure, so the cases that matter can be tested off-device: a policy naming a file
 * somebody deleted, a duplicate, a malformed entry. None of those can be produced
 * by holding a tablet, and each one decides whether a device ends up trusting the
 * right set.
 */
object CertificatePlan {

    data class Anchor(val sha256: String, val name: String)

    /**
     * The anchors this device should trust.
     *
     * ⚠️ **Entries marked unavailable are skipped, not treated as "trust
     * nothing".** A policy referencing a deleted file is broken, and the fix is to
     * report it — dropping the whole list because one row is bad would silently
     * remove every other anchor the device legitimately needs.
     */
    fun wanted(entries: JSONArray?): List<Anchor> {
        if (entries == null) return emptyList()

        val out = mutableListOf<Anchor>()
        val seen = mutableSetOf<String>()
        for (i in 0 until entries.length()) {
            val row = entries.optJSONObject(i) ?: continue
            if (!row.optBoolean("available", false)) continue
            val sha = row.optString("sha256").trim()
            if (sha.isEmpty() || !seen.add(sha)) continue
            out += Anchor(sha, row.optString("name").ifBlank { sha.take(12) })
        }
        return out
    }

    /**
     * Complaints about entries the server could not resolve.
     *
     * A policy naming a file that has been deleted has to *look* broken. Reported
     * as an apply error so it reaches the console, rather than being visible only
     * as a certificate that never appears.
     */
    fun unavailable(entries: JSONArray?): List<String> {
        if (entries == null) return emptyList()

        val out = mutableListOf<String>()
        for (i in 0 until entries.length()) {
            val row = entries.optJSONObject(i) ?: continue
            if (row.optBoolean("available", false)) continue
            out += "certificate ${row.optString("file_id")}: the file is no longer " +
                "in the library, so it cannot be installed"
        }
        return out
    }
}
