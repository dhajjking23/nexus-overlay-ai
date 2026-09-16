"""
NEXUS OVERLAY AI - WebSocket Server
Accepts multiple clients (MT5 EA + Android), manages connection lifecycle,
stale data detection, reconnect logic, heartbeat, broadcasts signals.
"""
from __future__ import annotations
import asyncio
import json
import time
import logging
from dataclasses import dataclass, field
from typing import Callable, Awaitable, Optional, Any
from enum import Enum

import websockets
from websockets.server import serve, WebSocketServerProtocol

from backend.models import (
    MessageType, ProtocolMessage, TickData, CandleData, SymbolInfo,
    now_ms, SystemStatus, SignalLifecycleState, DecisionState,
)
from backend.transport.protocol import (
    PROTOCOL_VERSION, MessageValidator, HeartbeatManager,
    create_message, create_heartbeat, parse_message,
    serialize_message, ProtocolError, ChecksumMismatchError,
    SequenceError, DuplicateMessageError, compute_checksum,
)
from backend.config_loader import get_config
from backend.auth import TokenAuth, RateLimiter, AuthResult

logger = logging.getLogger(__name__)


class ClientType(Enum):
    MT5_EA = "MT5_EA"
    ANDROID = "ANDROID"
    UNKNOWN = "UNKNOWN"


@dataclass
class ConnectedClient:
    """Tracks a connected WebSocket client."""
    websocket: WebSocketServerProtocol
    client_type: ClientType
    client_id: str
    symbol: str = "XAUUSD"
    last_seen: int = 0
    last_sequence: int = 0
    validator: MessageValidator = field(default_factory=MessageValidator)
    heartbeat: HeartbeatManager = field(default_factory=HeartbeatManager)
    metadata: dict = field(default_factory=dict)
    
    @property
    def is_stale(self) -> bool:
        return self.heartbeat.is_stale(timeout_ms=30000)


# Type alias for message handlers
MessageHandler = Callable[[ConnectedClient, ProtocolMessage], Awaitable[None]]
ConnectionHandler = Callable[[ConnectedClient], Awaitable[None]]
DisconnectionHandler = Callable[[ConnectedClient], Awaitable[None]]


