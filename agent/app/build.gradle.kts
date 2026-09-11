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

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

/**
 * Release signing, loaded from `agent/keystore.properties` (gitignored) or from
 * the environment for CI.
 *
 * Kept out of this file on purpose. The signing key *is* the fleet's identity:
 * Android refuses to install a build whose signature differs from the installed
 * one, and the agent-update channel cannot work around that — a key change means
 * a manual re-install on every device that ever ran a build signed with the old
 * one. So the key is worth protecting like the device CA, not like a build flag.
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
    namespace = "com.taksolutions.atlasmdm"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.taksolutions.atlasmdm"
        // 33 so java.security Ed25519 comes from the platform provider instead of a
        // bundled BouncyCastle. Every device in this fleet is on Android 16.
        minSdk = 33
        targetSdk = 36
        // Bump on every build you intend to upload: the server refuses a duplicate
        // versionCode, and Android refuses to install a downgrade.
        versionCode = 107
        versionName = "0.62.0"
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
            // Null when no keystore is configured. The task below turns that into
            // a failed build rather than an unsigned APK.
            signingConfig = signingConfigs.findByName("release")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    testOptions {
        unitTests {
            // android.util.Log and friends are stubs that throw in a JVM unit test.
            // The command dispatcher and the redactor are ordinary logic worth
            // testing off-device, and both log; without this they fail on the
            // logging rather than on anything they are meant to verify.
            isReturnDefaultValues = true
        }
    }

    buildFeatures {
        viewBinding = true
        // AGP 8 no longer generates BuildConfig unless asked. DebugConfigReceiver
        // gates itself on BuildConfig.DEBUG, so this is load-bearing rather than
        // convenience.
        buildConfig = true
    }

    packaging {
        resources.excludes += setOf(
            "META-INF/*.kotlin_module",
            // The three BouncyCastle artifacts each ship an identical multi-release
            // OSGI manifest, which the merger refuses to resolve on its own.
            "META-INF/versions/9/OSGI-INF/MANIFEST.MF",
            "META-INF/DEPENDENCIES",
            "META-INF/LICENSE*",
            "META-INF/NOTICE*"
        )
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.recyclerview:recyclerview:1.3.2")
    implementation("androidx.lifecycle:lifecycle-service:2.8.7")
    implementation("androidx.work:work-runtime-ktx:2.10.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.json:json:20240303")

    // PKCS#10 certificate signing requests. Android has no public CSR builder, and
    // hand-rolling DER for a security-critical structure is not worth the saved
    // megabyte. Android's own copy is namespaced com.android.org.bouncycastle, so
    // these do not collide.
    implementation("org.bouncycastle:bcpkix-jdk18on:1.79")
    implementation("org.bouncycastle:bcprov-jdk18on:1.79")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
}

/**
 * Refuse to build an unsigned release.
 *
 * AGP's default is to produce `app-release-unsigned.apk` and say nothing. That
 * artifact cannot be installed, and it looks exactly like a real build until a
 * device rejects it — which, for a fleet agent, is the slowest possible way to
 * find out. Failing here costs seconds instead.
 */
tasks.matching { it.name == "packageRelease" || it.name == "assembleRelease" }.configureEach {
    doFirst {
        if (signingProps == null) {
            throw GradleException(
                "Release signing is not configured. Copy agent/keystore.properties.example " +
                    "to agent/keystore.properties and fill it in, or set ATLAS_KEYSTORE_FILE / " +
                    "ATLAS_KEYSTORE_PASSWORD / ATLAS_KEY_ALIAS / ATLAS_KEY_PASSWORD."
            )
        }
    }
}
