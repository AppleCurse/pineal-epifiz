plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.ksp)
}

val canonicalVersion = rootProject.file("../VERSION").readText().trim()
require(canonicalVersion.isNotEmpty()) { "Repository VERSION file is empty; refusing to build an unidentified Android app." }

android {
    namespace = "com.example.pineal"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.aistudio.pineal.heretic"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = canonicalVersion

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
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
    }

    buildTypes {
        release {
            isMinifyEnabled = false
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
