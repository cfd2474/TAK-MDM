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

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

/*
 * A deliberately trivial app, used to prove the install pipeline on hardware.
 *
 * Single APK on purpose: no ABI or density splits, no OBB. The point is to
 * exercise PackageInstaller by itself, so that a failure has one candidate cause
 * rather than three. ATAK - base + split + OBB - is the escalation after this
 * works.
 *
 * It shows its own version on screen so an upgrade can be confirmed by looking at
 * the tablet, not only by trusting a version code the server reported.
 */
android {
    namespace = "org.takmdm.testapp"
    compileSdk = 36

    defaultConfig {
        applicationId = "org.takmdm.testapp"
        minSdk = 33
        // Well above the API 24 floor Android 16 enforces; below it every install
        // fails with INSTALL_FAILED_DEPRECATED_SDK_VERSION whatever the source.
        targetSdk = 36
        versionCode = 2
        versionName = "2.0"
    }

    // No splits. An ABI or density split would turn one install into several
    // parts and defeat the isolation this module exists for.
    splits {
        abi { isEnable = false }
        density { isEnable = false }
    }

    buildTypes {
        release { isMinifyEnabled = false }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions { jvmTarget = "17" }
    buildFeatures { buildConfig = true }
}

dependencies {
    implementation("androidx.appcompat:appcompat:1.7.0")
}
