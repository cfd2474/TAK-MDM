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

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

private class RecordingHandler(
    override val type: String,
    private val outcome: CommandOutcome = CommandOutcome.ok()
) : CommandHandler {
    var calls = 0
    override fun execute(command: Command): CommandOutcome {
        calls++
        return outcome
    }
}

private fun envelope(id: String, type: String, params: JSONObject = JSONObject()) =
    JSONObject().put("id", id).put("command_type", type).put("params", params)

private fun arrayOfCommands(vararg items: JSONObject) =
    JSONArray().apply { items.forEach { put(it) } }

class CommandDispatcherTest {

    @Test
    fun `a registered handler runs and reports success`() {
        val handler = RecordingHandler("lock")
        val dispatcher = CommandDispatcher(listOf(handler))

        val dispatched = dispatcher.dispatch(arrayOfCommands(envelope("c1", "lock")))

        assertEquals(1, handler.calls)
        assertEquals(1, dispatched.results.size)
        assertTrue(dispatched.results[0].succeeded)
        assertEquals("c1", dispatched.results[0].commandId)
    }

    @Test
    fun `an unknown command type is reported, not dropped`() {
        val dispatcher = CommandDispatcher(listOf(RecordingHandler("lock")))

        val dispatched = dispatcher.dispatch(arrayOfCommands(envelope("c9", "teleport")))

        // The bug this whole class exists to fix. Dropping it silently meant the
        // server redelivered until max_attempts and then showed
        // "EXPIRED - exceeded max attempts": a device that received the command and
        // failed, rather than an agent that cannot execute one (D89).
        assertEquals(1, dispatched.results.size)
        assertFalse(dispatched.results[0].succeeded)
        assertTrue(dispatched.results[0].error!!.contains("unsupported"))
    }

    @Test
    fun `a handler that throws becomes a failed result rather than aborting the batch`() {
        val throwing = object : CommandHandler {
            override val type = "locate"
            override fun execute(command: Command): CommandOutcome =
                throw IllegalStateException("no location provider")
        }
        val after = RecordingHandler("lock")
        val dispatcher = CommandDispatcher(listOf(throwing, after))

        val dispatched = dispatcher.dispatch(
            arrayOfCommands(envelope("c1", "locate"), envelope("c2", "lock"))
        )

        // One failing command must not strand the others: they are independent
        // one-shots, and the queue redelivers whatever went unreported.
        assertEquals(2, dispatched.results.size)
        assertFalse(dispatched.results[0].succeeded)
        assertTrue(dispatched.results[0].error!!.contains("no location provider"))
        assertEquals(1, after.calls)
    }

    @Test
    fun `a deferred effect is returned and not executed`() {
        var fired = false
        val handler = object : CommandHandler {
            override val type = "reboot"
            override fun execute(command: Command) =
                CommandOutcome.okAfterReporting { fired = true }
        }
        val dispatcher = CommandDispatcher(listOf(handler))

        val dispatched = dispatcher.dispatch(arrayOfCommands(envelope("c1", "reboot")))

        // Running it here would kill the process before the result could be sent,
        // so the server would redeliver and the device would reboot again on the
        // next check-in — a loop ending only when the queue exhausts its attempts.
        assertFalse("the effect must wait until its result is reported", fired)
        assertEquals(1, dispatched.deferredEffects.size)
        assertTrue(dispatched.results[0].succeeded)

        dispatched.deferredEffects.first()()
        assertTrue(fired)
    }

    @Test
    fun `a malformed envelope is skipped without stopping the batch`() {
        val handler = RecordingHandler("lock")
        val dispatcher = CommandDispatcher(listOf(handler))

        val dispatched = dispatcher.dispatch(
            arrayOfCommands(JSONObject().put("no_id", true), envelope("c2", "lock"))
        )

        // No id means nothing to report against, so there is no honest result to
        // send. The valid command beside it must still run.
        assertEquals(1, dispatched.results.size)
        assertEquals("c2", dispatched.results[0].commandId)
        assertEquals(1, handler.calls)
    }

    @Test
    fun `duplicate handlers for one type are rejected at construction`() {
        val error = runCatching {
            CommandDispatcher(listOf(RecordingHandler("lock"), RecordingHandler("lock")))
        }.exceptionOrNull()

        // Otherwise one of them silently never runs, and which one depends on
        // registration order — a fault that would surface as a command that works
        // on one build and not the next.
        assertNotNull(error)
        assertTrue(error!!.message!!.contains("lock"))
    }

    @Test
    fun `results carry the shape the checkin request expects`() {
        val dispatcher = CommandDispatcher(
            listOf(RecordingHandler("locate", CommandOutcome.ok(JSONObject().put("lat", 51.5))))
        )

        val json = dispatcher.dispatch(arrayOfCommands(envelope("c1", "locate")))
            .results.first().toJson()

        // Field names are the wire contract with app/api/schemas.py:CommandResultReport.
        assertEquals("c1", json.getString("command_id"))
        assertTrue(json.getBoolean("succeeded"))
        assertEquals(51.5, json.getJSONObject("result").getDouble("lat"), 0.0001)
    }
}
