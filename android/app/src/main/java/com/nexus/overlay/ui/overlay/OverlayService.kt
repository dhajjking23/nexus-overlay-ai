package com.nexus.overlay.ui.overlay

import android.app.*
import android.app.ServiceInfo
import android.content.Intent
import android.graphics.PixelFormat
import android.os.Build
import android.os.IBinder
import android.view.*
import android.widget.FrameLayout
import androidx.compose.runtime.*
import androidx.compose.ui.platform.ComposeView
import androidx.core.app.NotificationCompat
import com.nexus.overlay.NexusOverlayApp
import com.nexus.overlay.R
import com.nexus.overlay.data.SignalStore
import com.nexus.overlay.ui.theme.NexusTheme
import com.nexus.overlay.viewmodel.OverlayMode
import kotlinx.coroutines.*

/**
 * Foreground service that manages the floating overlay window.
 * Supports Compact, Standard, and Pro modes with dragging and resizing.
 */
class OverlayService : Service() {

    private var overlayView: View? = null
    private var windowManager: WindowManager? = null
    private var layoutParams: WindowManager.LayoutParams? = null
    private var signalStore: SignalStore? = null
    private var currentMode: OverlayMode = OverlayMode.STANDARD
    private var currentOpacity: Float = 0.85f

    // Drag state
    private var initialX = 0
    private var initialY = 0
    private var initialTouchX = 0f
    private var initialTouchY = 0f
    private var isDragging = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        windowManager = getSystemService(WINDOW_SERVICE) as WindowManager
        signalStore = (application as NexusOverlayApp).signalStore
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> {
                currentMode = try {
                    OverlayMode.valueOf(intent.getStringExtra(EXTRA_MODE) ?: "STANDARD")
                } catch (e: Exception) { OverlayMode.STANDARD }
                currentOpacity = intent.getFloatExtra(EXTRA_OPACITY, 0.85f)
                startForegroundWithNotification()
                showOverlay()
            }
            ACTION_STOP -> {
                hideOverlay()
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf()
            }
            ACTION_UPDATE_MODE -> {
                currentMode = try {
                    OverlayMode.valueOf(intent.getStringExtra(EXTRA_MODE) ?: "STANDARD")
                } catch (e: Exception) { OverlayMode.STANDARD }
                recreateOverlay()
            }
            ACTION_UPDATE_OPACITY -> {
                currentOpacity = intent.getFloatExtra(EXTRA_OPACITY, 0.85f)
                updateOpacity()
            }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        hideOverlay()
        super.onDestroy()
    }

    private fun startForegroundWithNotification() {
        val channelId = NexusOverlayApp.CHANNEL_OVERLAY
        val notification = NotificationCompat.Builder(this, channelId)
            .setContentTitle("Nexus Overlay Active")
            .setContentText("Monitoring trading signals")
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .build()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    private fun showOverlay() {
        if (overlayView != null) return

        val context = this
        val modeConfig = getModeConfig(currentMode)

        layoutParams = WindowManager.LayoutParams(
            modeConfig.width,
            modeConfig.height,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                    WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL or
                    WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = 20
            y = 100
        }

        // Create Compose overlay view
        val composeView = ComposeView(context).apply {
            setContent {
                NexusTheme {
                    OverlayContent(
                        mode = currentMode,
                        signalStore = signalStore!!,
                        opacity = currentOpacity,
                        onClose = { stopSelf() },
                        onModeSwitch = { newMode ->
                            currentMode = newMode
                            recreateOverlay()
                        }
                    )
                }
            }
        }

        // Set up drag handling
        composeView.setOnTouchListener { _, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    initialX = layoutParams?.x ?: 0
                    initialY = layoutParams?.y ?: 0
                    initialTouchX = event.rawX
                    initialTouchY = event.rawY
                    isDragging = false
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = event.rawX - initialTouchX
                    val dy = event.rawY - initialTouchY
                    if (Math.abs(dx) > 5 || Math.abs(dy) > 5) {
                        isDragging = true
                    }
                    if (isDragging) {
                        layoutParams?.x = initialX + dx.toInt()
                        layoutParams?.y = initialY + dy.toInt()
                        try {
                            windowManager?.updateViewLayout(overlayView, layoutParams)
                        } catch (_: Exception) {}
                    }
                    true
                }
                MotionEvent.ACTION_UP -> {
                    true
                }
                else -> false
            }
        }

        overlayView = composeView
        try {
            windowManager?.addView(overlayView, layoutParams)
        } catch (e: Exception) {
            // Permission not granted or other issue
            overlayView = null
        }
    }

    private fun hideOverlay() {
        overlayView?.let { view ->
            try {
                windowManager?.removeView(view)
            } catch (_: Exception) {}
        }
        overlayView = null
    }

    private fun recreateOverlay() {
        hideOverlay()
        showOverlay()
    }

    private fun updateOpacity() {
        overlayView?.alpha = currentOpacity
    }

    private fun getModeConfig(mode: OverlayMode): ModeConfig {
        return when (mode) {
            OverlayMode.COMPACT -> ModeConfig(
                width = 320,
                height = 80,
                name = "Compact"
            )
            OverlayMode.STANDARD -> ModeConfig(
                width = 340,
                height = 280,
                name = "Standard"
            )
            OverlayMode.PRO -> ModeConfig(
                width = 400,
                height = 500,
                name = "Pro"
            )
        }
    }

    data class ModeConfig(val width: Int, val height: Int, val name: String)

    companion object {
        const val ACTION_START = "com.nexus.overlay.START"
        const val ACTION_STOP = "com.nexus.overlay.STOP"
        const val ACTION_UPDATE_MODE = "com.nexus.overlay.UPDATE_MODE"
        const val ACTION_UPDATE_OPACITY = "com.nexus.overlay.UPDATE_OPACITY"
        const val EXTRA_MODE = "overlay_mode"
        const val EXTRA_OPACITY = "overlay_opacity"
        private const val NOTIFICATION_ID = 1001
    }
}
