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

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * What a file card claims (W91).
 *
 * The case worth testing is the one where the obvious implementation is wrong:
 * a data package is **supposed** to disappear, so a card that asks the disk
 * reports a perfectly delivered package as Pending forever.
 */
class FileCardPlanTest {

    private fun state(
        dataPackage: Boolean = false,
        optional: Boolean = false,
        selected: Boolean = false,
        deliveredOnce: Boolean = false,
        onDisk: Boolean = false,
    ) = FileCardPlan.stateFor(dataPackage, optional, selected, deliveredOnce, onDisk)

    @Test
    fun `a delivered package reads Delivered even though the file is gone`() {
        // ⚠️ The whole point. ATAK consumed the zip; that is success, not a fault.
        assertEquals(
            FileCardPlan.State.DELIVERED,
            state(dataPackage = true, deliveredOnce = true, onDisk = false),
        )
    }

    @Test
    fun `a delivered package still reads Delivered while the file is present`() {
        // The window before ATAK's watcher picks it up. Same claim either way:
        // what the MDM knows is that it handed the package over.
        assertEquals(
            FileCardPlan.State.DELIVERED,
            state(dataPackage = true, deliveredOnce = true, onDisk = true),
        )
    }

    @Test
    fun `a package not yet delivered is Pending`() {
        assertEquals(FileCardPlan.State.PENDING, state(dataPackage = true))
    }

    @Test
    fun `an ordinary required file is judged by the disk, not by the record`() {
        // Unchanged behaviour, and deliberately so: for a file meant to stay put,
        // "we placed it once" is not evidence it is still there — hardware showed
        // a deleted required file going unnoticed, which is why the check exists.
        assertEquals(
            FileCardPlan.State.PENDING,
            state(deliveredOnce = true, onDisk = false),
        )
        assertEquals(FileCardPlan.State.INSTALLED, state(onDisk = true))
    }

    @Test
    fun `an untaken offer reads as an offer`() {
        assertEquals(FileCardPlan.State.OFFERED, state(optional = true, selected = false))
    }

    @Test
    fun `a taken offer follows the disk`() {
        assertEquals(
            FileCardPlan.State.TAKEN,
            state(optional = true, selected = true, onDisk = true),
        )
        assertEquals(
            FileCardPlan.State.PENDING,
            state(optional = true, selected = true, onDisk = false),
        )
    }

    @Test
    fun `re-download is offered only once there is something to re-send`() {
        assertTrue(FileCardPlan.offersRedownload(dataPackage = true, deliveredOnce = true))
        // Before delivery the reconciler is still going to place it on its own,
        // and a button racing the reconciler is a button that sometimes appears
        // to do nothing.
        assertFalse(FileCardPlan.offersRedownload(dataPackage = true, deliveredOnce = false))
    }

    @Test
    fun `an ordinary file never offers re-download`() {
        assertFalse(FileCardPlan.offersRedownload(dataPackage = false, deliveredOnce = true))
    }
}
