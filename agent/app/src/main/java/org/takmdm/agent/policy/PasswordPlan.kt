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

package org.takmdm.agent.policy

/**
 * The pure part of password-policy application: what passcode *quality* the
 * device must enforce, given the server's fields.
 *
 * The agent drives the passcode through the granular `setPasswordMinimum*`
 * family rather than the newer complexity buckets, because that family maps 1:1
 * onto the spec (`min_length`, `min_letters`, `min_digits`, `min_symbols`) and a
 * Device Owner on a company-owned device may still use it. That family only
 * *bites* at a high enough quality, and the per-character-class setters throw
 * `IllegalStateException` below [PwQuality.COMPLEX] — so the quality has to be
 * derived from the other fields, not taken at face value. That derivation is
 * here so it can be unit-tested; the `DevicePolicyManager` calls in
 * [PolicyApplier.applyPassword] are only exercised on hardware.
 */
object PasswordPlan {

    /** Least → most restrictive; ordinals match the server's `PasswordQuality` (0–6). */
    enum class PwQuality { UNSPECIFIED, SOMETHING, NUMERIC, NUMERIC_COMPLEX, ALPHABETIC, ALPHANUMERIC, COMPLEX }

    private val BY_ORDINAL = PwQuality.entries

    /**
     * The quality to pass to `setPasswordQuality`. **Never null** — when the
     * policy asks for nothing this is [PwQuality.UNSPECIFIED], which the applier
     * pushes so a quality left over from a policy that no longer applies is
     * released rather than latched (R14).
     *
     * It is the strictest of:
     *  - the mapped `quality` field;
     *  - [PwQuality.NUMERIC] if a `min_length` is set (a length floor is ignored
     *    below NUMERIC);
     *  - [PwQuality.COMPLEX] if any of `min_letters` / `min_digits` / `min_symbols`
     *    is set (the granular setters require it).
     *
     * Bumping up never weakens the operator's intent — a higher quality is a
     * superset requirement.
     */
    fun effectiveQuality(
        quality: Int?,
        minLength: Int?,
        minLetters: Int?,
        minDigits: Int?,
        minSymbols: Int?,
    ): PwQuality {
        var q = BY_ORDINAL.getOrNull(quality ?: 0) ?: PwQuality.UNSPECIFIED
        if ((minLength ?: 0) > 0 && q < PwQuality.NUMERIC) q = PwQuality.NUMERIC
        if (listOf(minLetters, minDigits, minSymbols).any { (it ?: 0) > 0 }) q = PwQuality.COMPLEX
        return q
    }

    /**
     * The per-character-class minimums only apply once quality is COMPLEX — below
     * it the setters throw `IllegalStateException` for an app targeting API 30+,
     * and the values are inert anyway (Android reference §6c).
     */
    fun charClassMinimumsApply(effective: PwQuality): Boolean = effective == PwQuality.COMPLEX
}
