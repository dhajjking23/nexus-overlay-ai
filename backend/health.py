"""
NEXUS OVERLAY AI - Health Check Server

Lightweight HTTP server for health checks and system status.
Uses aiohttp.web for minimal overhead.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional

from aiohttp import web

logger = logging.getLogger(__name__)

# Version pulled from config or default
DEFAULT_VERSION = "1.0.0"


class HealthServer:
    """
    Lightweight HTTP health-check server.
    
    Endpoints:
        GET /health  — quick health check (JSON)
        GET /status  — full system status (JSON)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        transport_cfg = cfg.get("transport", {})
        system_cfg = cfg.get("system", {})

        self._port: int = int(transport_cfg.get("health_port", 8766))
        self._host: str = transport_cfg.get("host", "0.0.0.0")
        self._version: str = system_cfg.get("version", DEFAULT_VERSION)
        self._enabled: bool = system_cfg.get("health_check_enabled", True)

        self._start_time: float = time.time()
        self._status: Dict[str, Any] = {
            "engines_loaded": 0,
            "mt5_connected": False,
            "android_connected": False,
        }

        self._runner: Optional[web.AppRunner] = None
        self._app: Optional[web.Application] = None

    @property
    def port(self) -> int:
        return self._port

    def update_status(self, key: str, value: Any) -> None:
        """Update a status field (thread/async safe for simple values)."""
        self._status[key] = value
        logger.debug(f"Health status updated: {key}={value}")

    async def start(self) -> None:
        """Start the HTTP health-check server."""
        if not self._enabled:
            logger.info("Health check server disabled by config")
            return

        self._app = web.Application()
        self._app.router.add_get("/health", self._handle_health)
        self._app.router.add_get("/status", self._handle_status)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()
        logger.info(f"Health check server started on {self._host}:{self._port}")

    async def stop(self) -> None:
        """Stop the HTTP health-check server."""
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
            logger.info("Health check server stopped")

    async def _handle_health(self, request: web.Request) -> web.Response:
        """GET /health — lightweight health check."""
        uptime = time.time() - self._start_time
        body = {
            "status": "ok",
            "uptime_seconds": round(uptime, 1),
            "version": self._version,
            "engines_loaded": self._status.get("engines_loaded", 0),
            "mt5_connected": self._status.get("mt5_connected", False),
            "android_connected": self._status.get("android_connected", False),
        }
        return web.json_response(body, dumps=json.dumps)

    async def _handle_status(self, request: web.Request) -> web.Response:
        """GET /status — full system status."""
        uptime = time.time() - self._start_time
        body = {
            "status": "ok",
            "uptime_seconds": round(uptime, 1),
            "version": self._version,
        }
        # Merge in all tracked status keys
        body.update(self._status)
        return web.json_response(body, dumps=json.dumps)
