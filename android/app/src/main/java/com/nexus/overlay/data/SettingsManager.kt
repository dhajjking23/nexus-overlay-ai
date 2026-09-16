package com.nexus.overlay.data

import android.content.Context
import android.content.SharedPreferences
import com.nexus.overlay.viewmodel.OverlayMode

/**
 * Persists all user settings via SharedPreferences.
 * Loaded once at app startup, saved on every change.
 */
class SettingsManager(context: Context) {

    private val prefs: SharedPreferences =
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    // --- Server ---
    var serverHost: String
        get() = prefs.getString(KEY_HOST, DEFAULT_HOST) ?: DEFAULT_HOST
        set(value) = prefs.edit().putString(KEY_HOST, value).apply()

    var serverPort: Int
        get() = prefs.getInt(KEY_PORT, DEFAULT_PORT)
        set(value) = prefs.edit().putInt(KEY_PORT, value).apply()

    var authToken: String
        get() = prefs.getString(KEY_AUTH_TOKEN, DEFAULT_AUTH_TOKEN) ?: DEFAULT_AUTH_TOKEN
        set(value) = prefs.edit().putString(KEY_AUTH_TOKEN, value).apply()

    // --- Overlay ---
    var overlayMode: OverlayMode
        get() = try {
            OverlayMode.valueOf(prefs.getString(KEY_OVERLAY_MODE, OverlayMode.STANDARD.name)!!)
        } catch (_: Exception) {
            OverlayMode.STANDARD
        }
        set(value) = prefs.edit().putString(KEY_OVERLAY_MODE, value.name).apply()

    var overlayOpacity: Float
        get() = prefs.getFloat(KEY_OVERLAY_OPACITY, DEFAULT_OPACITY)
        set(value) = prefs.edit().putFloat(KEY_OVERLAY_OPACITY, value).apply()

    // --- Behavior ---
    var autoConnect: Boolean
        get() = prefs.getBoolean(KEY_AUTO_CONNECT, true)
        set(value) = prefs.edit().putBoolean(KEY_AUTO_CONNECT, value).apply()

    var alertOnSignal: Boolean
        get() = prefs.getBoolean(KEY_ALERT_ON_SIGNAL, true)
        set(value) = prefs.edit().putBoolean(KEY_ALERT_ON_SIGNAL, value).apply()

    var alertOnSLHit: Boolean
        get() = prefs.getBoolean(KEY_ALERT_ON_SL_HIT, false)
        set(value) = prefs.edit().putBoolean(KEY_ALERT_ON_SL_HIT, value).apply()

    /** Save entire UiState snapshot in one call. */
    fun saveAll(
        host: String,
        port: Int,
        token: String,
        mode: OverlayMode,
        opacity: Float,
        autoConnect: Boolean,
        alertSignal: Boolean,
        alertSL: Boolean
    ) {
        prefs.edit()
            .putString(KEY_HOST, host)
            .putInt(KEY_PORT, port)
            .putString(KEY_AUTH_TOKEN, token)
            .putString(KEY_OVERLAY_MODE, mode.name)
            .putFloat(KEY_OVERLAY_OPACITY, opacity)
            .putBoolean(KEY_AUTO_CONNECT, autoConnect)
            .putBoolean(KEY_ALERT_ON_SIGNAL, alertSignal)
            .putBoolean(KEY_ALERT_ON_SL_HIT, alertSL)
            .apply()
    }

    companion object {
        private const val PREFS_NAME = "nexus_overlay_settings"

        private const val KEY_HOST = "server_host"
        private const val KEY_PORT = "server_port"
        private const val KEY_AUTH_TOKEN = "auth_token"
        private const val KEY_OVERLAY_MODE = "overlay_mode"
        private const val KEY_OVERLAY_OPACITY = "overlay_opacity"
        private const val KEY_AUTO_CONNECT = "auto_connect"
        private const val KEY_ALERT_ON_SIGNAL = "alert_on_signal"
        private const val KEY_ALERT_ON_SL_HIT = "alert_on_sl_hit"

        // Defaults — pre-filled so user doesn't have to type everything
        const val DEFAULT_HOST = "161.118.225.156"
        const val DEFAULT_PORT = 8765
        const val DEFAULT_AUTH_TOKEN = "65308a15c52a8af73a4879a2d10222678913e972225294a015a164ef80947181"
        const val DEFAULT_OPACITY = 0.85f
    }
}
