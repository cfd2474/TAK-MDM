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

package com.taksolutions.atlasmdm.diag

import android.util.Log
import java.io.File
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

/**
 * A size-capped log on internal storage.
 *
 * Two files rather than one. Trimming a single file means rewriting it on every
 * overflow, and a process killed mid-rewrite loses the whole history — the log is
 * most likely to be truncated exactly when the agent is misbehaving, which is when
 * it is needed. Rotating instead is one rename, and the previous generation stays
 * intact.
 *
 * The bound is therefore `2 × maxBytes` worst case, which is the number that
 * matters for the upload cap on the other end.
 */
class RingFileLogSink(
    directory: File,
    private val maxBytes: Long = DEFAULT_MAX_BYTES
) : LogSink {

    private val current = File(directory, "agent.log")
    private val previous = File(directory, "agent.log.1")
    private val lock = Any()

    init {
        directory.mkdirs()
    }

    override fun write(entry: LogEntry) {
        val line = format(entry)
        synchronized(lock) {
            if (current.length() + line.length > maxBytes) rotate()
            current.appendText(line)
        }
    }

    override fun read(): String = synchronized(lock) {
        buildString {
            if (previous.exists()) append(previous.readText())
            if (current.exists()) append(current.readText())
        }
    }

    override fun clear() = synchronized(lock) {
        current.delete()
        previous.delete()
        Unit
    }

    /** Bytes currently held, so a caller can decide before reading it all in. */
    fun sizeBytes(): Long = synchronized(lock) {
        (if (previous.exists()) previous.length() else 0L) +
            (if (current.exists()) current.length() else 0L)
    }

    private fun rotate() {
        previous.delete()
        // renameTo can fail across odd filesystems; losing the older generation is
        // survivable, silently appending past the cap forever is not.
        if (!current.renameTo(previous)) current.delete()
    }

    private fun format(entry: LogEntry): String = buildString {
        append(TIMESTAMP.format(Instant.ofEpochMilli(entry.timestampMillis)))
        append(' ')
        append(levelChar(entry.level))
        append('/')
        append(entry.tag)
        append(": ")
        append(entry.message)
        append('\n')
        entry.error?.let {
            // The facade scrubbed the message but not the throwable, and an
            // exception message is exactly where an unredacted secret survives.
            append(Redactor.scrub(Log.getStackTraceString(it)))
            if (!endsWith('\n')) append('\n')
        }
    }

    private fun levelChar(level: Int): Char = when (level) {
        Log.VERBOSE -> 'V'
        Log.DEBUG -> 'D'
        Log.INFO -> 'I'
        Log.WARN -> 'W'
        Log.ERROR -> 'E'
        else -> '?'
    }

    companion object {
        /**
         * 256 KB per generation, 512 KB total. Comfortably more than one enrolment
         * or install cycle produces, and small enough to upload over a link that
         * this fleet is assumed to have very little of.
         */
        const val DEFAULT_MAX_BYTES = 256L * 1024

        /**
         * `java.time`, not `SimpleDateFormat`: entries are formatted off the lock
         * and `SimpleDateFormat` is not thread-safe, so sharing one instance
         * corrupts timestamps under concurrent writes — and the sync loop, the
         * WorkManager job and the command handlers all log from different threads.
         */
        private val TIMESTAMP: DateTimeFormatter =
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss.SSS", Locale.US)
                .withZone(ZoneId.systemDefault())
    }
}
