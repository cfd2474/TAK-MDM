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

package com.taksolutions.atlasmdm.policy

/**
 * Which position to believe, when several providers answer (W162).
 *
 * Pure, and deliberately so — the same reason as [LocationSamplingPlan]. Choosing
 * between a coarse fix from a second ago and a precise one from a minute ago is
 * arithmetic over timestamps and accuracies; none of it needs Android, and all of
 * the awkward cases are testable on the JVM rather than only on a tablet standing
 * in the wrong car park.
 *
 * ⚠️ **The agent used to have no such decision to make**, because it never asked
 * for a fix at all: `locate` and the periodic sampler both read
 * `getLastKnownLocation`, a passive cache that some *other* app has to fill.
 * Reporting was therefore parasitic — accurate on a tablet running ATAK, silently
 * hours stale on one that was not, with nothing to tell the two apart from the
 * console. Asking for a fix is what creates the question this object answers.
 */
object LocationFixPlan {

    /**
     * One provider's answer, stripped of Android.
     *
     * `accuracyMetres` is nullable because a `Location` need not carry one, and a
     * missing accuracy must never read as `0f` — a perfect fix is exactly what an
     * absent accuracy is not.
     */
    data class Candidate(
        val latitude: Double,
        val longitude: Double,
        val accuracyMetres: Float?,
        val provider: String,
        val timeMillis: Long,
    )

    /**
     * How old a fix may be and still be called *current*.
     *
     * Thirty seconds: long enough that a fix obtained while the providers were
     * still settling still counts, short enough that nothing from a previous
     * location can. It bounds the answer to "where is this tablet **now**", which
     * is the only question `locate` is ever asked.
     */
    const val FRESH_WINDOW_MS = 30_000L

    /**
     * An accuracy beyond which a fix is not worth preferring on precision alone.
     *
     * ⚠️ Comparing accuracies directly would let a 3 000 m cell-tower estimate beat
     * a 2 000 m one and call that an improvement. Past this radius the number has
     * stopped describing a position and started describing a town, so such fixes
     * are ordered by age instead — a recent vague answer is more useful than an old
     * vague one, whereas between two *precise* answers precision is what matters.
     */
    const val USABLE_ACCURACY_M = 200f

    /** Is this fix recent enough to present as the device's current position? */
    fun isFresh(candidate: Candidate, now: Long, windowMs: Long = FRESH_WINDOW_MS): Boolean {
        val age = now - candidate.timeMillis
        // ⚠️ A negative age is a device whose clock is ahead of ours, not a fix
        // from the future. Treated as fresh: the alternative is that a tablet with
        // a skewed clock can never report its position at all, and the skew is not
        // something the holder of the tablet can see or fix.
        if (age < 0L) return true
        return age <= windowMs
    }

    /**
     * The fix to report, or `null` if there is nothing to report at all.
     *
     * ⚠️ **Accuracy first, not recency.** Both are wanted and they conflict: the
     * network provider answers in milliseconds with a kilometre of error while GPS
     * takes tens of seconds and lands within metres. Ordering by age would hand
     * back the cell-tower estimate every single time and the GPS session would be
     * wasted — which is indistinguishable, from the console, from not having asked.
     *
     * So: anything usably precise wins on precision, and only among the vague is
     * age the tie-breaker. An unknown accuracy sorts with the vague, because a fix
     * that will not say how wrong it might be cannot be allowed to beat one that
     * does.
     */
    fun best(candidates: List<Candidate>): Candidate? {
        if (candidates.isEmpty()) return null

        val precise = candidates.filter {
            it.accuracyMetres != null && it.accuracyMetres <= USABLE_ACCURACY_M
        }
        if (precise.isNotEmpty()) {
            // Accuracy, then age: two fixes of equal precision are separated by
            // which one describes the device's position more recently.
            return precise.minWithOrNull(
                compareBy<Candidate> { it.accuracyMetres!! }.thenByDescending { it.timeMillis }
            )
        }
        return candidates.maxByOrNull { it.timeMillis }
    }

    /**
     * Age in whole seconds, for the operator's benefit, never negative.
     *
     * The console shows this next to the position so a fallback reads as a
     * fallback. Clamping at zero keeps a skewed device clock from reporting a
     * position as arriving from the future, which reads as a bug in us.
     */
    fun ageSeconds(candidate: Candidate, now: Long): Long =
        maxOf(0L, (now - candidate.timeMillis) / 1000L)
}
