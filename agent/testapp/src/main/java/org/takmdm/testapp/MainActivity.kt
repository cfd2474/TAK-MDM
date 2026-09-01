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

package org.takmdm.testapp

import android.os.Bundle
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

/** Shows its own version, so an upgrade is confirmable by looking at the device. */
class MainActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(
            TextView(this).apply {
                text = getString(
                    R.string.installed_version,
                    BuildConfig.VERSION_NAME,
                    BuildConfig.VERSION_CODE
                )
                textSize = 22f
                setPadding(48, 96, 48, 48)
            }
        )
    }
}
