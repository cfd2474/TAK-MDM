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

package com.taksolutions.atlasmdm.ui

import android.content.Context
import android.util.TypedValue
import android.view.View
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.widget.LinearLayout
import android.widget.SeekBar
import android.widget.TextView
import com.google.android.material.materialswitch.MaterialSwitch
import com.taksolutions.atlasmdm.R

/**
 * The controls on the kiosk's Device Settings screen (W71).
 *
 * Beside [ConsoleViews] rather than inside it, because the console *reports* and
 * this *changes things* — and the two have different obligations. Every control
 * here applies immediately and shows the value the device actually holds after
 * the write, never the value that was asked for.
 *
 * ⚠️ **A control must never lie about having worked.** Most of what a Device
 * Owner can change here can also be refused by the platform, and a switch that
 * springs back to where it was tells the user more honestly than a toast they
 * will not read. So every setter returns the value the device ended up with, and
 * the row re-renders from that.
 */
object SettingsViews {

    private fun dp(context: Context, value: Int) = ConsoleViews.dp(context, value)

    /**
     * A labelled switch that applies on toggle.
     *
     * @param apply performs the change and returns what the device actually ended
     *   up at. Returning the old value is how a control reports refusal.
     */
    fun switchRow(
        context: Context,
        label: CharSequence,
        summary: CharSequence?,
        checked: Boolean,
        apply: (Boolean) -> Boolean,
    ): View {
        val row = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            // 56dp is the platform's own minimum for a settings row, and this
            // screen is used outdoors and in gloves.
            minimumHeight = dp(context, 56)
            layoutParams = LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT).apply {
                topMargin = dp(context, 4); bottomMargin = dp(context, 4)
            }
        }

        val text = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(0, WRAP_CONTENT, 1f)
        }
        text.addView(TextView(context).apply {
            setText(label)
            setTextAppearance(R.style.TextAppearance_Atlas_Value)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
        })
        if (!summary.isNullOrBlank()) {
            text.addView(TextView(context).apply {
                setText(summary)
                setTextAppearance(R.style.TextAppearance_Atlas_Label)
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
            })
        }
        row.addView(text)

        val toggle = MaterialSwitch(context).apply { isChecked = checked }
        toggle.setOnCheckedChangeListener { view, wanted ->
            val actual = apply(wanted)
            if (actual != wanted) {
                // Snap back without re-entering this listener, so a refusal is
                // one visible correction rather than a loop.
                view.setOnCheckedChangeListener(null)
                view.isChecked = actual
                view.setOnCheckedChangeListener { _, again -> apply(again) }
            }
        }
        row.addView(toggle)
        // The whole row is the target, not just the switch — a 48dp toggle at the
        // end of a wide row is a small target on a tablet held in one hand.
        row.setOnClickListener { toggle.toggle() }
        return row
    }

    /**
     * A labelled slider that applies as it moves.
     *
     * ⚠️ Applies on **change**, not only on release. A brightness slider that did
     * nothing until you let go would be unusable in the dark, which is when it is
     * most likely to be needed.
     */
    fun sliderRow(
        context: Context,
        label: CharSequence,
        min: Int,
        max: Int,
        value: Int,
        format: (Int) -> String,
        apply: (Int) -> Unit,
    ): View {
        val row = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT).apply {
                topMargin = dp(context, 8); bottomMargin = dp(context, 8)
            }
        }

        val header = LinearLayout(context).apply { orientation = LinearLayout.HORIZONTAL }
        header.addView(TextView(context).apply {
            setText(label)
            setTextAppearance(R.style.TextAppearance_Atlas_Value)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
            layoutParams = LinearLayout.LayoutParams(0, WRAP_CONTENT, 1f)
        })
        val readout = TextView(context).apply {
            text = format(value)
            setTextAppearance(R.style.TextAppearance_Atlas_Mono)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
        }
        header.addView(readout)
        row.addView(header)

        row.addView(SeekBar(context).apply {
            this.min = min
            this.max = max
            progress = value.coerceIn(min, max)
            minimumHeight = dp(context, 48)
            setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
                override fun onProgressChanged(bar: SeekBar, at: Int, fromUser: Boolean) {
                    readout.text = format(at)
                    // Only when a person moved it: applying our own initial value
                    // back to the device would overwrite what it already had.
                    if (fromUser) apply(at)
                }
                override fun onStartTrackingTouch(bar: SeekBar) = Unit
                override fun onStopTrackingTouch(bar: SeekBar) = Unit
            })
        })
        return row
    }

    /** A one-line note under a control, for saying why something is unavailable. */
    fun note(context: Context, text: CharSequence): TextView =
        TextView(context).apply {
            setText(text)
            setTextAppearance(R.style.TextAppearance_Atlas_Label)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
            layoutParams = LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT).apply {
                topMargin = dp(context, 2); bottomMargin = dp(context, 8)
            }
        }
}
