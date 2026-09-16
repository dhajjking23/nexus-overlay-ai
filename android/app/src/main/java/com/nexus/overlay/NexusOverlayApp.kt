package com.nexus.overlay

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import com.nexus.overlay.data.SettingsManager
import com.nexus.overlay.data.SignalStore
import com.nexus.overlay.data.WebSocketClient
import com.nexus.overlay.viewmodel.MainViewModel

/**
 * Application class for Nexus Overlay AI.
 * Initializes shared components and manages app lifecycle.
 */
class NexusOverlayApp : Application() {

    lateinit var signalStore: SignalStore
        private set

    lateinit var webSocketClient: WebSocketClient
        private set

    lateinit var viewModel: MainViewModel
        private set

    lateinit var settingsManager: SettingsManager
        private set

    override fun onCreate() {
        super.onCreate()
        instance = this

        // Initialize settings (SharedPreferences)
        settingsManager = SettingsManager(this)

        // Initialize shared dependencies with saved settings
        signalStore = SignalStore()
        webSocketClient = WebSocketClient(
            signalStore = signalStore,
            authToken = settingsManager.authToken
        )
        viewModel = MainViewModel(signalStore, webSocketClient, settingsManager)

        // Create notification channels
        createNotificationChannels()
    }

    private fun createNotificationChannels() {
        val manager = getSystemService(NotificationManager::class.java) ?: return

        val overlayChannel = NotificationChannel(
            CHANNEL_OVERLAY,
            "Overlay Service",
            NotificationManager.IMPORTANCE_LOW
        ).apply {
            description = "Keeps the overlay running in the background"
            setShowBadge(false)
        }

        val alertChannel = NotificationChannel(
            CHANNEL_ALERTS,
            "Signal Alerts",
            NotificationManager.IMPORTANCE_HIGH
        ).apply {
            description = "Trading signal notifications"
            enableVibration(true)
        }

        manager.createNotificationChannels(listOf(overlayChannel, alertChannel))
    }

    companion object {
        const val CHANNEL_OVERLAY = "overlay_service"
        const val CHANNEL_ALERTS = "signal_alerts"

        lateinit var instance: NexusOverlayApp
            private set
    }
}
