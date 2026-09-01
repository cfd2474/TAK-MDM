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

package org.takmdm.agent.diag

import android.util.Log

/**
 * The agent's own diagnostic log.
 *
 * **Deliberately not `logcat`.** `READ_LOGS` has been restricted to privileged
 * system apps since API 16, so a normally-installed Device Owner cannot read the
 * system buffer — and whether an unprivileged app may still read back its *own*
 * lines is not something any official source confirms, so nothing here depends on
 * it. Android's own guidance is to keep your own logs in internal storage rather
 * than using the system log, which is what this does (D87).
 *
 * Writing our own also puts redaction under our control, which matters once these
 * lines leave the device on an operator's request.
 *
 * Entries still tee to `logcat` so `adb` remains useful whenever it is available.
 */
object AgentLog {

    /**
     * Where entries are persisted.
     *
     * An interface so the store can be swapped — a test uses an in-memory sink, and
     * a future build could add a second destination — without this facade knowing.
     */
    @Volatile
    private var sink: LogSink = NoopLogSink

    /**
     * Installed once, from `Application.onCreate`.
     *
     * Until then every call is a plain `logcat` write and nothing is persisted. That
     * is deliberate: a log facade that throws or queues before initialisation would
     * turn a diagnostic aid into a new failure mode.
     */
    fun install(sink: LogSink) {
        this.sink = sink
    }

    fun d(tag: String, message: String) = write(Log.DEBUG, tag, message, null)
    fun i(tag: String, message: String) = write(Log.INFO, tag, message, null)
    fun w(tag: String, message: String, error: Throwable? = null) =
        write(Log.WARN, tag, message, error)

    fun e(tag: String, message: String, error: Throwable? = null) =
        write(Log.ERROR, tag, message, error)

    /** Everything the operator can currently be shown, oldest first. */
    fun dump(): String = sink.read()

    fun clear() = sink.clear()

    private fun write(level: Int, tag: String, message: String, error: Throwable?) {
        val safe = Redactor.scrub(message)
        Log.println(level, tag, safe)
        if (error != null) Log.println(level, tag, Log.getStackTraceString(error))

        runCatching { sink.write(LogEntry(System.currentTimeMillis(), level, tag, safe, error)) }
            // A failing log must never take down the thing it is observing.
            .onFailure { Log.w(TAG, "log sink write failed: ${it.message}") }
    }

    private const val TAG = "AgentLog"
}

/** One recorded line. */
data class LogEntry(
    val timestampMillis: Long,
    val level: Int,
    val tag: String,
    val message: String,
    val error: Throwable? = null
)

/** Somewhere entries are kept until an operator asks for them. */
interface LogSink {
    fun write(entry: LogEntry)

    /** Everything currently held, oldest first, formatted for a human. */
    fun read(): String

    fun clear()
}

/** Used before [AgentLog.install]; keeps the facade total rather than nullable. */
object NoopLogSink : LogSink {
    override fun write(entry: LogEntry) = Unit
    override fun read() = ""
    override fun clear() = Unit
}
