"""
NEXUS OVERLAY AI - HTTP Bridge Server

Lightweight HTTP server that accepts JSON protocol messages from the MQL5 EA.
The EA cannot use WebSocket, so this bridge receives HTTP POST pushes and
routes them through the same pipeline as WebSocket messages.

Endpoints:
  POST /message — Receives JSON protocol messages from MT5 EA
  GET  /         — Simple status page

Uses aiohttp.web for minimal overhead.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, Optional

from aiohttp import web

from backend.models import MessageType, ProtocolMessage, now_ms
from backend.auth import TokenAuth

logger = logging.getLogger(__name__)


# Type alias matching WebSocket server convention
MessageHandler = Callable[[Any, ProtocolMessage], Awaitable[None]]


@dataclass
class HTTPClient:
    """
    Lightweight stub that mimics the ConnectedClient interface expected
    by NexusOverlayApp._on_tick / _on_candle / _on_symbol_info.

    Each HTTP request creates a fresh instance — there is no persistent
    connection state.
    """
    client_id: str
    client_type: str = "MT5_EA"
    symbol: str = "XAUUSD"
    last_seen: int = field(default_factory=now_ms)
    last_sequence: int = 0
    metadata: dict = field(default_factory=dict)


class _RateLimiter:
    """
    Simple in-memory per-IP sliding-window rate limiter.
    Counts requests in a 60-second window. Max 60 requests/min/IP.
    """

    def __init__(self, max_per_minute: int = 60) -> None:
        self._max = max_per_minute
        # {ip: [timestamp, ...]} — list of request timestamps in the window
        self._hits: dict[str, list[float]] = {}

    def is_allowed(self, ip: str) -> bool:
        now = time.monotonic()
        window_start = now - 60.0
        hits = self._hits.get(ip, [])
        # Prune old entries
        hits = [t for t in hits if t > window_start]
        if len(hits) >= self._max:
            self._hits[ip] = hits
            return False
        hits.append(now)
        self._hits[ip] = hits
        return True

    def cleanup(self, max_age: float = 300.0) -> int:
        """Remove stale entries. Returns count removed."""
        now = time.monotonic()
        stale = [ip for ip, hits in self._hits.items()
                 if not hits or (now - hits[-1]) > max_age]
        for ip in stale:
            del self._hits[ip]
        return len(stale)


class HTTPBridgeServer:
    """
    HTTP Bridge for the MQL5 Expert Advisor.

    The EA sends JSON protocol messages via POST /message.  This server
    parses them into ProtocolMessage instances and dispatches to the same
    callback handlers used by the WebSocket server.

    Configuration keys (inside the transport section of the config dict):
        transport.host          — bind address  (default 0.0.0.0)
        transport.http_port     — port           (default 8767)
        transport.http_bridge_enabled — bool     (default True)
        system.secret_key       — Bearer token   (empty = no auth)
    """

    def __init__(self, config: Optional[dict] = None) -> None:
        cfg = config or {}
        transport_cfg = cfg.get("transport", {})
        system_cfg = cfg.get("system", {})

        self.host: str = transport_cfg.get("host", "0.0.0.0")
        env_port = os.environ.get("HTTP_BRIDGE_PORT")
        self.port: int = int(env_port if env_port else transport_cfg.get("http_port", 8767))
        self._enabled: bool = transport_cfg.get("http_bridge_enabled", True)

        # Auth
        self._auth = TokenAuth(config=cfg)

        # Rate limiter (60 req/min/IP)
        self._rate_limiter = _RateLimiter(max_per_minute=60)

        # Callbacks
        self._on_tick: Optional[MessageHandler] = None
        self._on_candle: Optional[MessageHandler] = None
        self._on_symbol_info: Optional[MessageHandler] = None

        # Server internals
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._running = False
        self._start_time = 0.0

        # Stats
        self._sequence: int = 0
        self._total_messages: int = 0
        self._total_rejected: int = 0

    # ------------------------------------------------------------------
    # Callback registration
    # ------------------------------------------------------------------
    def on_tick(self, handler: MessageHandler) -> None:
        """Register a handler for MARKET_TICK messages."""
        self._on_tick = handler

    def on_candle(self, handler: MessageHandler) -> None:
        """Register a handler for CANDLE_CLOSED messages."""
        self._on_candle = handler

    def on_symbol_info(self, handler: MessageHandler) -> None:
        """Register a handler for SYMBOL_INFO messages."""
        self._on_symbol_info = handler

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def start(self) -> None:
        """Start the HTTP bridge server."""
        if not self._enabled:
            logger.info("HTTP bridge server disabled by config")
            return

        self._app = web.Application()
        self._app.router.add_get("/", self._handle_status_page)
        self._app.router.add_post("/message", self._handle_message)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()

        self._running = True
        self._start_time = time.time()
        logger.info(
            f"HTTP bridge server started on {self.host}:{self.port} "
            f"(auth={'enabled' if self._auth.enabled else 'disabled'})"
        )

    async def stop(self) -> None:
        """Stop the HTTP bridge server gracefully."""
        self._running = False
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
            logger.info("HTTP bridge server stopped")

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    def get_status(self) -> dict:
        """Return server status dict."""
        uptime = time.time() - self._start_time if self._start_time else 0.0
        return {
            "running": self._running,
            "host": self.host,
            "port": self.port,
            "auth_enabled": self._auth.enabled,
            "total_messages": self._total_messages,
            "total_rejected": self._total_rejected,
            "sequence": self._sequence,
            "uptime_seconds": round(uptime, 1),
        }

    # ------------------------------------------------------------------
    # Request handlers
    # ------------------------------------------------------------------
    async def _handle_status_page(self, request: web.Request) -> web.Response:
        """GET / — Simple status page."""
        status = self.get_status()
        return web.json_response(
            {"service": "nexus-overlay-http-bridge", **status},
            dumps=json.dumps,
        )

    async def _handle_message(self, request: web.Request) -> web.Response:
        """
        POST /message — Receive a JSON protocol message from the MT5 EA.

        Flow:
          1. Rate-limit check
          2. Auth check (if configured)
          3. Parse JSON body
          4. Create ProtocolMessage
          5. Dispatch to registered handler
          6. Return acknowledgement
        """
        # --- Rate limit ---
        client_ip = request.remote or "unknown"
        if not self._rate_limiter.is_allowed(client_ip):
            self._total_rejected += 1
            logger.warning(f"Rate limit exceeded for {client_ip}")
            return web.json_response(
                {"status": "error", "error": "Rate limit exceeded"},
                status=429,
            )

        # --- Auth ---
        if self._auth.enabled:
            auth_header = request.headers.get("Authorization", "")
            token = ""
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
            auth_result = self._auth.validate_token(token)
            if not auth_result.passed:
                self._total_rejected += 1
                logger.warning(
                    f"Auth failed from {client_ip}: {auth_result.reason}"
                )
                return web.json_response(
                    {"status": "error", "error": "Unauthorized"},
                    status=401,
                )

        # --- Parse body ---
        try:
            body_bytes = await request.read()
            if not body_bytes:
                return web.json_response(
                    {"status": "error", "error": "Empty request body"},
                    status=400,
                )
            data = json.loads(body_bytes)
        except json.JSONDecodeError as exc:
            self._total_rejected += 1
            logger.warning(f"Invalid JSON from {client_ip}: {exc}")
            return web.json_response(
                {"status": "error", "error": f"Invalid JSON: {exc}"},
                status=400,
            )
        except Exception as exc:
            self._total_rejected += 1
            logger.error(f"Error reading request body from {client_ip}: {exc}")
            return web.json_response(
                {"status": "error", "error": "Failed to read request body"},
                status=400,
            )

        # --- Validate required fields ---
        if not isinstance(data, dict):
            self._total_rejected += 1
            return web.json_response(
                {"status": "error", "error": "Request body must be a JSON object"},
                status=400,
            )

        message_type_str = data.get("message_type", "")
        if not message_type_str:
            self._total_rejected += 1
            return web.json_response(
                {"status": "error", "error": "Missing 'message_type' field"},
                status=400,
            )

        try:
            message_type = MessageType(message_type_str)
        except ValueError:
            self._total_rejected += 1
            logger.warning(f"Unknown message type from {client_ip}: {message_type_str}")
            return web.json_response(
                {"status": "error", "error": f"Unknown message_type: {message_type_str}"},
                status=400,
            )

        # --- Create ProtocolMessage ---
        try:
            message = ProtocolMessage(
                protocol_version=data.get("protocol_version", "1.0"),
                message_type=message_type,
                sequence=data.get("sequence", 0),
                symbol=data.get("symbol", "XAUUSD"),
                timeframe=data.get("timeframe", "M1"),
                timestamp=data.get("timestamp", now_ms()),
                payload=data.get("payload", {}),
                checksum=data.get("checksum", ""),
            )
        except Exception as exc:
            self._total_rejected += 1
            logger.error(f"Failed to create ProtocolMessage from {client_ip}: {exc}")
            return web.json_response(
                {"status": "error", "error": f"Message construction failed: {exc}"},
                status=400,
            )

        # --- Dispatch to handler ---
        self._total_messages += 1
        self._sequence = message.sequence or self._sequence

        # Create stub client for callback compatibility
        http_client = HTTPClient(
            client_id=f"http_{client_ip}_{int(time.time() * 1000)}",
            client_type="MT5_EA",
            symbol=message.symbol,
            last_seen=now_ms(),
            last_sequence=message.sequence,
        )

        logger.debug(
            f"HTTP message from {client_ip}: "
            f"type={message_type.value} symbol={message.symbol} "
            f"seq={message.sequence}"
        )

        try:
            await self._dispatch_message(http_client, message)
        except Exception as exc:
            logger.error(
                f"Handler error for {message_type.value} from {client_ip}: {exc}",
                exc_info=True,
            )
            # Still return 200 — the message was received and parsed.
            # Handler errors are not the EA's fault.

        return web.json_response(
            {
                "status": "ok",
                "sequence": message.sequence,
                "message_type": message_type.value,
            },
            status=200,
        )

    # ------------------------------------------------------------------
    # Message routing (mirrors WebSocket _process_message logic)
    # ------------------------------------------------------------------
    async def _dispatch_message(
        self, client: HTTPClient, message: ProtocolMessage
    ) -> None:
        """Route a parsed message to the appropriate registered handler."""
        msg_type = message.message_type

        if msg_type == MessageType.MARKET_TICK:
            if self._on_tick:
                await self._on_tick(client, message)
            else:
                logger.debug("MARKET_TICK received but no tick handler registered")

        elif msg_type == MessageType.CANDLE_CLOSED:
            if self._on_candle:
                await self._on_candle(client, message)
            else:
                logger.debug("CANDLE_CLOSED received but no candle handler registered")

        elif msg_type == MessageType.SYMBOL_INFO:
            if self._on_symbol_info:
                await self._on_symbol_info(client, message)
            else:
                logger.debug("SYMBOL_INFO received but no symbol_info handler registered")

        elif msg_type == MessageType.HEARTBEAT:
            logger.debug(
                f"Heartbeat from HTTP bridge: {message.payload.get('source', '?')}"
            )

        elif msg_type == MessageType.CONNECTION_STATUS:
            status = message.payload.get("status", "unknown")
            logger.info(f"MT5 status update (HTTP): {status}")

        else:
            logger.warning(
                f"Unhandled message type {msg_type.value} from HTTP bridge"
            )
