package com.nexus.overlay.viewmodel

import android.app.Application
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.nexus.overlay.NexusOverlayApp
import com.nexus.overlay.data.*
import com.nexus.overlay.ui.overlay.OverlayService
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch

/**
 * Main ViewModel managing all UI state and user actions.
 * Bridges SignalStore data to UI composables.
 * Loads/saves settings via SettingsManager (SharedPreferences).
 *
 * Tracks signal freshness, AI status, system status for the
 * hardened Android overlay (Phase G).
 */
class MainViewModel(
    private val signalStore: SignalStore,
    private val webSocketClient: WebSocketClient,
    private val settingsManager: SettingsManager
) : AndroidViewModel(NexusOverlayApp.instance) {

    // --- UI State (loaded from saved settings) ---
    private val _uiState = MutableStateFlow(loadInitialState())
    val uiState: StateFlow<UiState> = _uiState.asStateFlow()

    private fun loadInitialState(): UiState {
        return UiState(
            serverHost = settingsManager.serverHost,
            serverPort = settingsManager.serverPort,
            authToken = settingsManager.authToken,
            overlayMode = settingsManager.overlayMode,
            overlayOpacity = settingsManager.overlayOpacity,
            autoConnect = settingsManager.autoConnect,
            alertOnSignal = settingsManager.alertOnSignal,
            alertOnSLHit = settingsManager.alertOnSLHit
        )
    }

    init {
        // Observe signal store and update UI state
        viewModelScope.launch {
            signalStore.currentSignal.collect { signal ->
                _uiState.update { it.copy(currentSignal = signal) }
            }
        }

        viewModelScope.launch {
            signalStore.marketData.collect { data ->
                _uiState.update { it.copy(marketData = data) }
            }
        }

        viewModelScope.launch {
            signalStore.mtfMatrix.collect { matrix ->
                _uiState.update { it.copy(mtfMatrix = matrix) }
            }
        }

        viewModelScope.launch {
            signalStore.connectionStatus.collect { status ->
                _uiState.update { it.copy(connectionState = status) }
            }
        }

        viewModelScope.launch {
            signalStore.symbolInfo.collect { info ->
                _uiState.update { it.copy(symbolInfo = info) }
            }
        }

        viewModelScope.launch {
            signalStore.regime.collect { regime ->
                _uiState.update { it.copy(regime = regime) }
            }
        }

        viewModelScope.launch {
            signalStore.signalHistory.collect { history ->
                _uiState.update { it.copy(signalHistory = history) }
            }
        }

        // --- Freshness observables (Phase G) ---
        viewModelScope.launch {
            signalStore.signalFreshness.collect { freshness ->
                _uiState.update { it.copy(signalFreshness = freshness) }
            }
        }

        viewModelScope.launch {
            signalStore.signalAge.collect { age ->
                _uiState.update { it.copy(signalAge = age) }
            }
        }

        viewModelScope.launch {
            signalStore.marketDataAge.collect { age ->
                _uiState.update { it.copy(marketDataAge = age) }
            }
        }

        viewModelScope.launch {
            signalStore.aiStatus.collect { status ->
                _uiState.update { it.copy(aiStatus = status) }
            }
        }

        viewModelScope.launch {
            signalStore.systemStatus.collect { status ->
                _uiState.update { it.copy(systemStatus = status) }
            }
        }

        // Start periodic freshness recalculation
        startFreshnessPolling()

        // Auto-connect on startup if enabled
        if (_uiState.value.autoConnect) {
            connect()
        }
    }

    /**
     * Poll freshness every second to update age display.
     */
    private fun startFreshnessPolling() {
        viewModelScope.launch {
            while (true) {
                signalStore.recalculateFreshness()
                kotlinx.coroutines.delay(1000)
            }
        }
    }

    // --- Connection actions ---
    fun connect() {
        val state = _uiState.value
        // Ensure auth token is synced to WebSocketClient before connecting
        webSocketClient.updateAuthToken(state.authToken)
        webSocketClient.connect(state.serverHost, state.serverPort)
    }

    fun disconnect() {
        webSocketClient.disconnect()
    }

    fun refreshConnection() {
        webSocketClient.reconnect()
    }

    // --- Overlay actions ---
    fun toggleOverlay() {
        val ctx = getApplication<NexusOverlayApp>()
        if (!Settings.canDrawOverlays(ctx)) {
            // Need to request permission
            _uiState.update { it.copy(needsOverlayPermission = true) }
            return
        }

        if (_uiState.value.isOverlayRunning) {
            // Stop overlay
            ctx.stopService(Intent(ctx, OverlayService::class.java))
            _uiState.update { it.copy(isOverlayRunning = false) }
        } else {
            // Start overlay
            val intent = Intent(ctx, OverlayService::class.java).apply {
                action = OverlayService.ACTION_START
                putExtra(OverlayService.EXTRA_MODE, _uiState.value.overlayMode.name)
                putExtra(OverlayService.EXTRA_OPACITY, _uiState.value.overlayOpacity)
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                ctx.startForegroundService(intent)
            } else {
                ctx.startService(intent)
            }
            _uiState.update { it.copy(isOverlayRunning = true) }
        }
    }

    // --- Settings actions (all auto-save) ---
    fun updateServerHost(host: String) {
        _uiState.update { it.copy(serverHost = host) }
        settingsManager.serverHost = host
    }

    fun updateServerPort(port: String) {
        val parsed = port.toIntOrNull() ?: 8765
        _uiState.update { it.copy(serverPort = parsed) }
        settingsManager.serverPort = parsed
    }

    fun updateAuthToken(token: String) {
        _uiState.update { it.copy(authToken = token) }
        webSocketClient.updateAuthToken(token)
        settingsManager.authToken = token
    }

    fun updateOverlayMode(mode: OverlayMode) {
        _uiState.update { it.copy(overlayMode = mode) }
        settingsManager.overlayMode = mode
        // If overlay is running, restart with new mode
        if (_uiState.value.isOverlayRunning) {
            val ctx = getApplication<NexusOverlayApp>()
            val intent = Intent(ctx, OverlayService::class.java).apply {
                action = OverlayService.ACTION_UPDATE_MODE
                putExtra(OverlayService.EXTRA_MODE, mode.name)
            }
            ctx.startService(intent)
        }
    }

    fun updateAutoConnect(enabled: Boolean) {
        _uiState.update { it.copy(autoConnect = enabled) }
        settingsManager.autoConnect = enabled
        if (enabled) connect()
    }

    fun updateAlertOnSignal(enabled: Boolean) {
        _uiState.update { it.copy(alertOnSignal = enabled) }
        settingsManager.alertOnSignal = enabled
    }

    fun updateAlertOnSLHit(enabled: Boolean) {
        _uiState.update { it.copy(alertOnSLHit = enabled) }
        settingsManager.alertOnSLHit = enabled
    }

    fun updateOverlayOpacity(opacity: Float) {
        _uiState.update { it.copy(overlayOpacity = opacity) }
        settingsManager.overlayOpacity = opacity
        if (_uiState.value.isOverlayRunning) {
            val ctx = getApplication<NexusOverlayApp>()
            val intent = Intent(ctx, OverlayService::class.java).apply {
                action = OverlayService.ACTION_UPDATE_OPACITY
                putExtra(OverlayService.EXTRA_OPACITY, opacity)
            }
            ctx.startService(intent)
        }
    }

    override fun onCleared() {
        super.onCleared()
        webSocketClient.disconnect()
    }
}

