package com.nexus.overlay.ui.overlay

import android.app.*
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.PixelFormat
import android.os.Build
import android.os.IBinder
import android.provider.Settings
import android.util.DisplayMetrics
import android.util.Log
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
 *
 * Handles:
 * - Overlay permission loss gracefully (Section XL/39)
 * - Screen rotation, different DPI, notch, navigation bar (Section G)
 * - Android 14/15 foreground service requirements (Section 40)
 * - Stale signal protection awareness (Section 41)
 */
class OverlayService : Service() {

    private var overlayView: View? = null
    private var windowManager: WindowManager? = null
    private var layoutParams: WindowManager.LayoutParams? = null
    private var signalStore: SignalStore? = null
    private var currentMode: OverlayMode = OverlayMode.STANDARD
    private var currentOpacity: Float = 0.85f
    private var hasOverlayPermission = false

    // Drag state
    private var initialX = 0
    private var initialY = 0
    private var initialTouchX = 0f
    private var initialTouchY = 0f
    private var isDragging = false

    // Freshness recalculation job
    private var freshnessJob: Job? = null
    private val serviceScope = CoroutineScope(Dispatchers.Main + SupervisorJob())

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
                startFreshnessRecalculation()
            }
            ACTION_STOP -> {
                stopFreshnessRecalculation()
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
        stopFreshnessRecalculation()
        hideOverlay()
        serviceScope.cancel()
        super.onDestroy()
    }

    /**
     * Recalculate signal freshness every second for the overlay.
     */
    private fun startFreshnessRecalculation() {
        stopFreshnessRecalculation()
        freshnessJob = serviceScope.launch {
            while (isActive) {
                delay(1000)
                signalStore?.recalculateFreshness()
            }
        }
    }

    private fun stopFreshnessRecalculation() {
        freshnessJob?.cancel()
        freshnessJob = null
    }

    /**
     * Section XL/39: Handle foreground service for Android 14+.
     * Properly declares foregroundServiceType for specialUse.
     */
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

        // Android 14 (UPSIDE_DOWN_CAKE) requires explicit foreground service type
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(
                NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE
            )
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    /**
     * Show the overlay window with proper layout params.
     * Handles screen dimensions, notch, navigation bar.
     * Section XL/39: Overlay is visualization layer, not chart source of truth.
     */
    private fun showOverlay() {
        if (overlayView != null) return

        // Check overlay permission first (Section XL: graceful permission loss)
        if (!Settings.canDrawOverlays(this)) {
            Log.w(TAG, "Overlay permission not granted — cannot show overlay")
            hasOverlayPermission = false
            // Notify the app about permission loss
            sendPermissionLossBroadcast()
            return
        }
        hasOverlayPermission = true

        val context = this
        val modeConfig = getModeConfig(currentMode)

        // Get display metrics for proper sizing across DPI/screen sizes
        val displayMetrics = DisplayMetrics()
        @Suppress("DEPRECATION")
        windowManager?.defaultDisplay?.getMetrics(displayMetrics)

        // Get safe area insets for notch and navigation bar
        val stableInsets = getStableInsets()

        // Calculate overlay dimensions considering DPI
        val overlayWidth = modeConfig.width.dpToPx(displayMetrics.density)
        val overlayHeight = modeConfig.height.dpToPx(displayMetrics.density)

        // Initial position: top-right area, accounting for status bar/notch
        val initialPosX = 20
        val initialPosY = stableInsets.top + 20

        layoutParams = WindowManager.LayoutParams(
            overlayWidth,
            overlayHeight,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            // Section XL/39: FLAG_NOT_FOCUSABLE ensures other apps can still be used
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                    WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL or
                    WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = initialPosX
            y = initialPosY
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

        // Set up drag handling with boundary clamping
        composeView.setOnTouchListener { _, event ->
            // If overlay permission was revoked, stop dragging
            if (!Settings.canDrawOverlays(this@OverlayService)) {
                hasOverlayPermission = false
                sendPermissionLossBroadcast()
                return@setOnTouchListener false
            }

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
                        // Calculate new position
                        val newX = initialX + dx.toInt()
                        val newY = initialY + dy.toInt()

                        // Clamp to screen bounds
                        val screenWidth = displayMetrics.widthPixels
                        val screenHeight = displayMetrics.heightPixels
                        val clampedX = newX.coerceIn(0, screenWidth - overlayWidth)
                        val clampedY = newY.coerceIn(
                            stableInsets.top,
                            screenHeight - overlayHeight - stableInsets.bottom
                        )

                        layoutParams?.x = clampedX
                        layoutParams?.y = clampedY
                        try {
                            windowManager?.updateViewLayout(overlayView, layoutParams)
                        } catch (e: WindowManager.BadTokenException) {
                            // Overlay was removed by system
                            Log.w(TAG, "BadTokenException during drag — overlay lost")
                            hasOverlayPermission = false
                            sendPermissionLossBroadcast()
                        } catch (e: Exception) {
                            Log.w(TAG, "Failed to update overlay layout: ${e.message}")
                        }
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
        } catch (e: SecurityException) {
            // Permission not granted
            Log.e(TAG, "SecurityException: overlay permission not granted")
            overlayView = null
            hasOverlayPermission = false
            sendPermissionLossBroadcast()
        } catch (e: WindowManager.BadTokenException) {
            Log.e(TAG, "BadTokenException: overlay window token invalid")
            overlayView = null
            hasOverlayPermission = false
            sendPermissionLossBroadcast()
        } catch (e: Exception) {
            Log.e(TAG, "Failed to add overlay view: ${e.message}")
            overlayView = null
        }
    }

    private fun hideOverlay() {
        overlayView?.let { view ->
            try {
                windowManager?.removeView(view)
            } catch (e: IllegalArgumentException) {
                // View was already removed
                Log.d(TAG, "Overlay view already removed")
            } catch (e: Exception) {
                Log.w(TAG, "Failed to remove overlay view: ${e.message}")
            }
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

    /**
     * Get stable insets for notch, status bar, navigation bar.
     * This ensures overlay is placed within the usable display area.
     */
    private fun getStableInsets(): Insets {
        val statusBarHeight = getStatusBarHeight()
        val navBarHeight = getNavigationBarHeight()
        return Insets(top = statusBarHeight, bottom = navBarHeight)
    }

    private fun getStatusBarHeight(): Int {
        val resourceId = resources.getIdentifier("status_bar_height", "dimen", "android")
        return if (resourceId > 0) resources.getDimensionPixelSize(resourceId) else 0
    }

    private fun getNavigationBarHeight(): Int {
        val resourceId = resources.getIdentifier("navigation_bar_height", "dimen", "android")
        return if (resourceId > 0) resources.getDimensionPixelSize(resourceId) else 0
    }

    /**
     * Send broadcast to notify app about permission loss.
     */
    private fun sendPermissionLossBroadcast() {
        val intent = Intent(ACTION_PERMISSION_LOST)
        sendBroadcast(intent)
        // Stop the service gracefully
        serviceScope.launch {
            delay(500)
            hideOverlay()
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
        }
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

    private data class ModeConfig(val width: Int, val height: Int, val name: String)

    private data class Insets(val top: Int, val bottom: Int)

    /**
     * Convert dp to px for proper sizing across different DPIs.
     */
    private fun Int.dpToPx(density: Float): Int = (this * density + 0.5f).toInt()

    companion object {
        private const val TAG = "OverlayService"
        const val ACTION_START = "com.nexus.overlay.START"
        const val ACTION_STOP = "com.nexus.overlay.STOP"
        const val ACTION_UPDATE_MODE = "com.nexus.overlay.UPDATE_MODE"
        const val ACTION_UPDATE_OPACITY = "com.nexus.overlay.UPDATE_OPACITY"
        const val ACTION_PERMISSION_LOST = "com.nexus.overlay.PERMISSION_LOST"
        const val EXTRA_MODE = "overlay_mode"
        const val EXTRA_OPACITY = "overlay_opacity"
        private const val NOTIFICATION_ID = 1001
    }
}
