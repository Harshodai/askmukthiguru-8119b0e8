# ==============================================================================
# ProGuard / R8 Rules for AskMukthiGuru Android Application
# ==============================================================================

# --- General Reflection & Stack Trace Preservation ---
-keepattributes SourceFile,LineNumberTable
-keepattributes *Annotation*
-keepattributes Signature
-keepattributes InnerClasses,EnclosingMethod

# --- Capacitor Core & Plugin Architecture ---
-keep class com.getcapacitor.** { *; }
-keep public class * extends com.getcapacitor.Plugin
-keepclassmembers class * {
    @com.getcapacitor.annotation.CapacitorPlugin <methods>;
}
-keepclassmembers class * {
    @com.getcapacitor.PluginMethod <methods>;
}
-keep class **.R$* { <fields>; }
-dontwarn com.getcapacitor.**

# --- WebKit & JavaScript Interface Bridge ---
# Critical for WebView <-> Native JavaScript bridge communication
-keepattributes JavascriptInterface
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}
-keepclassmembers class * {
    @androidx.webkit.JavascriptInterface <methods>;
}
-keep class android.webkit.** { *; }
-keep class androidx.webkit.** { *; }
-dontwarn androidx.webkit.**

# --- Cordova Plugin Compatibility ---
-keep public class * extends org.apache.cordova.CordovaPlugin
-keep class org.apache.cordova.** { *; }
-dontwarn org.apache.cordova.**

# --- AndroidX Support Libraries ---
-keep class androidx.appcompat.** { *; }
-keep class androidx.coordinatorlayout.** { *; }
-keep class androidx.core.** { *; }
-keep class androidx.core.splashscreen.** { *; }
-dontwarn androidx.**

# --- Firebase & Google Play Services ---
-keep class com.google.firebase.** { *; }
-dontwarn com.google.firebase.**
-keep class com.google.android.gms.** { *; }
-dontwarn com.google.android.gms.**

# --- Build Annotations & Warning Suppression ---
-dontwarn com.google.errorprone.annotations.**
-dontwarn javax.annotation.**
-dontwarn org.checkerframework.**
