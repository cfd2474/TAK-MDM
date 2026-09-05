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

import org.json.JSONObject

/** One transient action handed down in a check-in response. */
data class Command(
    val id: String,
    val type: String,
    val params: JSONObject
) {
    companion object {
        fun fromJson(json: JSONObject): Command? {
            val id = json.optString("id").takeIf { it.isNotBlank() } ?: return null
            val type = json.optString("command_type").takeIf { it.isNotBlank() } ?: return null
            return Command(id, type, json.optJSONObject("params") ?: JSONObject())
        }
    }
}

/**
 * What happened, reported back on the next check-in.
 *
 * [deferred] exists because two commands end the session that would report them.
 * A reboot or a wipe executed inline means the result never reaches the server, so
 * the command is redelivered on the next check-in and executed again — a device
 * that reboot-loops until the queue expires. Handlers for those return the effect
 * instead of performing it, and the caller runs it only once the result is
 * safely acknowledged.
 */
data class CommandOutcome(
    val succeeded: Boolean,
    val result: JSONObject? = null,
    val error: String? = null,
    val deferred: (() -> Unit)? = null
) {
    companion object {
        fun ok(result: JSONObject? = null) = CommandOutcome(true, result)
        fun failed(reason: String) = CommandOutcome(false, error = reason)

        /** Succeeded, but the effect runs after the result is reported. */
        fun okAfterReporting(effect: () -> Unit) = CommandOutcome(true, deferred = effect)
    }
}

/**
 * Executes one command type.
 *
 * One implementation per type, registered by [type], so adding a command does not
 * mean editing a dispatcher (D88). A `when` block would have been shorter and is
 * precisely how the seventh type gets forgotten.
 */
interface CommandHandler {
    /** Matches the server's `CommandType` value, e.g. `"lock"`. */
    val type: String

    fun execute(command: Command): CommandOutcome
}
