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

package com.taksolutions.atlasmdm.ui

/**
 * What a file's card should say, and what it should offer (W91).
 *
 * Pure, and separate from [MainActivity], because the interesting case is a
 * judgement rather than a rendering: **whether the file is still there says
 * nothing about whether the package was delivered.**
 *
 * ATAK watches `tools/datapackage` and imports what it finds. Verified on
 * hardware 2026-09-07: it **leaves the zip in place** afterwards, so the file
 * usually survives — but a user may delete it, and ATAK's `incoming/` sweeps its
 * contents after two hours. Either way the disk is the wrong question: the file
 * being gone is not a delivery that failed, and re-writing it would make the
 * watcher import the package a second time.
 *
 * The applied-content record is the honest source for a package: the MDM knows
 * what it placed, and that does not stop being true when ATAK takes it.
 *
 * ⚠️ **"Delivered" is the strongest claim available.** Whether ATAK actually
 * imported the package is not observable from here: the watcher leaves nothing
 * the MDM can read, and a vanished zip is equally consistent with a successful
 * import and with a user deleting it. Saying "Imported" would assert something
 * unknown — the same line W90 draws when `applied N config keys` proves the
 * Bundle was set and nothing about ATAK having read it.
 */
object FileCardPlan {

    enum class State {
        /** Placed, and expected to stay there. */
        INSTALLED,

        /** Required by policy, not on disk yet. */
        PENDING,

        /** Handed to ATAK. Absence afterwards is success, not a fault. */
        DELIVERED,

        /** Offered in the marketplace; the user has not taken it. */
        OFFERED,

        /** The user took the offer and it is on disk. */
        TAKEN,
    }

    /**
     * @param dataPackage the server marked this entry as an ATAK data package.
     * @param optional the entry is a marketplace offer rather than policy-required.
     * @param selected the user has chosen this offer.
     * @param deliveredOnce the agent has a record of placing this exact content
     *   at this destination — [com.taksolutions.atlasmdm.core.AgentConfig.appliedFileHash].
     * @param onDisk the file is present and the right size right now.
     */
    fun stateFor(
        dataPackage: Boolean,
        optional: Boolean,
        selected: Boolean,
        deliveredOnce: Boolean,
        onDisk: Boolean,
    ): State = when {
        // ⚠️ Checked before `onDisk` on purpose. A package that has been handed
        // over is Delivered whether or not the file survives — and re-sending it
        // because the file went missing is precisely the repeated import this
        // design exists to prevent.
        dataPackage && deliveredOnce -> State.DELIVERED
        dataPackage -> State.PENDING
        optional && !selected -> State.OFFERED
        optional -> if (onDisk) State.TAKEN else State.PENDING
        onDisk -> State.INSTALLED
        else -> State.PENDING
    }

    /**
     * Whether the card offers **Re-download**.
     *
     * Only for a package already delivered: before that the policy is still going
     * to place it on its own, and a button that races the reconciler is a button
     * that sometimes appears to do nothing.
     */
    fun offersRedownload(dataPackage: Boolean, deliveredOnce: Boolean): Boolean =
        dataPackage && deliveredOnce
}
