# Proguard rules for Nexus Overlay AI

# OkHttp
-dontwarn okhttp3.**
-dontwarn okio.**
-keepnames class okhttp3.internal.publicsuffix.PublicSuffixDatabase

# Compose
-dontwarn androidx.compose.**

# Keep WebSocket classes
-keep class com.nexus.overlay.data.** { *; }

# Keep ViewModel
-keep class com.nexus.overlay.viewmodel.** { *; }
