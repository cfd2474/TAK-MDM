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

/**
 * Is this install failure worth attempting again (W96, R19)?
 *
 * ⚠️ **Some failures are properties of the build, not of the moment.** An APK
 * whose native code does not match the CPU will fail identically forever —
 * `INSTALL_FAILED_NO_MATCHING_ABIS` cost one SM-X520 a multi-megabyte download
 * and a failed install on *every* reconcile, for days, with no possibility of
 * success. Retrying that is not resilience, it is a loop.
 *
 * ⚠️ **Giving up is not the same as going quiet.** A build ruled out here is
 * still reported and still leaves the device non-compliant: the app really is
 * missing and the operator really does need to know. What stops is the download
 * and the install attempt, not the reporting. A fault that stops being mentioned
 * is a fault nobody fixes.
 *
 * ⚠️ **Judged on the platform's message, which is a wire format of sorts.** These
 * names come from `PackageManager` and have been stable for many releases, but
 * matching text is inherently loose — so the default is to **retry**. Treating an
 * unknown failure as permanent could strand an app over a transient fault, which
 * is the worse mistake of the two.
 */
object InstallRetryPlan {

    /**
     * Failures that cannot be fixed by trying the same file again.
     *
     * Each is a mismatch between what the build *is* and what the device *is*:
     * no amount of waiting changes either.
     */
    private val PERMANENT = listOf(
        // The build's native code does not match this CPU. R19 exactly.
        "INSTALL_FAILED_NO_MATCHING_ABIS",
        // The build needs a newer Android than this device runs.
        "INSTALL_FAILED_OLDER_SDK",
        // A newer version is already installed; Android refuses downgrades.
        "INSTALL_FAILED_VERSION_DOWNGRADE",
        // Signed by a different key than the installed app: a policy problem,
        // not a network one, and retrying cannot resolve it.
        "INSTALL_FAILED_UPDATE_INCOMPATIBLE",
        "INSTALL_FAILED_DUPLICATE_PERMISSION",
        // The file itself is not installable. A re-download of the same bytes
        // produces the same bytes.
        "INSTALL_PARSE_FAILED",
        "INSTALL_FAILED_INVALID_APK",
    )

    /**
     * Should the agent try this build again on the next reconcile?
     *
     * Unknown failures answer true: storage fills up, downloads truncate, the
     * installer is busy, and every one of those clears on its own.
     */
    fun shouldRetry(message: String?): Boolean {
        val text = message.orEmpty().uppercase()
        return PERMANENT.none { text.contains(it) }
    }

    /**
     * A stable key for "this exact build on this device".
     *
     * ⚠️ Keyed on the artifact digest, not the package name. A package whose
     * policy moves to a different build must be tried again — the new file is
     * not the one that failed, and refusing it because its predecessor could not
     * install would make the fix invisible.
     */
    fun keyFor(packageName: String, artifactSha256: String): String =
        "$packageName@$artifactSha256"
}
