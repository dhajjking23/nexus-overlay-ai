package com.nexus.overlay.data

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.json.JSONObject

/**
 * In-memory signal store that holds the latest trading signal data
 * and exposes it as StateFlow for reactive UI updates.
 */
class SignalStore {

    // --- Current signal ---
    private val _currentSignal = MutableStateFlow<SignalData?>(null)
    val currentSignal: StateFlow<SignalData?> = _currentSignal.asStateFlow()

    // --- Market data ---
    private val _marketData = MutableStateFlow(MarketData())
    val marketData: StateFlow<MarketData> = _marketData.asStateFlow()

    // --- MTF Matrix ---
    private val _mtfMatrix = MutableStateFlow<Map<String, TimeframeSignal>>(emptyMap())
    val mtfMatrix: StateFlow<Map<String, TimeframeSignal>> = _mtfMatrix.asStateFlow()

    // --- Connection status ---
    private val _connectionStatus = MutableStateFlow(ConnectionState.DISCONNECTED)
    val connectionStatus: StateFlow<ConnectionState> = _connectionStatus.asStateFlow()

    // --- Symbol info ---
    private val _symbolInfo = MutableStateFlow<SymbolInfo?>(null)
    val symbolInfo: StateFlow<SymbolInfo?> = _symbolInfo.asStateFlow()

    // --- Signal history ---
    private val _signalHistory = MutableStateFlow<List<SignalData>>(emptyList())
    val signalHistory: StateFlow<List<SignalData>> = _signalHistory.asStateFlow()

    // --- Regime ---
    private val _regime = MutableStateFlow(RegimeData())
    val regime: StateFlow<RegimeData> = _regime.asStateFlow()

    companion object {
        private const val MAX_HISTORY = 50
    }

    fun updateConnectionState(state: ConnectionState) {
        _connectionStatus.value = state
    }

    fun processMessage(json: String) {
        try {
            val obj = JSONObject(json)
            val messageType = obj.optString("message_type", "")
            val payload = obj.optJSONObject("payload") ?: return

            when (messageType) {
                "SIGNAL_UPDATE" -> processSignalUpdate(payload)
                "MARKET_TICK" -> processMarketTick(payload)
                "CANDLE_CLOSED" -> processCandleClosed(payload)
                "SYMBOL_INFO" -> processSymbolInfo(payload)
                "HEARTBEAT" -> processHeartbeat(payload)
                "CONNECTION_STATUS" -> processConnectionStatus(payload)
            }
        } catch (e: Exception) {
            // Silent parse failure - don't crash on bad data
        }
    }

    private fun processSignalUpdate(payload: JSONObject) {
        val signal = SignalData(
            signalType = payload.optString("signal", "WAIT"),
            entry = payload.optDouble("entry", 0.0),
            sl = payload.optDouble("sl", 0.0),
            tp1 = payload.optDouble("tp1", 0.0),
            tp2 = payload.optDouble("tp2", 0.0),
            tp3 = payload.optDouble("tp3", 0.0),
            confidence = payload.optDouble("confidence", 0.0),
            timeframe = payload.optString("timeframe", ""),
            reason = payload.optString("reason", ""),
            timestamp = System.currentTimeMillis()
        )
        _currentSignal.value = signal

        // Add to history (prepend, cap at MAX_HISTORY)
        val history = _signalHistory.value.toMutableList()
        history.add(0, signal)
        if (history.size > MAX_HISTORY) history.removeAt(history.size - 1)
        _signalHistory.value = history

        // Update MTF matrix if present
        val mtf = payload.optJSONObject("mtf_matrix")
        if (mtf != null) {
            val matrix = mutableMapOf<String, TimeframeSignal>()
            for (key in mtf.keys()) {
                val tfObj = mtf.getJSONObject(key)
                matrix[key] = TimeframeSignal(
                    signal = tfObj.optString("signal", "NEUTRAL"),
                    strength = tfObj.optDouble("strength", 0.0),
                    alignment = tfObj.optString("alignment", "none")
                )
            }
            _mtfMatrix.value = matrix
        }

        // Update regime if present
        val regimeObj = payload.optJSONObject("regime")
        if (regimeObj != null) {
            _regime.value = RegimeData(
                type = regimeObj.optString("type", "unknown"),
                strength = regimeObj.optDouble("strength", 0.0),
                description = regimeObj.optString("description", "")
            )
        }
    }

