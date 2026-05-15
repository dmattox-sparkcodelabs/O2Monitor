package com.o2monitor.relay

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import android.util.Log

/**
 * Application class for O2 Relay.
 * Initializes global singletons and notification channels.
 */
class O2RelayApplication : Application() {

    companion object {
        private const val TAG = "O2RelayApp"

        const val CHANNEL_ID_RELAY_SERVICE = "o2_relay_service"
        const val CHANNEL_NAME_RELAY_SERVICE = "Relay Service"

        lateinit var instance: O2RelayApplication
            private set
    }

    override fun onCreate() {
        super.onCreate()
        instance = this

        Log.i(TAG, "O2 Relay Application starting, version ${BuildConfig.VERSION_NAME}")

        // Set up global uncaught exception handler
        setupExceptionHandler()

        // Create notification channels (required for Android 8.0+)
        createNotificationChannels()

        Log.i(TAG, "O2 Relay Application initialized")
    }

    private fun setupExceptionHandler() {
        val defaultHandler = Thread.getDefaultUncaughtExceptionHandler()

        Thread.setDefaultUncaughtExceptionHandler { thread, throwable ->
            Log.e(TAG, "Uncaught exception in thread ${thread.name}", throwable)

            // Log crash details
            Log.e(TAG, "Stack trace: ${throwable.stackTraceToString()}")

            // Call the default handler to allow crash reporting and process termination
            defaultHandler?.uncaughtException(thread, throwable)
        }
    }

    private fun createNotificationChannels() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val notificationManager = getSystemService(NotificationManager::class.java)

            // Relay service channel - low importance (no sound, persistent notification)
            val relayChannel = NotificationChannel(
                CHANNEL_ID_RELAY_SERVICE,
                CHANNEL_NAME_RELAY_SERVICE,
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Shows relay service status"
                setShowBadge(false)
            }

            notificationManager.createNotificationChannel(relayChannel)
            Log.d(TAG, "Created notification channel: $CHANNEL_ID_RELAY_SERVICE")
        }
    }
}
