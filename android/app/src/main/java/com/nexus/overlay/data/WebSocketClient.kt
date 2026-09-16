package com.nexus.overlay.data

import android.util.Log
import kotlinx.coroutines.*
import okhttp3.*
import okio.ByteString
import org.json.JSONObject
import java.util.Random
import java.util.concurrent.TimeUnit

/**
 * WebSocket client that connects to the Nexus Overlay AI Python backend.
 * Handles connection, reconnection with exponential backoff + jitter,
 * periodic heartbeat ping, connection quality tracking, and state resync on reconnect.
 */
class WebSocketClient(
    private val signalStore: SignalStore,
    private var authToken: String = ""
) {
    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.SECONDS) // No read timeout for WebSocket
        .writeTimeout(10, TimeUnit.SECONDS)
        .pingInterval(30, TimeUnit.SECONDS)
        .build()

    private var webSocket: WebSocket? = null
    private var scope: CoroutineScope? = null
    private var host = "192.168.1.100"
    private var port = 8765
    private var autoReconnect = true
    private var reconnectAttempt = 0
    private var maxReconnectDelay = 30_000L // 30 seconds max
    private val random = Random()

    // --- Heartbeat tracking ---
    private var heartbeatJob: Job? = null
    private var lastPongReceived = 0L
    private val heartbeatIntervalMs = 15_000L  // Send ping every 15 seconds
    private val heartbeatTimeoutMs = 30_000L   // If no pong in 30s, consider dead

    // --- Connection quality ---
    private var _connectionQuality = ConnectionQuality.UNKNOWN
    private var _latencyMs = 0L
    private var _packetsSent = 0L
    private var _packetsReceived = 0L
    private var _reconnectCount = 0

    /** Get current connection quality metrics */
    fun getConnectionQuality(): ConnectionQualitySnapshot {
        return ConnectionQualitySnapshot(
            quality = _connectionQuality,
            latencyMs = _latencyMs,
            packetsSent = _packetsSent,
            packetsReceived = _packetsReceived,
            reconnectCount = _reconnectCount
        )
    }

    /**
     * Update the auth token used for server identification.
     */
    fun updateAuthToken(token: String) {
        authToken = token
    }

    /**
     * Update the server host and port.
     */
    fun updateServer(host: String, port: Int) {
        this.host = host
        this.port = port
    }

    /**
     * Connect to the WebSocket server.
     * Uses currently saved host/port/authToken if not overridden.
     */
    fun connect(serverHost: String = host, serverPort: Int = port) {
        host = serverHost
        port = serverPort
        signalStore.updateConnectionState(ConnectionState.CONNECTING)

        val url = "ws://$host:$port"
        val request = Request.Builder()
            .url(url)
            .header("X-Client", "nexus-overlay-android")
            .header("X-Version", "2.0.0")
            .build()

        webSocket = client.newWebSocket(request, createListener())
        reconnectAttempt = 0
    }

    /**
     * Disconnect from the WebSocket server.
     */
    fun disconnect() {
        autoReconnect = false
        stopHeartbeat()
        scope?.cancel()
        webSocket?.close(1000, "Client disconnect")
        webSocket = null
        _connectionQuality = ConnectionQuality.UNKNOWN
        signalStore.updateConnectionState(ConnectionState.DISCONNECTED)
    }

    /**
     * Reconnect with the current host/port.
     */
    fun reconnect() {
        disconnect()
        autoReconnect = true
        connect(host, port)
    }

    /**
     * Send a message to the server (e.g., subscribe, acknowledge).
     */
    fun send(message: String) {
        val sent = webSocket?.send(message) ?: false
        if (sent) _packetsSent++
    }

    /**
     * Set auto-reconnect behavior.
     */
    fun setAutoReconnect(enabled: Boolean) {
        autoReconnect = enabled
    }

    /**
     * Check if currently connected.
     */
    fun isConnected(): Boolean {
        return webSocket != null && signalStore.connectionStatus.value == ConnectionState.CONNECTED
    }

    // --- Heartbeat ---

    private fun startHeartbeat() {
        stopHeartbeat()
        lastPongReceived = System.currentTimeMillis()
        heartbeatJob = scope?.launch {
            while (isActive) {
                delay(heartbeatIntervalMs)
                sendHeartbeatPing()

                // Check if we've timed out (no pong received)
                val now = System.currentTimeMillis()
                if (lastPongReceived > 0 && (now - lastPongReceived) > heartbeatTimeoutMs) {
                    Log.w(TAG, "Heartbeat timeout — server may be unresponsive")
                    _connectionQuality = ConnectionQuality.POOR
                    signalStore.updateConnectionState(ConnectionState.STALE)
                    // Force reconnect
                    attemptReconnect()
                    return@launch
                }
            }
        }
    }

    private fun stopHeartbeat() {
        heartbeatJob?.cancel()
        heartbeatJob = null
    }

    private fun sendHeartbeatPing() {
        try {
            val pingTime = System.currentTimeMillis()
            val payload = JSONObject().apply {
                put("client_type", "ANDROID")
                put("client_version", "2.0.0")
                put("ping_time_ms", pingTime)
                if (authToken.isNotEmpty()) {
                    put("auth_token", authToken)
                }
            }
            val msg = JSONObject().apply {
                put("protocol_version", "1.0")
                put("message_type", "PING")
                put("sequence", 0)
                put("symbol", "XAUUSD")
                put("timeframe", "TICK")
                put("timestamp", pingTime)
                put("payload", payload)
            }
            webSocket?.send(msg.toString())
            _packetsSent++
        } catch (e: Exception) {
            Log.w(TAG, "Failed to send heartbeat: ${e.message}")
        }
    }

    // --- State resync on reconnect ---

    private fun requestStateResync() {
        try {
            val msg = JSONObject().apply {
                put("protocol_version", "1.0")
                put("message_type", "REQUEST_STATE_RESYNC")
                put("sequence", 0)
                put("symbol", "XAUUSD")
                put("timeframe", "TICK")
                put("timestamp", System.currentTimeMillis())
                put("payload", JSONObject().apply {
                    put("client_type", "ANDROID")
                    put("client_version", "2.0.0")
                    put("request", "FULL_STATE")
                    if (authToken.isNotEmpty()) {
                        put("auth_token", authToken)
                    }
                })
            }
            webSocket?.send(msg.toString())
            _packetsSent++
            Log.i(TAG, "State resync requested")
        } catch (e: Exception) {
            Log.w(TAG, "Failed to request state resync: ${e.message}")
        }
    }

    // --- Identification ---

    private fun buildIdentificationMessage(): String {
        val payload = JSONObject().apply {
            put("client_type", "ANDROID")
            put("client_version", "2.0.0")
            if (authToken.isNotEmpty()) {
                put("auth_token", authToken)
            }
        }
        val msg = JSONObject().apply {
            put("protocol_version", "1.0")
            put("message_type", "HEARTBEAT")
            put("sequence", 0)
            put("symbol", "XAUUSD")
            put("timeframe", "TICK")
            put("timestamp", System.currentTimeMillis())
            put("payload", payload)
        }
        return msg.toString()
    }

    // --- WebSocket listener ---

    private fun createListener(): WebSocketListener {
        return object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                reconnectAttempt = 0
                _reconnectCount++
                signalStore.updateConnectionState(ConnectionState.CONNECTED)
                _connectionQuality = ConnectionQuality.EXCELLENT

                // Send identification message as first message (includes auth_token)
                val identificationMsg = buildIdentificationMessage()
                webSocket.send(identificationMsg)
                _packetsSent++

                // Request state resync immediately after connecting
                requestStateResync()

                // Start heartbeat monitoring
                scope?.let {
                    startHeartbeat()
                }
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                _packetsReceived++
                lastPongReceived = System.currentTimeMillis()

                // Check for PONG messages (server heartbeat response)
                try {
                    val obj = JSONObject(text)
                    val messageType = obj.optString("message_type", "")
                    if (messageType == "PONG") {
                        val serverTime = obj.optJSONObject("payload")?.optLong("server_time_ms", 0L) ?: 0L
                        if (serverTime > 0) {
                            _latencyMs = (System.currentTimeMillis() - serverTime) / 2
                            updateConnectionQuality()
                        }
                        return
                    }
                } catch (_: Exception) {
                    // Not JSON or no message_type — pass through to SignalStore
                }

                // Route message to SignalStore for processing
                signalStore.processMessage(text)
            }

            override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
                // Handle binary messages if needed
                onMessage(webSocket, bytes.utf8())
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                webSocket.close(code, reason)
                stopHeartbeat()
                signalStore.updateConnectionState(ConnectionState.DISCONNECTED)
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                stopHeartbeat()
                _connectionQuality = ConnectionQuality.UNKNOWN
                signalStore.updateConnectionState(ConnectionState.DISCONNECTED)
                attemptReconnect()
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                stopHeartbeat()
                _connectionQuality = ConnectionQuality.UNKNOWN
                signalStore.updateConnectionState(ConnectionState.ERROR)
                attemptReconnect()
            }
        }
    }

    // --- Reconnection with exponential backoff + jitter ---

    private fun attemptReconnect() {
        if (!autoReconnect) return

        scope?.cancel()
        scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

        reconnectAttempt++
        val delayMs = calculateReconnectDelay()

        Log.i(TAG, "Reconnecting in ${delayMs}ms (attempt $reconnectAttempt)")

        scope?.launch {
            delay(delayMs)
            if (autoReconnect) {
                connect(host, port)
            }
        }
    }

    private fun calculateReconnectDelay(): Long {
        // Exponential backoff with full jitter (Section D4: reconnect spec)
        // delay = random(0, min(cap, base * 2^attempt))
        val baseDelay = 1000L * (1L shl minOf(reconnectAttempt - 1, 4))
        val cappedDelay = minOf(baseDelay, maxReconnectDelay)
        // Add jitter: between 0 and cappedDelay
        val jitter = (cappedDelay * random.nextDouble()).toLong()
        return maxOf(500L, jitter) // Minimum 500ms
    }

    // --- Connection quality assessment ---

    private fun updateConnectionQuality() {
        _connectionQuality = when {
            _latencyMs < 100 -> ConnectionQuality.EXCELLENT
            _latencyMs < 300 -> ConnectionQuality.GOOD
            _latencyMs < 1000 -> ConnectionQuality.FAIR
            else -> ConnectionQuality.POOR
        }
    }

    companion object {
        private const val TAG = "WebSocketClient"
    }
}

/**
 * Connection quality levels for the WebSocket link.
 */
enum class ConnectionQuality {
    UNKNOWN,
    EXCELLENT,
    GOOD,
    FAIR,
    POOR
}

/**
 * Snapshot of current connection quality metrics.
 */
data class ConnectionQualitySnapshot(
    val quality: ConnectionQuality = ConnectionQuality.UNKNOWN,
    val latencyMs: Long = 0L,
    val packetsSent: Long = 0L,
    val packetsReceived: Long = 0L,
    val reconnectCount: Int = 0
)
