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

package org.takmdm.agent.command

import org.json.JSONObject

/**
 * `collect_logs` — uploads the agent's own diagnostic log on request.
 *
 * The point of the whole command layer, in one handler: a fielded tablet that will
 * not converge cannot be diagnosed by plugging in a cable, and three rounds of
 * blind server-side guessing during enrolment showed what that costs (D79). This
 * is the remote form of the same idea.
 *
 * Dependencies are injected as functions rather than an `ApiClient` and a sink, so
 * the handler is testable off-device and knows nothing about either. Uploading is
 * not this class's job to know how to do.
 */
class CollectLogsCommandHandler(
    private val readLogs: () -> String,
    /** Receives the log text and the id of the command that asked for it. */
    private val uploadLogs: (text: String, commandId: String) -> Unit,
    private val clearLogs: () -> Unit
) : CommandHandler {

    override val type = "collect_logs"

    override fun execute(command: Command): CommandOutcome {
        val text = readLogs()
        if (text.isBlank()) {
            // Not a failure. A device that has behaved since its last collection
            // genuinely has nothing to say, and reporting that as an error would
            // send an operator hunting for a fault that is not there.
            return CommandOutcome.ok(
                JSONObject().put("bytes", 0).put("note", "no log entries held")
            )
        }

        uploadLogs(text, command.id)

        // Opt-in: the default keeps the history, because the second collection
        // during an investigation usually wants the context of the first.
        if (command.params.optBoolean("clear_after", false)) clearLogs()

        return CommandOutcome.ok(
            JSONObject()
                .put("bytes", text.toByteArray(Charsets.UTF_8).size)
                .put("lines", text.count { it == '\n' })
        )
    }
}
