import java.util.Properties
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

val localProperties = Properties().apply {
    val file = rootProject.file("local.properties")
    if (file.exists()) file.inputStream().use { load(it) }
}

fun secret(property: String, env: String): String? =
    localProperties.getProperty(property) ?: System.getenv(env)

android {
    namespace = "com.cookmarks.app"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.cookmarks.app"
        minSdk = 34
        targetSdk = 36
        versionCode = 1
        versionName = "1.0"
        val baseUrl = providers.gradleProperty("cookmarksBaseUrl").getOrElse("http://100.76.187.39:8789")
        buildConfigField("String", "BASE_URL", "\"$baseUrl\"")
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    signingConfigs {
        create("release") {
            secret("cookmarks.keystore", "COOKMARKS_KEYSTORE")?.let { path ->
                storeFile = file(path)
                storePassword = requireNotNull(secret("cookmarks.keystore.password", "COOKMARKS_KEYSTORE_PASSWORD")) {
                    "cookmarks.keystore is set but cookmarks.keystore.password is missing"
                }
                keyAlias = secret("cookmarks.key.alias", "COOKMARKS_KEY_ALIAS") ?: "cookmarks"
                keyPassword = requireNotNull(secret("cookmarks.key.password", "COOKMARKS_KEY_PASSWORD")) {
                    "cookmarks.keystore is set but cookmarks.key.password is missing"
                }
            }
        }
    }

    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("release").takeIf { it.storeFile != null }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}

dependencies {
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.material3)
    implementation(libs.compose.ui.tooling.preview)
    debugImplementation(libs.compose.ui.tooling)
    implementation(libs.activity.compose)
    implementation(libs.navigation.compose)
    implementation(libs.serialization.json)
    implementation(libs.retrofit)
    implementation(libs.retrofit.serialization)
    implementation(libs.okhttp)
    implementation(libs.coil.compose)
    testImplementation(libs.junit)
}
