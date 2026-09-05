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

package com.taksolutions.atlasmdm.command

import org.json.JSONArray
import org.json.JSONObject
import com.taksolutions.atlasmdm.diag.AgentLog

/** A finished command, in the shape the check-in request expects. */
data class ReportedResult(
    val commandId: String,
    val succeeded: Boolean,
    val result: JSONObject?,
    val error: String?
) {
    fun toJson(): JSONObject = JSONObject()
        .put("command_id", commandId)
        .put("succeeded", succeeded)
        .put("result", result ?: JSONObject.NULL)
        .put("error", error ?: JSONObject.NULL)
}

/**
 * Runs the commands a check-in handed down and collects their results.
 *
 * Until this existed the agent read the desired state and **ignored the `commands`
 * array entirely** — the server dispatched, counted an attempt, and the device
 * dropped it. Because each delivery counts an attempt, an enqueued `LOCK` was
 * retried until `max_attempts` and then shown in the console as
 * `EXPIRED — exceeded max attempts`: a device that received the command and failed,
 * rather than an agent that could not execute one. A remote wipe promised something
 * it could not do.
 */
class CommandDispatcher(handlers: List<CommandHandler>) {

    private val byType: Map<String, CommandHandler> = handlers.associateBy { it.type }

    init {
        val duplicates = handlers.groupBy { it.type }.filterValues { it.size > 1 }.keys
        // Two handlers for one type means one of them silently never runs, and which
        // one depends on registration order. Fail at construction instead.
        require(duplicates.isEmpty()) { "duplicate command handlers for: $duplicates" }
    }

    /**
     * Execute everything in [commands], oldest first.
     *
     * Returns the results to report and any deferred effects to run **after** those
     * results are safely acknowledged. The caller must not run the effects before
     * reporting; see [CommandOutcome.deferred].
     */
    fun dispatch(commands: JSONArray): Dispatched {
        val results = mutableListOf<ReportedResult>()
        val deferred = mutableListOf<() -> Unit>()

        for (index in 0 until commands.length()) {
            val json = commands.optJSONObject(index) ?: continue
            val command = Command.fromJson(json)
            if (command == null) {
                AgentLog.w(TAG, "ignoring malformed command envelope at index $index")
                continue
            }

            val outcome = execute(command)
            results += ReportedResult(
                command.id, outcome.succeeded, outcome.result, outcome.error
            )
            outcome.deferred?.let { deferred += it }
        }

        return Dispatched(results, deferred)
    }

    private fun execute(command: Command): CommandOutcome {
        val handler = byType[command.type]
        if (handler == null) {
            // Reported, never dropped (D89). The console must be able to tell "this
            // agent cannot do that" from "the device tried and failed" — silence
            // made the two identical, which is the bug this class exists to fix.
            val message = "unsupported by this agent build"
            AgentLog.w(TAG, "command ${command.id}: unknown type '${command.type}'")
            return CommandOutcome.failed(message)
        }

        AgentLog.i(TAG, "executing ${command.type} (${command.id})")
        return runCatching { handler.execute(command) }
            .getOrElse {
                val detail = "${it.javaClass.simpleName}: ${it.message ?: "no message"}"
                AgentLog.e(TAG, "command ${command.id} (${command.type}) threw", it)
                CommandOutcome.failed(detail)
            }
            .also {
                if (it.succeeded) AgentLog.i(TAG, "command ${command.id} succeeded")
                else AgentLog.w(TAG, "command ${command.id} failed: ${it.error}")
            }
    }

    /** Results to send, and effects to run once they are sent. */
    data class Dispatched(
        val results: List<ReportedResult>,
        val deferredEffects: List<() -> Unit>
    )

    private companion object {
        const val TAG = "CommandDispatcher"
    }
}
