plugins {
    id("com.android.application")
}

android {
    namespace = "com.pcontrol.app"
    compileSdk = 37

    defaultConfig {
        applicationId = "com.pcontrol.app"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "1.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            // APK pessoal: assina com a chave de debug pra instalar direto no celular.
            signingConfig = signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
