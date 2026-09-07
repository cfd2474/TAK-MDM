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
 * When a downloaded APK has done its job and can be thrown away (W88).
 *
 * `PackageInstaller` copies what it is handed into the system's own store, so once
 * an install succeeds the agent's copy is dead weight — and an APK is the largest
 * thing the agent ever writes. Left alone, a device accumulates one copy of every
 * app it has ever been sent, plus one of every agent build it has taken.
 *
 * ⚠️ **Deleting too eagerly costs a re-download over a field connection**, which is
 * the expensive mistake here, so the rule is deliberately narrow: a file goes only
 * once something is known to have been installed from it.
 *
 * Pure and separated from the reconciler because the self-update case cannot be
 * observed on a device at all — the process is killed part-way through the install,
 * so the decision is made by whichever build starts *next*, reading a note the dead
 * one left behind. A test is the only place that sequence can be watched.
 */
object InstallerCachePlan {

    /**
     * Whether the parts an install consumed should be discarded now.
     *
     * ⚠️ **Kept on failure, on purpose.** The cache is what the next attempt reuses:
     * a download that passed its sha check is byte-correct, so re-fetching it would
     * buy nothing and cost the whole transfer again. A failed install is retried on
     * the next sync and finds its parts still there.
     */
    fun discardAfterInstall(installSucceeded: Boolean): Boolean = installSucceeded

    /**
     * Whether a recorded self-update has finished, given the build now running.
     *
     * @param runningVersionCode the `versionCode` of the build asking.
     * @param pendingVersionCode the `versionCode` the dead build was installing.
     *
     * ⚠️ **`>=`, not `==`.** Reaching here *above* the pending version means a
     * later update overtook it — that APK is spent too, and an `==` test would
     * strand it on disk forever with nothing left that could ever match it.
     *
     * Below it means the install did not take, so the download is kept for the
     * retry rather than thrown away and fetched again.
     */
    fun selfUpdateFinished(runningVersionCode: Long, pendingVersionCode: Long): Boolean =
        runningVersionCode >= pendingVersionCode
}
