package com.nexus.overlay.data

import android.util.Log
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.json.JSONObject

/**
 * In-memory signal store that holds the latest trading signal data
 * and exposes it as StateFlow for reactive UI updates.
 *
 * Includes stale signal protection:
 * - STALE: no update within STALE_THRESHOLD_MS (15s)
 * - INVALID: no update within CRITICAL_THRESHOLD_MS (30s)
 * Tracks signal_age, market_data_age, decision_age.
 * Handles state resync on reconnect.
 */
class SignalStore {

    companion object {
        private const val TAG = "SignalStore"
        private const val MAX_HISTORY = 50

        /** After this many ms without a signal update, mark as STALE */
        const val STALE_THRESHOLD_MS = 15_000L
        /** After this many ms without a signal update, mark as INVALID */
        const val CRITICAL_THRESHOLD_MS = 30_000L
        /** After this many ms without market data, mark market data as stale */
        const val MARKET_STALE_THRESHOLD_MS = 10_000L
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

    // --- Signal freshness ---
    private val _signalFreshness = MutableStateFlow(SignalFreshness.FRESH)
    val signalFreshness: StateFlow<SignalFreshness> = _signalFreshness.asStateFlow()

    // --- Ages (milliseconds since last update) ---
    private val _signalAge = MutableStateFlow(0L)
    val signalAge: StateFlow<Long> = _signalAge.asStateFlow()

    private val _marketDataAge = MutableStateFlow(0L)
    val marketDataAge: StateFlow<Long> = _marketDataAge.asStateFlow()

    private val _decisionAge = MutableStateFlow(0L)
    val decisionAge: StateFlow<Long> = _decisionAge.asStateFlow()

    // --- AI status ---
    private val _aiStatus = MutableStateFlow(AiStatus.OFFLINE)
    val aiStatus: StateFlow<AiStatus> = _aiStatus.asStateFlow()

    // --- System status ---
    private val _systemStatus = MutableStateFlow("")
    val systemStatus: StateFlow<String> = _systemStatus.asStateFlow()

    // --- Wait reason (for WAIT decisions) ---
    private val _waitReason = MutableStateFlow<String?>(null)
    val waitReason: StateFlow<String?> = _waitReason.asStateFlow()

    // --- Timestamps for age tracking ---
    private var lastSignalTimestamp = 0L
    private var lastMarketTimestamp = 0L
    private var lastDecisionTimestamp = 0L

    fun updateConnectionState(state: ConnectionState) {
        _connectionStatus.value = state
    }

    /**
     * Recalculate freshness based on current time and thresholds.
     * Should be called periodically (e.g., every second) from a coroutine.
     */
    fun recalculateFreshness() {
        val now = System.currentTimeMillis()

        // Signal age
        if (lastSignalTimestamp > 0) {
            val age = now - lastSignalTimestamp
            _signalAge.value = age
            _signalFreshness.value = when {
                age >= CRITICAL_THRESHOLD_MS -> SignalFreshness.INVALID
                age >= STALE_THRESHOLD_MS -> SignalFreshness.STALE
                else -> SignalFreshness.FRESH
            }
        } else if (_currentSignal.value != null) {
            // Signal exists but no timestamp — consider stale
            _signalFreshness.value = SignalFreshness.STALE
        }

        // Market data age
        if (lastMarketTimestamp > 0) {
            _marketDataAge.value = now - lastMarketTimestamp
        }

        // Decision age
        if (lastDecisionTimestamp > 0) {
            _decisionAge.value = now - lastDecisionTimestamp
        }
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
                    _signalFreshness.value = SignalFreshness.NO_SIGNAL
                    _waitReason.value = payload.optString("reason", "INVALIDATED")
                    lastSignalTimestamp = 0L
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
                    _systemStatus.value = "$status - $message"
                    Log.i(TAG, "System status: $status - $message")
                }

                // === State resync messages (sent on reconnect) ===
                "CURRENT_MARKET_SNAPSHOT" -> processMarketSnapshot(payload)
                "CURRENT_ACTIVE_SIGNAL" -> processSignal(payload, isUpdate = false)
                "CURRENT_SYSTEM_STATUS" -> {
                    val status = payload.optString("status", "unknown")
                    val message = payload.optString("message", "")
                    _systemStatus.value = "$status - $message"

                    // AI status
                    val aiOnline = payload.optBoolean("ai_online", false)
                    _aiStatus.value = if (aiOnline) AiStatus.ONLINE else AiStatus.OFFLINE

                    // Regime from system status
                    val regimeObj = payload.optJSONObject("regime")
                    if (regimeObj != null) {
                        _regime.value = RegimeData(
                            type = regimeObj.optString("type", "unknown"),
                            strength = regimeObj.optDouble("strength", 0.0),
                            description = regimeObj.optString("description", "")
                        )
                    }

                    Log.i(TAG, "State resync: system status received")
                }
                "MTF_UPDATE" -> {
                    val matrix = mutableMapOf<String, TimeframeSignal>()
                    for (key in payload.keys()) {
                        val tfObj = payload.getJSONObject(key)
                        matrix[key] = TimeframeSignal(
                            signal = tfObj.optString("signal", "NEUTRAL"),
                            strength = tfObj.optDouble("strength", 0.0),
                            alignment = tfObj.optString("alignment", "none")
                        )
                    }
                    _mtfMatrix.value = matrix
                }
            }
        } catch (e: Exception) {
            // Silent parse failure - don't crash on bad data
            Log.w(TAG, "Failed to parse message: ${e.message}")
        }
    }

    private fun processSignal(payload: JSONObject, isUpdate: Boolean) {
        val now = System.currentTimeMillis()
        lastSignalTimestamp = now
        lastDecisionTimestamp = now

        val decision = payload.optString("decision", "WAIT")

        // Parse wait reason from WAIT decisions (Section 82: show reason)
        if (decision == "WAIT") {
            _waitReason.value = payload.optString("wait_reason",
                payload.optString("reason", null))
        } else {
            _waitReason.value = null
        }

        // Parse counter evidence (Section 20/27)
        val counterEvidence = payload.optJSONArray("counter_evidence")?.let { arr ->
            (0 until arr.length()).map { arr.getString(it) }
        } ?: emptyList()

        val signal = SignalData(
            decision = decision,
            confidence = payload.optDouble("confidence",
                payload.optDouble("decision_score", 0.0)),
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
            counterEvidence = counterEvidence,
            invalidations = payload.optJSONArray("invalidations")?.let { arr ->
                (0 until arr.length()).map { arr.getString(it) }
            } ?: emptyList(),
            isUpdate = isUpdate,
            timestamp = now,
            decisionScore = payload.optDouble("decision_score",
                payload.optDouble("confidence", 0.0)),
            waitReason = if (decision == "WAIT")
                payload.optString("wait_reason", payload.optString("reason", ""))
            else "",
            // Legacy fields kept for backward compatibility
            signalType = decision,
            timeframe = payload.optString("timeframe", ""),
            reason = payload.optString("reason", "")
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

        // Update AI status if present
        val aiOnline = payload.optBoolean("ai_online", false)
        if (payload.has("ai_online")) {
            _aiStatus.value = if (aiOnline) AiStatus.ONLINE else AiStatus.OFFLINE
        }
    }

    private fun processMarketSnapshot(payload: JSONObject) {
        lastMarketTimestamp = System.currentTimeMillis()
        _marketData.value = _marketData.value.copy(
            bid = payload.optDouble("bid", 0.0),
            ask = payload.optDouble("ask", 0.0),
            spread = payload.optDouble("spread", 0.0),
            price = payload.optDouble("price", 0.0),
            lastUpdate = System.currentTimeMillis()
        )
    }

    private fun processMarketTick(payload: JSONObject) {
        lastMarketTimestamp = System.currentTimeMillis()
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
        _signalFreshness.value = SignalFreshness.NO_SIGNAL
        _signalAge.value = 0L
        _marketDataAge.value = 0L
        _decisionAge.value = 0L
        _aiStatus.value = AiStatus.OFFLINE
        _systemStatus.value = ""
        _waitReason.value = null
        lastSignalTimestamp = 0L
        lastMarketTimestamp = 0L
        lastDecisionTimestamp = 0L
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
    val counterEvidence: List<String> = emptyList(),
    val invalidations: List<String> = emptyList(),
    val isUpdate: Boolean = false,
    val timestamp: Long = 0L,
    val decisionScore: Double = 0.0,
    val waitReason: String = "",
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

/**
 * Signal freshness levels (Section 41: stale signal protection).
 * FRESH: signal updated within STALE_THRESHOLD_MS
 * STALE: signal not updated for STALE_THRESHOLD_MS to CRITICAL_THRESHOLD_MS
 * INVALID: signal not updated for > CRITICAL_THRESHOLD_MS
 * NO_SIGNAL: no signal received yet
 */
enum class SignalFreshness {
    FRESH,
    STALE,
    INVALID,
    NO_SIGNAL
}

/**
 * AI provider status (Section 6/7: AI-independent mode).
 * The system must work with AI OFFLINE.
 */
enum class AiStatus {
    ONLINE,
    OFFLINE
}
