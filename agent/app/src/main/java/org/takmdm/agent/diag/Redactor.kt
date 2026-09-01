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

/**
 * Removes secrets from log lines before they are persisted.
 *
 * These logs leave the device when an operator collects them, so the old
 * assumption — that a log is local and transient — no longer holds. Two layers,
 * because neither is sufficient alone:
 *
 *  * **Exact values**, registered while they are live. Catches an enrollment token
 *    that reaches a log through a message nobody thought to check, including one in
 *    a third-party stack trace.
 *  * **Shapes**, for values never registered: PEM blocks, and long opaque tokens
 *    following a word like `token=` or `secret:`.
 *
 * The right primary defence is still not logging a secret in the first place. This
 * is what catches the case where that failed.
 */
object Redactor {

    private const val MASK = "[redacted]"

    /** Live secret values. Never more than a handful. */
    private val secrets = mutableSetOf<String>()

    /**
     * A shape to remove, paired with what replaces it. The replacement is explicit
     * per rule because some rules keep a label and others do not.
     */
    private class Rule(val regex: Regex, val replace: (MatchResult) -> String)

    private val rules = listOf(
        // PEM private keys, across lines. Replaced whole.
        Rule(
            Regex(
                "-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
                setOf(RegexOption.DOT_MATCHES_ALL)
            )
        ) { MASK },
        // token=…, "secret": "…", Authorization: Bearer …
        // The label is kept so the reader can see *what* was removed; a bare mask
        // reads like a parsing bug.
        Rule(
            Regex(
                """((?:token|secret|password|passwd|bearer|authorization)\W{1,4})([A-Za-z0-9+/=_-]{12,})""",
                RegexOption.IGNORE_CASE
            )
        ) { "${it.groupValues[1]}$MASK" }
    )

    /**
     * Register a value that must never appear in a log.
     *
     * Short values are ignored: masking every occurrence of a three-character
     * string would redact ordinary prose and make the log useless, which is its own
     * kind of failure.
     */
    fun protect(value: String?) {
        if (value == null || value.length < MIN_SECRET_LENGTH) return
        synchronized(secrets) { secrets.add(value) }
    }

    /** Forget a value that is no longer live, e.g. a consumed enrollment token. */
    fun forget(value: String?) {
        if (value == null) return
        synchronized(secrets) { secrets.remove(value) }
    }

    fun scrub(text: String): String {
        var result = text

        // Longest first, so a secret containing another is masked whole rather than
        // leaving a fragment of it behind.
        val snapshot = synchronized(secrets) { secrets.sortedByDescending { it.length } }
        for (secret in snapshot) {
            if (result.contains(secret)) result = result.replace(secret, MASK)
        }

        for (rule in rules) {
            result = rule.regex.replace(result, rule.replace)
        }

        return result
    }

    private const val MIN_SECRET_LENGTH = 8

    /** Test seam: the registry is process-wide state. */
    internal fun resetForTest() = synchronized(secrets) { secrets.clear() }
}
