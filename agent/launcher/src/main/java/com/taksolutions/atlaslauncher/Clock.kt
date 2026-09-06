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

import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/**
 * The home screen clock (W68, Chunk 2).
 *
 * Two rows: the device's own time on top, Zulu beneath it. Both are wanted at
 * once — the local row is what someone at the device reads, the Zulu row is what
 * they say on the net — so this is not a choice between them.
 *
 * Pure formatting, taking the instant and the zone rather than reading them, so
 * the Zulu rule can be tested rather than trusted.
 */
object Clock {

    /**
     * ⚠️ `HHmmss'Z'` — TAK convention, not `HH:mm:ss UTC`. On a device whose whole
     * purpose is coordinating with other people on a shared time reference, the
     * trailing Z is what says *which* reference, and it is the form those people
     * read on every other surface they use.
     *
     * ⚠️ Keeping the separators off is also what tells the two rows apart at a
     * glance. Rendered with colons beside the local row it reads as the same
     * clock printed twice with a stray Z.
     */
    private val ZULU: DateTimeFormatter = DateTimeFormatter.ofPattern("HHmmss'Z'")

    /** 24-hour, always: a kiosk clock that needed AM/PM read would be worse. */
    private val LOCAL: DateTimeFormatter = DateTimeFormatter.ofPattern("HH:mm:ss")

    /** The device's own time zone, 24-hour. The top row. */
    fun local(instant: Instant, zone: ZoneId): String = LOCAL.format(instant.atZone(zone))

    /** UTC, whatever the device's zone is. The row beneath. */
    fun zulu(instant: Instant): String = ZULU.format(instant.atZone(ZoneId.of("UTC")))
}
