package org.takmdm.agent.core

import org.json.JSONArray
import org.json.JSONObject

/**
 * Canonical JSON, matching the server's `app/security/bundle.py` byte for byte.
 *
 * Sorted keys, no insignificant whitespace, UTF-8. The server signs this exact
 * encoding, so any divergence here makes every bundle signature fail with nothing
 * to indicate why. It is reimplemented rather than shared precisely because the two
 * must agree independently — `scripts/dev_enroll.py` verifies a third
 * implementation against the server for the same reason.
 */
object CanonicalJson {

    private const val FORM_FEED = ''

    fun encode(value: Any?): ByteArray =
        buildString { write(value, this) }.toByteArray(Charsets.UTF_8)

    private fun write(value: Any?, out: StringBuilder) {
        when (value) {
            null, JSONObject.NULL -> out.append("null")
            is JSONObject -> writeObject(value, out)
            is JSONArray -> writeArray(value, out)
            is String -> writeString(value, out)
            is Boolean -> out.append(if (value) "true" else "false")
            is Int, is Long -> out.append(value.toString())
            is Double -> writeNumber(value, out)
            is Float -> writeNumber(value.toDouble(), out)
            else -> writeString(value.toString(), out)
        }
    }

    private fun writeNumber(value: Double, out: StringBuilder) {
        // A whole number must serialize as "8", not "8.0". Python never adds a
        // fractional part to an int, and org.json readily parses an integral
        // literal into a Double.
        if (value.isFinite() && value == Math.floor(value) && Math.abs(value) < 1e15) {
            out.append(value.toLong().toString())
        } else {
            out.append(value.toString())
        }
    }

    private fun writeObject(obj: JSONObject, out: StringBuilder) {
        val keys = obj.keys().asSequence().toMutableList()
        keys.sort()
        out.append('{')
        keys.forEachIndexed { index, key ->
            if (index > 0) out.append(',')
            writeString(key, out)
            out.append(':')
            write(obj.opt(key), out)
        }
        out.append('}')
    }

    private fun writeArray(array: JSONArray, out: StringBuilder) {
        out.append('[')
        for (index in 0 until array.length()) {
            if (index > 0) out.append(',')
            write(array.opt(index), out)
        }
        out.append(']')
    }

    private fun writeString(value: String, out: StringBuilder) {
        out.append('"')
        for (char in value) {
            when (char) {
                '"' -> out.append("\\\"")
                '\\' -> out.append("\\\\")
                '\n' -> out.append("\\n")
                '\r' -> out.append("\\r")
                '\t' -> out.append("\\t")
                '\b' -> out.append("\\b")
                // Python escapes form feed as \f rather than , so it needs
                // its own case. Kotlin has no \f escape, hence the constant.
                FORM_FEED -> out.append("\\f")
                else ->
                    // ensure_ascii=False leaves non-ASCII as literal UTF-8, so only
                    // genuine control characters are escaped.
                    if (char < ' ') {
                        out.append(String.format("\\u%04x", char.code))
                    } else {
                        out.append(char)
                    }
            }
        }
        out.append('"')
    }
}
