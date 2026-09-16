"""
NEXUS OVERLAY AI - State Resync

When an Android client connects or reconnects, it must receive the full
current system state immediately so the overlay can render accurately
without waiting for the next broadcast cycle.

Resync payload types:
  CURRENT_SYSTEM_STATUS    — MT5 connection, data health, engine state
  CURRENT_MARKET_SNAPSHOT  — Latest atomic snapshot (price, candles, indicators)
  CURRENT_ACTIVE_SIGNAL    — The most recent actionable signal (if any)
  CURRENT_SIGNAL_STATE     — Lifecycle state of the active signal
  CURRENT_SERVER_TIME      — VPS clock for time-sync calibration

Design ref: audit sections XLIV, 47 (state resync on reconnect, atomic snapshot)
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional, TYPE_CHECKING

from backend.models import MessageType, now_ms, SignalLifecycleState

if TYPE_CHECKING:
    from backend.engines.market_snapshot import MarketSnapshot
    from backend.transport.websocket_server import NexusWebSocketServer

logger = logging.getLogger(__name__)


class ResyncPayloadType:
    """Identifiers for resync message sub-types."""
    CURRENT_SYSTEM_STATUS = "CURRENT_SYSTEM_STATUS"
    CURRENT_MARKET_SNAPSHOT = "CURRENT_MARKET_SNAPSHOT"
    CURRENT_ACTIVE_SIGNAL = "CURRENT_ACTIVE_SIGNAL"
    CURRENT_SIGNAL_STATE = "CURRENT_SIGNAL_STATE"
    CURRENT_SERVER_TIME = "CURRENT_SERVER_TIME"


class StateResync:
    """
    Sends the full current system state to an Android client on connect.

    Usage:
        resync = StateResync(ws_server, state_provider)
        await resync.send_full_state(client)

    The state_provider is a callback object that returns the current values:
        - system_status() -> dict
        - latest_snapshot() -> Optional[MarketSnapshot]
        - active_signal() -> Optional[dict]
        - signal_state() -> str (lifecycle state)
    """

    def __init__(
        self,
        ws_server: NexusWebSocketServer,
        state_provider: Optional[Any] = None,
    ) -> None:
        self._ws = ws_server
        self._provider = state_provider
        self._logger = logging.getLogger("nexus.transport.state_resync")

    def set_state_provider(self, provider: Any) -> None:
        """Set the state provider callback object."""
        self._provider = provider

    async def send_full_state(self, client_id: str) -> bool:
        """
        Send all current state messages to a specific client.

        Returns True if all messages were sent successfully.
        """
        sent_count = 0
        total = 5

        try:
            # 1. CURRENT_SERVER_TIME — send first so client can calibrate clock
            await self._send_server_time(client_id)
            sent_count += 1

            # 2. CURRENT_SYSTEM_STATUS — client needs to know if system is live
            await self._send_system_status(client_id)
            sent_count += 1

            # 3. CURRENT_MARKET_SNAPSHOT — the latest price/data state
            await self._send_market_snapshot(client_id)
            sent_count += 1

            # 4. CURRENT_ACTIVE_SIGNAL — the most recent actionable signal
            await self._send_active_signal(client_id)
            sent_count += 1

            # 5. CURRENT_SIGNAL_STATE — lifecycle state of the signal
            await self._send_signal_state(client_id)
            sent_count += 1

            self._logger.info(
                f"State resync complete for {client_id}: "
                f"{sent_count}/{total} messages sent"
            )
            return sent_count == total

        except Exception as e:
            self._logger.error(f"State resync failed for {client_id}: {e}")
            return False

    async def send_broadcast_state(self) -> bool:
        """
        Broadcast current state to ALL connected Android clients.
        Useful on system startup or after major state change.
        """
        android_clients = [
            cid for cid, c in self._ws.clients.items()
            if c.client_type.value == "ANDROID"
        ]

        if not android_clients:
            self._logger.debug("No Android clients for broadcast resync")
            return True

        success_count = 0
        for cid in android_clients:
            if await self.send_full_state(cid):
                success_count += 1

        return success_count == len(android_clients)

    async def _send_server_time(self, client_id: str) -> None:
        """Send CURRENT_SERVER_TIME for client clock calibration."""
        self._ws._sequence += 1
        from backend.transport.protocol import create_message, serialize_message

        msg = create_message(
            message_type=MessageType.SYSTEM_STATUS,
            sequence=self._ws._sequence,
            payload={
                "resync_type": ResyncPayloadType.CURRENT_SERVER_TIME,
                "server_time_ms": now_ms(),
                "server_utc_offset": time.timezone,
            },
        )
        client = self._ws.clients.get(client_id)
        if client:
            await client.websocket.send(serialize_message(msg))

    async def _send_system_status(self, client_id: str) -> None:
        """Send CURRENT_SYSTEM_STATUS."""
        status_data: Dict[str, Any] = {}
        if self._provider and hasattr(self._provider, "system_status"):
            status_data = self._provider.system_status() or {}

        self._ws._sequence += 1
        from backend.transport.protocol import create_message, serialize_message

        msg = create_message(
            message_type=MessageType.SYSTEM_STATUS,
            sequence=self._ws._sequence,
            payload={
                "resync_type": ResyncPayloadType.CURRENT_SYSTEM_STATUS,
                "data": status_data,
            },
        )
        client = self._ws.clients.get(client_id)
        if client:
            await client.websocket.send(serialize_message(msg))

    async def _send_market_snapshot(self, client_id: str) -> None:
        """Send CURRENT_MARKET_SNAPSHOT — the latest atomic snapshot."""
        snapshot_data: Optional[Dict[str, Any]] = None
        if self._provider and hasattr(self._provider, "latest_snapshot"):
            snapshot = self._provider.latest_snapshot()
            if snapshot is not None and hasattr(snapshot, "to_dict"):
                snapshot_data = snapshot.to_dict()

        if snapshot_data is None:
            self._logger.debug(f"No snapshot available for resync to {client_id}")
            return

        self._ws._sequence += 1
        from backend.transport.protocol import create_message, serialize_message

        msg = create_message(
            message_type=MessageType.MARKET_SNAPSHOT,
            sequence=self._ws._sequence,
            payload={
                "resync_type": ResyncPayloadType.CURRENT_MARKET_SNAPSHOT,
                "data": snapshot_data,
            },
        )
        client = self._ws.clients.get(client_id)
        if client:
            await client.websocket.send(serialize_message(msg))

    async def _send_active_signal(self, client_id: str) -> None:
        """Send CURRENT_ACTIVE_SIGNAL — the most recent trading signal."""
        signal_data: Optional[Dict[str, Any]] = None
        if self._provider and hasattr(self._provider, "active_signal"):
            signal_data = self._provider.active_signal()

        if signal_data is None:
            self._logger.debug(f"No active signal for resync to {client_id}")
            return

        self._ws._sequence += 1
        from backend.transport.protocol import create_message, serialize_message

        msg = create_message(
            message_type=MessageType.SIGNAL_CREATED,
            sequence=self._ws._sequence,
            payload={
                "resync_type": ResyncPayloadType.CURRENT_ACTIVE_SIGNAL,
                "data": signal_data,
            },
        )
        client = self._ws.clients.get(client_id)
        if client:
            await client.websocket.send(serialize_message(msg))

    async def _send_signal_state(self, client_id: str) -> None:
        """Send CURRENT_SIGNAL_STATE — lifecycle state of active signal."""
        state_str = SignalLifecycleState.NEW.value
        if self._provider and hasattr(self._provider, "signal_state"):
            state_str = self._provider.signal_state() or state_str

        self._ws._sequence += 1
        from backend.transport.protocol import create_message, serialize_message

        msg = create_message(
            message_type=MessageType.SIGNAL_UPDATED,
            sequence=self._ws._sequence,
            payload={
                "resync_type": ResyncPayloadType.CURRENT_SIGNAL_STATE,
                "signal_state": state_str,
            },
        )
        client = self._ws.clients.get(client_id)
        if client:
            await client.websocket.send(serialize_message(msg))