// --- UI State ---
data class UiState(
    val currentSignal: SignalData? = null,
    val marketData: MarketData = MarketData(),
    val mtfMatrix: Map<String, TimeframeSignal> = emptyMap(),
    val connectionState: ConnectionState = ConnectionState.DISCONNECTED,
    val symbolInfo: SymbolInfo? = null,
    val regime: RegimeData = RegimeData(),
    val signalHistory: List<SignalData> = emptyList(),
    val isOverlayRunning: Boolean = false,
    val overlayMode: OverlayMode = OverlayMode.STANDARD,
    val overlayOpacity: Float = 0.85f,
    val serverHost: String = SettingsManager.DEFAULT_HOST,
    val serverPort: Int = SettingsManager.DEFAULT_PORT,
    val authToken: String = SettingsManager.DEFAULT_AUTH_TOKEN,
    val autoConnect: Boolean = true,
    val alertOnSignal: Boolean = true,
    val alertOnSLHit: Boolean = false,
    val needsOverlayPermission: Boolean = false,
    // Phase G: Freshness fields
    val signalFreshness: SignalFreshness = SignalFreshness.NO_SIGNAL,
    val signalAge: Long = 0L,
    val marketDataAge: Long = 0L,
    val aiStatus: AiStatus = AiStatus.OFFLINE,
    val systemStatus: String = ""
)

enum class OverlayMode {
    COMPACT,
    STANDARD,
    PRO
}
