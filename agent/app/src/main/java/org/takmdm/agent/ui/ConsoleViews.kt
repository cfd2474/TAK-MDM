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

package org.takmdm.agent.ui

import android.content.Context
import android.graphics.Typeface
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.content.ContextCompat
import com.google.android.material.card.MaterialCardView
import org.takmdm.agent.R

/**
 * Small view builders for the status console, so each section's render code reads
 * as a layout rather than a pile of `LayoutParams` boilerplate. Kept out of the
 * activity because there are five sections and they all want the same card, the
 * same label/value row, and the same status pill.
 */
object ConsoleViews {

    fun dp(context: Context, value: Int): Int =
        (value * context.resources.displayMetrics.density).toInt()

    /** A section heading. */
    fun sectionTitle(context: Context, text: CharSequence): TextView =
        TextView(context).apply {
            setText(text)
            setTextAppearance(R.style.TextAppearance_Atlas_SectionTitle)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 18f)
            val m = dp(context, 4)
            layoutParams = LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT).apply {
                topMargin = m; bottomMargin = dp(context, 12)
            }
        }

    /** An outlined card the sections drop their content into. */
    fun card(context: Context): MaterialCardView {
        val card = MaterialCardView(context)
        card.layoutParams = LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT).apply {
            bottomMargin = dp(context, 12)
        }
        card.radius = dp(context, 14).toFloat()
        card.cardElevation = 0f
        card.setCardBackgroundColor(ContextCompat.getColor(context, R.color.atlas_navy_panel))
        card.strokeColor = ContextCompat.getColor(context, R.color.atlas_navy_line)
        card.strokeWidth = dp(context, 1)
        val inner = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            val p = dp(context, 16)
            setPadding(p, p, p, p)
        }
        card.addView(inner)
        card.tag = inner
        return card
    }

    /** The content container inside a [card]. */
    fun body(card: MaterialCardView): LinearLayout = card.tag as LinearLayout

    /** A "LABEL" over a value, the device-info and policy-field row. */
    fun kv(context: Context, label: CharSequence, value: CharSequence, mono: Boolean = false): View {
        val row = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT).apply {
                topMargin = dp(context, 6); bottomMargin = dp(context, 6)
            }
        }
        row.addView(TextView(context).apply {
            text = label
            setTextAppearance(R.style.TextAppearance_Atlas_Label)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 11f)
        })
        row.addView(TextView(context).apply {
            text = value
            if (mono) {
                setTextAppearance(R.style.TextAppearance_Atlas_Mono)
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
            } else {
                setTextAppearance(R.style.TextAppearance_Atlas_Value)
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 15f)
            }
            setTextIsSelectable(true)
            val t = dp(context, 2)
            setPadding(0, t, 0, 0)
        })
        return row
    }

    enum class Tone { OK, WARN, ERROR, NEUTRAL }

    /** A rounded status chip. */
    fun pill(context: Context, text: CharSequence, tone: Tone): TextView =
        TextView(context).apply {
            setText(text)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
            typeface = Typeface.DEFAULT_BOLD
            gravity = Gravity.CENTER
            val hp = dp(context, 10); val vp = dp(context, 4)
            setPadding(hp, vp, hp, vp)
            setBackgroundResource(R.drawable.bg_pill)
            setTextColor(
                ContextCompat.getColor(
                    context,
                    when (tone) {
                        Tone.OK -> R.color.atlas_ok
                        Tone.WARN -> R.color.atlas_warn
                        Tone.ERROR -> R.color.atlas_error
                        Tone.NEUTRAL -> R.color.atlas_steel
                    }
                )
            )
            layoutParams = LinearLayout.LayoutParams(WRAP_CONTENT, WRAP_CONTENT)
        }

    /** Faint full-width rule between rows in a card. */
    fun divider(context: Context): View =
        View(context).apply {
            layoutParams = LinearLayout.LayoutParams(MATCH_PARENT, dp(context, 1)).apply {
                topMargin = dp(context, 6); bottomMargin = dp(context, 6)
            }
            setBackgroundColor(ContextCompat.getColor(context, R.color.atlas_navy_line))
        }

    fun emptyNote(context: Context, text: CharSequence): TextView =
        TextView(context).apply {
            setText(text)
            setTextColor(ContextCompat.getColor(context, R.color.atlas_text_muted))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
            setPadding(0, dp(context, 8), 0, 0)
        }
}
