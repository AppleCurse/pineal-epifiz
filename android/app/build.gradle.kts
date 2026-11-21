plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.ksp)
}

android {
    // [2026-11-21] namespace, applicationId ile aynı hizada: "com.example.*"
    // şablon artığıydı. Kaynaklar da com.aistudio.pineal.heretic altına
    // taşındı; uygulama kimliği değişmedi (applicationId AYNI kaldı).
    namespace = "com.aistudio.pineal.heretic"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.aistudio.pineal.heretic"
        minSdk = 26
        targetSdk = 35
        // VERSION dosyası tek kaynak: 3.0.0-rc.2 (bkz. VERSION).
        versionCode = 3
        versionName = "3.0.0-rc.2"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    // [2026-11-21] Release imzası GİZLİ ENV VAR'lardan okunur; hiçbir gizli
    // değer depoya girmez. Dört değişkenin hepsi tanımlıysa release derlemesi
    // imzalanır; değilse sessiz unsigned APK yerine AÇIK uyarı loglanır ve
    // imzasız kalır (uydurma imza YOK). CI'da imzalama istenirse
    // PINEAL_RELEASE_* değişkenleri keystore ile birlikte verilmelidir.
    val releaseStoreFile = System.getenv("PINEAL_RELEASE_STORE_FILE")?.takeIf { it.isNotBlank() }
    val releaseStorePassword = System.getenv("PINEAL_RELEASE_STORE_PASSWORD")?.takeIf { it.isNotBlank() }
    val releaseKeyAlias = System.getenv("PINEAL_RELEASE_KEY_ALIAS")?.takeIf { it.isNotBlank() }
    val releaseKeyPassword = System.getenv("PINEAL_RELEASE_KEY_PASSWORD")?.takeIf { it.isNotBlank() }
    val releaseSigningReady = releaseStoreFile != null && releaseStorePassword != null &&
        releaseKeyAlias != null && releaseKeyPassword != null
    if (!releaseSigningReady) {
        logger.lifecycle(
            "[pineal] PINEAL_RELEASE_STORE_FILE/STORE_PASSWORD/KEY_ALIAS/KEY_PASSWORD " +
                "tanımlı değil — release build İMZASIZ üretilecek."
        )
    }

    signingConfigs {
        getByName("debug") {
            if (file("${rootDir}/debug.keystore").exists()) {
                storeFile = file("${rootDir}/debug.keystore")
                storePassword = "android"
                keyAlias = "androiddebugkey"
                keyPassword = "android"
            }
        }
        if (releaseSigningReady) {
            create("release") {
                storeFile = file(releaseStoreFile!!)
                storePassword = releaseStorePassword
                keyAlias = releaseKeyAlias
                keyPassword = releaseKeyPassword
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            if (releaseSigningReady) {
                signingConfig = signingConfigs.getByName("release")
            }
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
        debug {
            signingConfig = signingConfigs.getByName("debug")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    lint {
        textReport = true
        textOutput = layout.buildDirectory.file("reports/lint-results-debug.txt").get().asFile
    }
}

// Kotlin compiler diagnostics are normally only present in the raw Actions log.
// Capture them so the root build-failure hook can publish actionable annotations.
val kotlinCiDiagnostics = layout.buildDirectory.file("reports/kotlin-compiler-ci.log")
tasks.withType<org.jetbrains.kotlin.gradle.tasks.KotlinCompile>().configureEach {
    doFirst {
        kotlinCiDiagnostics.get().asFile.apply {
            parentFile.mkdirs()
            writeText("")
        }
    }
    val listener = org.gradle.api.logging.StandardOutputListener { output ->
        kotlinCiDiagnostics.get().asFile.appendText(output.toString())
    }
    logging.addStandardOutputListener(listener)
    logging.addStandardErrorListener(listener)
}

// Keep lint fail-closed while surfacing each concrete error as a GitHub check
// annotation. This avoids a generic exit-code-only failure on CI.
val emitLintErrors by tasks.registering {
    doLast {
        val report = layout.buildDirectory.file("reports/lint-results-debug.txt").get().asFile
        if (report.exists()) {
            val reportText = report.readText()
            reportText.lineSequence()
                .filter { it.contains(": Error:") }
                .forEach { println("::error title=Android lint::${it.replace("%", "%25")}") }
            System.getenv("GITHUB_STEP_SUMMARY")?.let { summaryPath ->
                file(summaryPath).appendText(
                    "\n## Android lint report\n\n```text\n${reportText.take(60000)}\n```\n"
                )
            }
        }
    }
}

tasks.configureEach {
    if (name == "lintDebug") {
        finalizedBy(emitLintErrors)
    }
}

dependencies {
    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.activity.compose)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.ui)
    implementation(libs.androidx.ui.graphics)
    implementation(libs.androidx.ui.tooling.preview)
    implementation(libs.androidx.material3)
    implementation(libs.androidx.material.icons.extended)
    implementation(libs.androidx.navigation.compose)

    implementation(libs.androidx.room.runtime)
    implementation(libs.androidx.room.ktx)
    ksp(libs.androidx.room.compiler)

    implementation(libs.kotlinx.serialization.json)
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.okhttp)
    implementation(libs.retrofit)
    implementation(libs.retrofit.converter.serialization)
}
