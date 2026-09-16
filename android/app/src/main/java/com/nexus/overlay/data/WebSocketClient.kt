package com.nexus.overlay.data

import kotlinx.coroutines.*
import okhttp3.*
import okio.ByteString
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * WebSocket client that connects to the Nexus Overlay AI Python backend.
 * Handles connection, reconnection, and message routing to SignalStore.
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

    private val _isConnected = false

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
            .header("X-Version", "1.0.0")
            .build()

        webSocket = client.newWebSocket(request, createListener())
        reconnectAttempt = 0
    }

    /**
     * Disconnect from the WebSocket server.
     */
    fun disconnect() {
        autoReconnect = false
        scope?.cancel()
        webSocket?.close(1000, "Client disconnect")
        webSocket = null
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
        webSocket?.send(message)
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

    private fun buildIdentificationMessage(): String {
        val payload = JSONObject().apply {
            put("client_type", "ANDROID")
            put("client_version", "1.0.0")
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

    private fun createListener(): WebSocketListener {
        return object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                reconnectAttempt = 0
                signalStore.updateConnectionState(ConnectionState.CONNECTED)

                // Send identification message as first message (includes auth_token)
                val identificationMsg = buildIdentificationMessage()
                webSocket.send(identificationMsg)
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                // Route message to SignalStore for processing
                signalStore.processMessage(text)
            }

            override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
                // Handle binary messages if needed
                onMessage(webSocket, bytes.utf8())
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                webSocket.close(code, reason)
                signalStore.updateConnectionState(ConnectionState.DISCONNECTED)
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                signalStore.updateConnectionState(ConnectionState.DISCONNECTED)
                attemptReconnect()
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                signalStore.updateConnectionState(ConnectionState.ERROR)
                attemptReconnect()
            }
        }
    }

    private fun attemptReconnect() {
        if (!autoReconnect) return

        scope?.cancel()
        scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

        reconnectAttempt++
        val delayMs = calculateReconnectDelay()

        scope?.launch {
            delay(delayMs)
            if (autoReconnect) {
                connect(host, port)
            }
        }
    }

    private fun calculateReconnectDelay(): Long {
        // Exponential backoff: 1s, 2s, 4s, 8s, 16s, 30s (capped)
        val baseDelay = 1000L * (1L shl minOf(reconnectAttempt - 1, 4))
        return minOf(baseDelay, maxReconnectDelay)
    }
}