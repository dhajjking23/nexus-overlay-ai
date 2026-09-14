"""
NEXUS OVERLAY AI - Session Engine
Detects Asian/London/NewYork/Overlap trading sessions.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_SESSIONS = {
    "asian": {"start_hour": 0, "end_hour": 6, "tz_offset": 9},
    "london": {"start_hour": 7, "end_hour": 16, "tz_offset": 0},
    "new_york": {"start_hour": 13, "end_hour": 22, "tz_offset": -5},
    "overlap": {"start_hour": 13, "end_hour": 16, "tz_offset": 0},
}


class SessionEngine:
    def __init__(self, config: dict[str, Any] | None = None, event_bus=None):
        self._config = config or {}
        self._event_bus = event_bus
        sc = self._config.get("sessions", {})
        self._broker_tz_offset = sc.get("broker_tz_offset", 0)
        self._sessions = sc.get("sessions", DEFAULT_SESSIONS)

    def analyze(self, timestamp_ms: int | None = None) -> dict:
        if timestamp_ms is None:
            dt = datetime.now(timezone.utc)
        else:
            dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        broker_dt = dt + timedelta(seconds=self._broker_tz_offset * 3600)
        hour = broker_dt.hour
        active_sessions: list[str] = []
        for name, sess in self._sessions.items():
            start = sess.get("start_hour", 0)
            end = sess.get("end_hour", 24)
            if start <= hour < end:
                active_sessions.append(name)
        primary = "off" if not active_sessions else (
            "overlap" if "overlap" in active_sessions else active_sessions[-1])
        return {
            "active_sessions": active_sessions,
            "primary_session": primary,
            "broker_hour": hour,
            "broker_time": broker_dt.strftime("%H:%M"),
            "is_trading_hours": len(active_sessions) > 0,
            "session_active": primary != "off",
        }
