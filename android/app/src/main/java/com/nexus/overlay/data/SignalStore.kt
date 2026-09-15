package com.nexus.overlay.data

import android.util.Log
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.json.JSONObject

/**
 * In-memory signal store that holds the latest trading signal data
 * and exposes it as StateFlow for reactive UI updates.
 */
class SignalStore {

    companion object {
        private const val TAG = "SignalStore"
        private const val MAX_HISTORY = 50
    }

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

    fun updateConnectionState(state: ConnectionState) {
        _connectionStatus.value = state
    }

    fun processMessage(json: String) {
        try {
            val obj = JSONObject(json)
            val messageType = obj.optString("message_type", "")
            val payload = obj.optJSONObject("payload") ?: return

            when (messageType) {
                "SIGNAL_CREATED" -> processSignal(payload, isUpdate = false)
                "SIGNAL_UPDATED" -> processSignal(payload, isUpdate = true)
                "SIGNAL_INVALIDATED" -> {
                    _currentSignal.value = null
                }
                "MARKET_SNAPSHOT" -> processMarketSnapshot(payload)
                "MARKET_TICK" -> processMarketTick(payload)
                "CANDLE_CLOSED" -> {
                    // No-op for now
                }
                "SYMBOL_INFO" -> processSymbolInfo(payload)
                "HEARTBEAT" -> {
                    // Heartbeat confirms backend is alive
                    Log.d(TAG, "Heartbeat received")
                }
                "CONNECTION_STATUS" -> processConnectionStatus(payload)
                "SYSTEM_STATUS" -> {
                    val status = payload.optString("status", "unknown")
                    val message = payload.optString("message", "")
                    Log.i(TAG, "System status: $status - $message")
                }
            }
        } catch (e: Exception) {
            // Silent parse failure - don't crash on bad data
            Log.w(TAG, "Failed to parse message: ${e.message}")
        }
    }

    private fun processSignal(payload: JSONObject, isUpdate: Boolean) {
        val signal = SignalData(
            decision = payload.optString("decision", "WAIT"),
            confidence = payload.optDouble("confidence", 0.0),
            entry = payload.optDouble("entry", 0.0),
            sl = payload.optDouble("sl", 0.0),
            tp1 = payload.optDouble("tp1", 0.0),
            tp2 = payload.optDouble("tp2", 0.0),
            tp3 = payload.optDouble("tp3", 0.0),
            rr = payload.optDouble("rr", 0.0),
            trend = payload.optString("trend", ""),
            regime = payload.optString("regime", ""),
            evidence = payload.optJSONArray("evidence")?.let { arr ->
                (0 until arr.length()).map { arr.getString(it) }
            } ?: emptyList(),
            invalidations = payload.optJSONArray("invalidations")?.let { arr ->
                (0 until arr.length()).map { arr.getString(it) }
            } ?: emptyList(),
            isUpdate = isUpdate,
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

    private fun processMarketSnapshot(payload: JSONObject) {
        _marketData.value = _marketData.value.copy(
            bid = payload.optDouble("bid", 0.0),
            ask = payload.optDouble("ask", 0.0),
            spread = payload.optDouble("spread", 0.0),
            price = payload.optDouble("price", 0.0),
            lastUpdate = System.currentTimeMillis()
        )
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
    val decision: String = "WAIT",
    val confidence: Double = 0.0,
    val entry: Double = 0.0,
    val sl: Double = 0.0,
    val tp1: Double = 0.0,
    val tp2: Double = 0.0,
    val tp3: Double = 0.0,
    val rr: Double = 0.0,
    val trend: String = "",
    val regime: String = "",
    val evidence: List<String> = emptyList(),
    val invalidations: List<String> = emptyList(),
    val isUpdate: Boolean = false,
    val timestamp: Long = 0L,
    // Legacy fields kept for backward compatibility
    val signalType: String = decision,
    val timeframe: String = "",
    val reason: String = ""
)

data class MarketData(
    val bid: Double = 0.0,
    val ask: Double = 0.0,
    val spread: Double = 0.0,
    val price: Double = 0.0,
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
