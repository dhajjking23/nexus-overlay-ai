"""
NEXUS OVERLAY AI - Session Engine
Detects Asian/London/NewYork/Overlap trading sessions using IANA timezones with DST support.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

DEFAULT_SESSIONS = {
    "asian": {"start": "00:00", "end": "06:00", "timezone": "Asia/Tokyo"},
    "london": {"start": "07:00", "end": "16:00", "timezone": "Europe/London"},
    "new_york": {"start": "13:00", "end": "22:00", "timezone": "America/New_York"},
    "overlap": {"start": "13:00", "end": "16:00", "timezone": "Europe/London"},
}


class SessionEngine:
    def __init__(self, config: dict[str, Any] | None = None, event_bus=None):
        self._config = config or {}
        self._event_bus = event_bus
        sc = self._config.get("sessions", {})
        self._broker_timezone = sc.get("broker_timezone", "UTC")
        self._sessions = sc.get("sessions", DEFAULT_SESSIONS)

    def _parse_time(self, time_str: str) -> tuple[int, int]:
        """Parse HH:MM string to (hour, minute)."""
        try:
            parts = time_str.split(":")
            return int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            return 0, 0

    def _is_in_session(self, dt: datetime, session: dict) -> bool:
        """Check if datetime is within session, handling midnight crossover."""
        tz_name = session.get("timezone", "UTC")
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            logger.warning(f"Unknown timezone {tz_name}, using UTC")
            tz = timezone.utc

        # Convert to session's timezone
        local_dt = dt.astimezone(tz)
        start_h, start_m = self._parse_time(session.get("start", "00:00"))
        end_h, end_m = self._parse_time(session.get("end", "24:00"))

        start_min = start_h * 60 + start_m
        end_min = end_h * 60 + end_m
        current_min = local_dt.hour * 60 + local_dt.minute

        if start_min <= end_min:
            # Normal session (e.g., 07:00-16:00)
            return start_min <= current_min < end_min
        else:
            # Midnight crossover (e.g., 22:00-04:00)
            return current_min >= start_min or current_min < end_min

    def analyze(self, timestamp_ms: int | None = None) -> dict:
        if timestamp_ms is None:
            dt = datetime.now(timezone.utc)
        else:
            dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)

        active_sessions: list[str] = []
        for name, sess in self._sessions.items():
            if self._is_in_session(dt, sess):
                active_sessions.append(name)

        # Determine primary session
        primary = "off"
        if "overlap" in active_sessions:
            primary = "overlap"
        elif "new_york" in active_sessions:
            primary = "new_york"
        elif "london" in active_sessions:
            primary = "london"
        elif "asian" in active_sessions:
            primary = "asian"

        # Also get broker local time for display
        try:
            broker_tz = ZoneInfo(self._broker_timezone)
        except Exception:
            broker_tz = timezone.utc
        broker_dt = dt.astimezone(broker_tz)

        return {
            "active_sessions": active_sessions,
            "primary_session": primary,
            "broker_hour": broker_dt.hour,
            "broker_minute": broker_dt.minute,
            "broker_time": broker_dt.strftime("%H:%M"),
            "broker_timezone": self._broker_timezone,
            "is_trading_hours": len(active_sessions) > 0,
            "session_active": primary != "off",
        }
