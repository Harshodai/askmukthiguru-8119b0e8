# Capacitor
-keep class com.getcapacitor.** { *; }
-keep class **.R$* { <fields>; }
-keepclassmembers class * {
    @com.getcapacitor.annotation.CapacitorPlugin <methods>;
}
-keepclassmembers class * {
    @androidx.webkit.JavascriptInterface <methods>;
}
# Firebase
-keep class com.google.firebase.** { *; }
-dontwarn com.google.firebase.**