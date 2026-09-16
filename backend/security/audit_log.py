"""
NEXUS OVERLAY AI - Security Audit Log

Records security-relevant events for monitoring and forensics:
- Authentication attempts (success/failure)
- Rate limit hits and rejections
- Malformed message rejections
- Suspicious patterns (replay attacks, invalid HMAC, etc.)
- Payload size violations
"""
from __future__ import annotations

import json
import logging
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional


logger = logging.getLogger(__name__)


class AuditEventType(Enum):
    """Types of security audit events."""
    AUTH_SUCCESS = "AUTH_SUCCESS"
    AUTH_FAILURE = "AUTH_FAILURE"
    AUTH_NO_TOKEN = "AUTH_NO_TOKEN"
    RATE_LIMIT_HIT = "RATE_LIMIT_HIT"
    RATE_LIMIT_REJECTED = "RATE_LIMIT_REJECTED"
    MALFORMED_MESSAGE = "MALFORMED_MESSAGE"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    INVALID_HMAC = "INVALID_HMAC"
    REPLAY_ATTACK = "REPLAY_ATTACK"
    DUPLICATE_MESSAGE_ID = "DUPLICATE_MESSAGE_ID"
    STALE_TIMESTAMP = "STALE_TIMESTAMP"
    INVALID_NONCE = "INVALID_NONCE"
    SUSPICIOUS_PATTERN = "SUSPICIOUS_PATTERN"
    CONNECTION_REJECTED = "CONNECTION_REJECTED"
    SECURITY_VALIDATION_FAILED = "SECURITY_VALIDATION_FAILED"


@dataclass
class AuditEvent:
    """A single security audit event."""
    timestamp: float
    event_type: AuditEventType
    source_ip: str = "unknown"
    client_id: str = ""
    message_id: str = ""
    details: str = ""
    severity: str = "INFO"  # INFO, WARNING, CRITICAL

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "event_type": self.event_type.value,
            "source_ip": self.source_ip,
            "client_id": self.client_id,
            "message_id": self.message_id,
            "details": self.details,
            "severity": self.severity,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


class SecurityAuditLog:
    """
    Security audit logging system.

    Maintains an in-memory ring buffer of recent events and supports
    pattern detection for suspicious activity (e.g., repeated auth failures
    from the same IP, which may indicate brute-force attempts).

    Usage:
        audit = SecurityAuditLog(max_events=10000)
        audit.log_event(AuditEventType.AUTH_FAILURE, source_ip="10.0.0.5")
        audit.log_event(AuditEventType.RATE_LIMIT_REJECTED, source_ip="10.0.0.5")
        suspicious = audit.check_suspicious_patterns("10.0.0.5")
    """

    def __init__(
        self,
        max_events: int = 10000,
        brute_force_threshold: int = 10,
        brute_force_window_s: float = 300.0,
    ):
        """
        Args:
            max_events: Maximum events to keep in the ring buffer.
            brute_force_threshold: Number of auth failures before flagging IP.
            brute_force_window_s: Time window for brute-force detection (seconds).
        """
        self._max_events = max_events
        self._brute_force_threshold = brute_force_threshold
        self._brute_force_window_s = brute_force_window_s
        self._events: deque[AuditEvent] = deque(maxlen=max_events)
        # Per-IP auth failure tracking for brute-force detection
        self._auth_failures: dict[str, list[float]] = {}
        # Aggregate counters
        self._counters: dict[str, int] = {}

    def log_event(
        self,
        event_type: AuditEventType,
        source_ip: str = "unknown",
        client_id: str = "",
        message_id: str = "",
        details: str = "",
        severity: str = "INFO",
    ) -> AuditEvent:
        """
        Log a security audit event.

        Returns the created AuditEvent.
        """
        now = time.time()
        event = AuditEvent(
            timestamp=now,
            event_type=event_type,
            source_ip=source_ip,
            client_id=client_id,
            message_id=message_id,
            details=details,
            severity=severity,
        )
        self._events.append(event)

        # Update counters
        counter_key = event_type.value
        self._counters[counter_key] = self._counters.get(counter_key, 0) + 1

        # Log to Python logger
        log_fn = logger.warning if severity in ("WARNING", "CRITICAL") else logger.info
        log_fn(
            f"[SECURITY] {event_type.value} from {source_ip}: {details}"
        )

        # Track auth failures for brute-force detection
        if event_type in (
            AuditEventType.AUTH_FAILURE,
            AuditEventType.INVALID_HMAC,
        ):
            self._track_auth_failure(source_ip, now)

        return event

    def _track_auth_failure(self, ip: str, now: float) -> None:
        """Track auth failures per IP for brute-force detection."""
        if ip not in self._auth_failures:
            self._auth_failures[ip] = []
        self._auth_failures[ip].append(now)
        # Prune old entries
        cutoff = now - self._brute_force_window_s
        self._auth_failures[ip] = [
            t for t in self._auth_failures[ip] if t > cutoff
        ]

    def check_suspicious_patterns(self, ip: str) -> bool:
        """
        Check if an IP shows suspicious patterns (e.g., brute-force).
        Returns True if suspicious.
        """
        failures = self._auth_failures.get(ip, [])
        if len(failures) >= self._brute_force_threshold:
            self.log_event(
                AuditEventType.SUSPICIOUS_PATTERN,
                source_ip=ip,
                details=(
                    f"Possible brute-force: {len(failures)} auth failures "
                    f"in {self._brute_force_window_s}s"
                ),
                severity="CRITICAL",
            )
            return True
        return False

    def get_events(
        self,
        event_type: Optional[AuditEventType] = None,
        source_ip: Optional[str] = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """Query events with optional filters."""
        result = list(self._events)
        if event_type:
            result = [e for e in result if e.event_type == event_type]
        if source_ip:
            result = [e for e in result if e.source_ip == source_ip]
        return result[-limit:]

    def get_counters(self) -> dict[str, int]:
        """Get aggregate event counters."""
        return dict(self._counters)

    def get_total_events(self) -> int:
        """Get total number of events in the buffer."""
        return len(self._events)

    def clear(self) -> None:
        """Clear all events and counters (for testing)."""
        self._events.clear()
        self._auth_failures.clear()
        self._counters.clear()