class NexusWebSocketServer:
    """
    WebSocket server for NEXUS OVERLAY AI.
    
    Manages bidirectional communication between:
    - MT5 EA (sends ticks, candles, symbol info)
    - Android clients (receives signals, snapshots)
    
    Features:
    - Multiple client support with type detection
    - Heartbeat management per client
    - Stale data detection
    - Broadcast to all Android clients
    - Per-client sequence validation
    """
    
    def __init__(self, config: dict | None = None):
        cfg = config or get_config()
        self.host = cfg.get("transport.host", "0.0.0.0")
        self.port = int(cfg.get("transport.port", 8765))
        self.heartbeat_interval = int(cfg.get("transport.heartbeat_interval", 5000))
        self.stale_timeout = int(cfg.get("transport.stale_data_timeout_ms", 10000))
        self.reconnect_delay = int(cfg.get("transport.reconnect_delay_ms", 1000))
        self.max_reconnect = int(cfg.get("transport.max_reconnect_attempts", 10))
        self.protocol_version = cfg.get("transport.protocol_version", "1.0")
        
        # Connected clients
        self.clients: dict[str, ConnectedClient] = {}
        self._sequence: int = 0
        
        # Callbacks
        self._on_tick: Optional[MessageHandler] = None
        self._on_candle: Optional[MessageHandler] = None
        self._on_symbol_info: Optional[MessageHandler] = None
        self._on_config_update: Optional[MessageHandler] = None
        self._on_calibrate: Optional[MessageHandler] = None
        self._on_connect: Optional[ConnectionHandler] = None
        self._on_disconnect: Optional[DisconnectionHandler] = None
        
        # Security
        self._auth = TokenAuth(config=cfg)
        max_per_minute = int(cfg.get("transport.rate_limit_per_minute", 120))
        self._rate_limiter = RateLimiter(max_per_minute=max_per_minute, burst=20)

        # Server state
        self._server = None
        self._running = False
        self._stale_check_task: Optional[asyncio.Task] = None
        self._event_bus = None

        # Runtime stats
        self._stats: dict = {
            "total_messages": 0,
            "messages_per_minute": 0.0,
            "uptime_start": 0,
        }
    
    def on_tick(self, handler: MessageHandler) -> None:
        self._on_tick = handler
    
    def on_candle(self, handler: MessageHandler) -> None:
        self._on_candle = handler
    
    def on_symbol_info(self, handler: MessageHandler) -> None:
        self._on_symbol_info = handler
    
    def on_config_update(self, handler: MessageHandler) -> None:
        self._on_config_update = handler
    
    def on_calibrate(self, handler: MessageHandler) -> None:
        self._on_calibrate = handler
    
    def on_connect(self, handler: ConnectionHandler) -> None:
        self._on_connect = handler
    
    def on_disconnect(self, handler: DisconnectionHandler) -> None:
        self._on_disconnect = handler
    
    def set_event_bus(self, event_bus) -> None:
        """Set the event bus for publishing events."""
        self._event_bus = event_bus
    
    async def start(self) -> None:
        """Start the WebSocket server."""
        self._running = True
        self._stats["uptime_start"] = time.time()
        self._server = await serve(
            self._handle_client,
            self.host,
            self.port,
            ping_interval=None,  # We handle ping ourselves
            ping_timeout=None,
        )
        logger.info(f"WebSocket server started on {self.host}:{self.port}")
        
        # Start stale connection checker
        self._stale_check_task = asyncio.create_task(self._stale_check_loop())
    
    async def stop(self) -> None:
        """Stop the WebSocket server gracefully."""
        self._running = False
        
        if self._stale_check_task:
            self._stale_check_task.cancel()
            try:
                await self._stale_check_task
            except asyncio.CancelledError:
                pass
        
        # Stop heartbeats for all clients
        for client in list(self.clients.values()):
            await client.heartbeat.stop()
        
        # Close all connections
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        
        # Disconnect all clients
        for client_id in list(self.clients.keys()):
            await self._remove_client(client_id)
        
        logger.info("WebSocket server stopped")
    
    def _detect_client_type(self, ws: WebSocketServerProtocol, message: ProtocolMessage) -> ClientType:
        """Detect client type from first message payload."""
        payload = message.payload
        client_type_str = payload.get("client_type", "")
        
        if client_type_str == "MT5_EA" or message.message_type in (
            MessageType.MARKET_TICK, MessageType.CANDLE_CLOSED, MessageType.SYMBOL_INFO
        ):
            return ClientType.MT5_EA
        elif client_type_str == "ANDROID":
            return ClientType.ANDROID
        
        return ClientType.UNKNOWN
    
    def _generate_client_id(self, client_type: ClientType, ws: WebSocketServerProtocol) -> str:
        """Generate unique client ID."""
        remote = ws.remote_address if ws.remote_address else ("unknown", 0)
        prefix = client_type.value.lower()
        return f"{prefix}_{remote[0]}_{remote[1]}_{int(time.time() * 1000)}"
    
    async def _handle_client(self, ws: WebSocketServerProtocol) -> None:
        """Handle a single WebSocket client connection."""
        client: Optional[ConnectedClient] = None
        client_id: Optional[str] = None

        # Rate limit check
        remote_ip = "unknown"
        if ws.remote_address:
            remote_ip = ws.remote_address[0]

        if not self._rate_limiter.check_rate_limit(remote_ip):
            logger.warning(f"Rate limit exceeded for {remote_ip}, rejecting")
            await ws.close(1008, "Rate limit exceeded")
            return
        
        try:
            # Wait for first message to identify client
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
                message = parse_message(raw)
            except (asyncio.TimeoutError, ProtocolError) as e:
                logger.warning(f"Client connection rejected: {e}")
                await ws.close(1008, "Identification timeout or protocol error")
                return

            # Auth check: if auth is enabled, validate token from first message
            if self._auth.enabled:
                provided_token = message.payload.get("auth_token", "")
                if not provided_token:
                    logger.warning(f"Client {remote_ip} sent no auth token (allowed)")
                else:
                    auth_result = self._auth.validate_token(provided_token)
                    if not auth_result.passed:
                        logger.warning(
                            f"Auth failed from {remote_ip}: {auth_result.reason}"
                        )
                        await ws.close(1008, "Authentication failed")
                        return

            client_type = self._detect_client_type(ws, message)
            client_id = self._generate_client_id(client_type, ws)
            
            client = ConnectedClient(
                websocket=ws,
                client_type=client_type,
                client_id=client_id,
                symbol=message.symbol,
                last_seen=now_ms(),
                last_sequence=message.sequence,
            )
            
            self.clients[client_id] = client
            logger.info(
                f"Client connected: {client_type.value} ({client_id}) "
                f"from {ws.remote_address}"
            )
            
            # Start heartbeat for this client
            await client.heartbeat.start(
                lambda msg: ws.send(serialize_message(msg))
            )
            
            # Fire connect callback
            if self._on_connect:
                await self._on_connect(client)
            
            # If event bus, publish connection event
            if self._event_bus:
                from backend.event_bus import EventType
                await self._event_bus.publish(
                    EventType.CONNECTION_RESTORED,
                    source="websocket_server",
                    payload={"client_id": client_id, "client_type": client_type.value}
                )
            
            # Process first message (we already read it)
            await self._process_message(client, message)
            
            # Main receive loop
            async for raw in ws:
                try:
                    message = parse_message(raw, client.validator)
                    await self._process_message(client, message)
                except ProtocolError as e:
                    logger.warning(f"Protocol error from {client_id}: {e}")
                    await self._send_error(ws, str(e))
                except Exception as e:
                    logger.error(f"Message processing error from {client_id}: {e}")
        
        except websockets.ConnectionClosed:
            logger.info(f"Client disconnected (normal): {client_id}")
        except Exception as e:
            logger.error(f"Client error ({client_id}): {e}")
        finally:
            if client_id:
                await self._remove_client(client_id)
    
    async def _process_message(self, client: ConnectedClient, message: ProtocolMessage) -> None:
        """Route incoming message to appropriate handler."""
        client.last_seen = now_ms()
        client.last_sequence = message.sequence
        client.heartbeat.record_received()

        # Update stats
        self._stats["total_messages"] += 1

        msg_type = message.message_type
        
        if msg_type == MessageType.HEARTBEAT:
            # Heartbeat received, acknowledge
            logger.debug(f"Heartbeat from {client.client_id}: {message.payload.get('source', '?')}")
            return
        
        elif msg_type == MessageType.MARKET_TICK:
            if self._on_tick:
                await self._on_tick(client, message)
        
        elif msg_type == MessageType.CANDLE_CLOSED:
            if self._on_candle:
                await self._on_candle(client, message)
        
        elif msg_type == MessageType.SYMBOL_INFO:
            if self._on_symbol_info:
                await self._on_symbol_info(client, message)
        
        elif msg_type == MessageType.CONNECTION_STATUS:
            status = message.payload.get("status", "unknown")
            logger.info(f"MT5 status update: {status}")
        
        elif msg_type == MessageType.CONFIG_UPDATE:
            if self._on_config_update:
                await self._on_config_update(client, message)
        
        elif msg_type == MessageType.CALIBRATE_OVERLAY:
            if self._on_calibrate:
                await self._on_calibrate(client, message)
        
        elif msg_type == MessageType.ACKNOWLEDGE:
            logger.debug(f"ACK from {client.client_id}: {message.payload}")
        
        else:
            logger.warning(f"Unhandled message type {msg_type} from {client.client_id}")
    
    async def _send_error(self, ws: WebSocketServerProtocol, error_text: str) -> None:
        """Send an error message to a client."""
        self._sequence += 1
        msg = create_message(
            message_type=MessageType.ERROR,
            sequence=self._sequence,
            payload={"error": error_text, "timestamp": now_ms()},
        )
        try:
            await ws.send(serialize_message(msg))
        except Exception:
            pass
    
    async def _remove_client(self, client_id: str) -> None:
        """Clean up a disconnected client."""
        client = self.clients.pop(client_id, None)
        if not client:
            return
        
        await client.heartbeat.stop()
        
        if self._on_disconnect:
            try:
                await self._on_disconnect(client)
            except Exception as e:
                logger.error(f"Disconnect callback error: {e}")
        
        if self._event_bus:
            from backend.event_bus import EventType
            await self._event_bus.publish(
                EventType.CONNECTION_LOST,
                source="websocket_server",
                payload={"client_id": client_id, "client_type": client.client_type.value}
            )
        
        logger.info(f"Client removed: {client_id}")
    
    async def broadcast_to_android(self, message: ProtocolMessage) -> None:
        """Broadcast a message to all connected Android clients."""
        data = serialize_message(message)
        android_clients = [
            c for c in self.clients.values()
            if c.client_type == ClientType.ANDROID
        ]
        
        if not android_clients:
            logger.debug("No Android clients connected for broadcast")
            return
        
        disconnected = []
        for client in android_clients:
            try:
                await client.websocket.send(data)
                client.last_seen = now_ms()
            except websockets.ConnectionClosed:
                disconnected.append(client.client_id)
            except Exception as e:
                logger.error(f"Broadcast error to {client.client_id}: {e}")
                disconnected.append(client.client_id)
        
        for cid in disconnected:
            await self._remove_client(cid)
    
    async def send_to_client(self, client_id: str, message: ProtocolMessage) -> bool:
        """Send a message to a specific client."""
        client = self.clients.get(client_id)
        if not client:
            logger.warning(f"Client {client_id} not found")
            return False
        
        try:
            await client.websocket.send(serialize_message(message))
            client.last_seen = now_ms()
            return True
        except Exception as e:
            logger.error(f"Send error to {client_id}: {e}")
            await self._remove_client(client_id)
            return False
    
    async def broadcast_signal(self, signal_payload: dict) -> None:
        """Broadcast a trading signal to all Android clients."""
        self._sequence += 1
        msg = create_message(
            message_type=MessageType.SIGNAL_CREATED,
            sequence=self._sequence,
            payload=signal_payload,
        )
        await self.broadcast_to_android(msg)
    
    async def broadcast_signal_update(self, signal_payload: dict) -> None:
        """Broadcast signal update to all Android clients."""
        self._sequence += 1
        msg = create_message(
            message_type=MessageType.SIGNAL_UPDATED,
            sequence=self._sequence,
            payload=signal_payload,
        )
        await self.broadcast_to_android(msg)
    
    async def broadcast_signal_invalidation(self, signal_id: str, reason: str) -> None:
        """Broadcast signal invalidation to all Android clients."""
        self._sequence += 1
        msg = create_message(
            message_type=MessageType.SIGNAL_INVALIDATED,
            sequence=self._sequence,
            payload={"signal_id": signal_id, "reason": reason},
        )
        await self.broadcast_to_android(msg)
    
    async def broadcast_snapshot(self, snapshot_payload: dict) -> None:
        """Broadcast market snapshot to all Android clients."""
        self._sequence += 1
        msg = create_message(
            message_type=MessageType.MARKET_SNAPSHOT,
            sequence=self._sequence,
            payload=snapshot_payload,
        )
        await self.broadcast_to_android(msg)
    
    async def broadcast_system_status(self, status_payload: dict) -> None:
        """Broadcast system status to all Android clients."""
        self._sequence += 1
        msg = create_message(
            message_type=MessageType.SYSTEM_STATUS,
            sequence=self._sequence,
            payload=status_payload,
        )
        await self.broadcast_to_android(msg)
    
    async def _stale_check_loop(self) -> None:
        """Periodically check for stale MT5 EA clients (not Android consumers)."""
        while self._running:
            await asyncio.sleep(5.0)
            
            now = now_ms()
            stale_clients = []
            
            for client_id, client in self.clients.items():
                # Only disconnect MT5 EA if stale — Android is a consumer, not data source
                if client.client_type == ClientType.MT5_EA:
                    age = now - client.last_seen
                    if age > self.stale_timeout:
                        stale_clients.append(client_id)
                        logger.warning(
                            f"Stale MT5 client detected: {client_id} "
                            f"(last seen {age}ms ago)"
                        )
            
            for client_id in stale_clients:
                await self._remove_client(client_id)
    
    def get_status(self) -> dict:
        """Get server status."""
        clients_info = {}
        for cid, c in self.clients.items():
            clients_info[cid] = {
                "type": c.client_type.value,
                "symbol": c.symbol,
                "last_seen": c.last_seen,
                "last_sequence": c.last_sequence,
                "is_stale": c.is_stale,
                "remote": str(c.websocket.remote_address) if c.websocket.remote_address else "unknown",
            }

        uptime = 0.0
        if self._stats["uptime_start"] > 0:
            uptime = time.time() - self._stats["uptime_start"]

        return {
            "running": self._running,
            "host": self.host,
            "port": self.port,
            "total_clients": len(self.clients),
            "mt5_clients": sum(1 for c in self.clients.values() if c.client_type == ClientType.MT5_EA),
            "android_clients": sum(1 for c in self.clients.values() if c.client_type == ClientType.ANDROID),
            "sequence": self._sequence,
            "clients": clients_info,
            "stats": {
                "total_messages": self._stats["total_messages"],
                "messages_per_minute": round(
                    self._stats["total_messages"] / (uptime / 60.0), 1
                ) if uptime > 60 else self._stats["total_messages"],
                "uptime_seconds": round(uptime, 1),
            },
            "auth_enabled": self._auth.enabled,
        }