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

import java.util.Properties

/*
 * The ATLAS kiosk home screen (W68).
 *
 * A separate application, not a screen inside the agent, and that is the whole
 * design. An activity carrying `category.HOME` is offered as a home app to every
 * device that installs the build, so putting one in the agent would change what
 * the agent *is* on devices that never asked for a kiosk. Here it ships only
 * where a policy asks for it, and removing that policy removes its claim on HOME
 * - which keeps "unassign the profile" as a recovery that needs no physical
 * access. See docs/DECISION-atlas-launcher.md.
 *
 * It holds no policy of its own. Everything it shows arrives as managed
 * configuration from the Device Owner, so this app has no server, no credentials
 * and nothing to enrol.
 */

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

/*
 * The agent's keystore, deliberately.
 *
 * Not because anything requires a shared signature - the config channel is
 * managed configuration, which needs none - but because these two artifacts are
 * one product with one update channel, and a second key would be a second thing
 * to lose. Android's no-downgrade and no-resign rules apply here exactly as they
 * do to the agent: a key change means a manual re-install on every device.
 */
val signingProps: Properties? = run {
    val file = rootProject.file("keystore.properties")
    when {
        file.exists() -> Properties().apply { file.inputStream().use(::load) }
        System.getenv("ATLAS_KEYSTORE_FILE") != null -> Properties().apply {
            setProperty("storeFile", System.getenv("ATLAS_KEYSTORE_FILE"))
            setProperty("storePassword", System.getenv("ATLAS_KEYSTORE_PASSWORD") ?: "")
            setProperty("keyAlias", System.getenv("ATLAS_KEY_ALIAS") ?: "key0")
            setProperty("keyPassword", System.getenv("ATLAS_KEY_PASSWORD") ?: "")
        }
        else -> null
    }
}

android {
    namespace = "com.taksolutions.atlaslauncher"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.taksolutions.atlaslauncher"
        minSdk = 33
        targetSdk = 36
        // Bump on every build you intend to upload: the server refuses a duplicate
        // versionCode, and Android refuses to install a downgrade.
        versionCode = 4
        versionName = "0.4.0"
    }

    // No splits, for the same reason the agent has none: the Device Owner install
    // path is simplest with one file, and a density split would put the launcher's
    // icons in a part that has to be installed alongside.
    splits {
        abi { isEnable = false }
        density { isEnable = false }
    }

    signingConfigs {
        signingProps?.let { props ->
            create("release") {
                storeFile = file(props.getProperty("storeFile"))
                storePassword = props.getProperty("storePassword")
                keyAlias = props.getProperty("keyAlias")
                keyPassword = props.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.findByName("release")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions { jvmTarget = "17" }
    buildFeatures { buildConfig = true }

    testOptions {
        unitTests { isReturnDefaultValues = true }
    }
}

dependencies {
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.recyclerview:recyclerview:1.3.2")
    testImplementation("junit:junit:4.13.2")
}
