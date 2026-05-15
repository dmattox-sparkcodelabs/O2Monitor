# Add project specific ProGuard rules here.
# Keep kotlinx.serialization
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.AnnotationsKt
-keepclassmembers class kotlinx.serialization.json.** {
    *** Companion;
}
-keepclasseswithmembers class kotlinx.serialization.json.** {
    kotlinx.serialization.KSerializer serializer(...);
}
-keep,includedescriptorclasses class com.o2monitor.app.**$$serializer { *; }
-keepclassmembers class com.o2monitor.app.** {
    *** Companion;
}
-keepclasseswithmembers class com.o2monitor.app.** {
    kotlinx.serialization.KSerializer serializer(...);
}
