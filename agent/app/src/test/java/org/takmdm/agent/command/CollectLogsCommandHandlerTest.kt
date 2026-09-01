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
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CollectLogsCommandHandlerTest {

    private class Recorder {
        var uploaded: String? = null
        var uploadedFor: String? = null
        var cleared = false
    }

    private fun handler(recorder: Recorder, logs: () -> String) =
        CollectLogsCommandHandler(
            readLogs = logs,
            uploadLogs = { text, commandId ->
                recorder.uploaded = text
                recorder.uploadedFor = commandId
            },
            clearLogs = { recorder.cleared = true }
        )

    private fun command(params: JSONObject = JSONObject()) =
        Command(id = "cmd-1", type = "collect_logs", params = params)

    @Test
    fun `the log is uploaded and attributed to the command`() {
        val recorder = Recorder()

        val outcome = handler(recorder) { "line one\nline two\n" }.execute(command())

        assertTrue(outcome.succeeded)
        assertEquals("line one\nline two\n", recorder.uploaded)
        // The link is what tells an operator which request produced which capture.
        assertEquals("cmd-1", recorder.uploadedFor)
    }

    @Test
    fun `an empty log is a success, not a failure`() {
        val recorder = Recorder()

        val outcome = handler(recorder) { "" }.execute(command())

        // A device that has behaved since its last collection genuinely has nothing
        // to say. Reporting that as an error sends an operator hunting a fault that
        // is not there.
        assertTrue(outcome.succeeded)
        assertEquals(0, outcome.result!!.getInt("bytes"))
        assertEquals(null, recorder.uploaded)
    }

    @Test
    fun `the log is kept by default`() {
        val recorder = Recorder()

        handler(recorder) { "something\n" }.execute(command())

        // The second collection in an investigation usually wants the context of
        // the first, so discarding is opt-in.
        assertFalse(recorder.cleared)
    }

    @Test
    fun `clear_after discards the log once it is uploaded`() {
        val recorder = Recorder()

        handler(recorder) { "something\n" }
            .execute(command(JSONObject().put("clear_after", true)))

        assertTrue(recorder.cleared)
    }

    @Test
    fun `byte count is measured in bytes not characters`() {
        val recorder = Recorder()

        val outcome = handler(recorder) { "éééé" }.execute(command())

        // Characters and bytes diverge exactly where a cap matters; the server
        // measures bytes, so a mismatch here would let a bundle be refused after a
        // handler reported it as comfortably within the limit.
        assertEquals(8, outcome.result!!.getInt("bytes"))
    }
}