    private fun processMarketTick(payload: JSONObject) {
        _marketData.value = _marketData.value.copy(
            bid = payload.optDouble("bid", 0.0),
            ask = payload.optDouble("ask", 0.0),
            spread = payload.optDouble("spread", 0.0),
            lastUpdate = System.currentTimeMillis()
        )
    }

    private fun processCandleClosed(payload: JSONObject) {
        // Could store latest candles per timeframe here
    }

    private fun processSymbolInfo(payload: JSONObject) {
        _symbolInfo.value = SymbolInfo(
            digits = payload.optInt("digits", 2),
            point = payload.optDouble("point", 0.01),
            spread = payload.optDouble("spread", 0.0),
            lotMin = payload.optDouble("lot_min", 0.01),
            lotMax = payload.optDouble("lot_max", 100.0),
            lotStep = payload.optDouble("lot_step", 0.01),
            contractSize = payload.optDouble("contract_size", 100.0),
            currency = payload.optString("currency", "USD"),
            stopLevel = payload.optInt("stop_level", 0),
            freezeLevel = payload.optInt("freeze_level", 0)
        )
    }

    private fun processHeartbeat(payload: JSONObject) {
        // Heartbeat confirms backend is alive
        if (_connectionStatus.value == ConnectionState.CONNECTED) {
            _connectionStatus.value = ConnectionState.CONNECTED
        }
    }

    private fun processConnectionStatus(payload: JSONObject) {
        val status = payload.optString("status", "UNKNOWN")
        _connectionStatus.value = when (status) {
            "CONNECTED" -> ConnectionState.CONNECTED
            "DISCONNECTED" -> ConnectionState.DISCONNECTED
            "STALE" -> ConnectionState.STALE
            else -> ConnectionState.ERROR
        }
    }

    fun clear() {
        _currentSignal.value = null
        _marketData.value = MarketData()
        _mtfMatrix.value = emptyMap()
        _signalHistory.value = emptyList()
        _regime.value = RegimeData()
    }
}

// --- Data classes ---

data class SignalData(
    val signalType: String = "WAIT",
    val entry: Double = 0.0,
    val sl: Double = 0.0,
    val tp1: Double = 0.0,
    val tp2: Double = 0.0,
    val tp3: Double = 0.0,
    val confidence: Double = 0.0,
    val timeframe: String = "",
    val reason: String = "",
    val timestamp: Long = 0L
)

data class MarketData(
    val bid: Double = 0.0,
    val ask: Double = 0.0,
    val spread: Double = 0.0,
    val lastUpdate: Long = 0L
)

data class TimeframeSignal(
    val signal: String = "NEUTRAL",
    val strength: Double = 0.0,
    val alignment: String = "none"
)

data class RegimeData(
    val type: String = "unknown",
    val strength: Double = 0.0,
    val description: String = ""
)

data class SymbolInfo(
    val digits: Int = 2,
    val point: Double = 0.01,
    val spread: Double = 0.0,
    val lotMin: Double = 0.01,
    val lotMax: Double = 100.0,
    val lotStep: Double = 0.01,
    val contractSize: Double = 100.0,
    val currency: String = "USD",
    val stopLevel: Int = 0,
    val freezeLevel: Int = 0
)

enum class ConnectionState {
    DISCONNECTED,
    CONNECTING,
    CONNECTED,
    STALE,
    ERROR
}
