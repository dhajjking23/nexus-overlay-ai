"""
NEXUS OVERLAY AI - Engine Health Tracker

Provides ``EngineHealth`` to track the operational state of every engine.
Critical engines must NEVER silently swallow exceptions — errors must
propagate to the health tracker so the system can degrade gracefully
instead of producing decisions on corrupted data.

States:
    READY    — last cycle succeeded
    DEGRADED — last cycle had a non-critical error
    ERROR    — last cycle raised an unhandled exception
    OFFLINE  — engine has never started or was explicitly stopped

Design ref: audit section 32 (no silent exception swallowing for critical engines)
"""
from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class EngineHealthState(Enum):
    """Operational state of an engine."""
    READY = "READY"
    DEGRADED = "DEGRADED"
    ERROR = "ERROR"
    OFFLINE = "OFFLINE"


@dataclass
class EngineHealth:
    """Tracks health state for a single engine."""
    name: str
    state: EngineHealthState = EngineHealthState.OFFLINE
    last_success_ms: int = 0
    last_error_ms: int = 0
    last_error_msg: str = ""
    error_count: int = 0
    cycle_count: int = 0

    def record_success(self) -> None:
        """Record a successful cycle."""
        self.cycle_count += 1
        self.last_success_ms = int(time.time() * 1000)
        self.state = EngineHealthState.READY

    def record_error(self, msg: str = "") -> None:
        """Record a failed cycle."""
        self.error_count += 1
        self.last_error_ms = int(time.time() * 1000)
        self.last_error_msg = msg
        self.state = EngineHealthState.ERROR
        logger.error(f"Engine {self.name} error [{self.error_count}]: {msg}")

    def record_degraded(self, msg: str = "") -> None:
        """Record a non-critical degradation."""
        self.last_error_ms = int(time.time() * 1000)
        self.last_error_msg = msg
        self.state = EngineHealthState.DEGRADED
        logger.warning(f"Engine {self.name} degraded: {msg}")

    def set_offline(self) -> None:
        """Mark engine as offline."""
        self.state = EngineHealthState.OFFLINE

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "last_success_ms": self.last_success_ms,
            "last_error_ms": self.last_error_ms,
            "last_error_msg": self.last_error_msg,
            "error_count": self.error_count,
            "cycle_count": self.cycle_count,
        }


class EngineHealthTracker:
    """Global registry of all engine health states.

    Usage::

        tracker = EngineHealthTracker()
        tracker.register("indicator_engine")

        # In engine cycle:
        try:
            ...
            tracker.get("indicator_engine").record_success()
        except Exception as e:
            tracker.get("indicator_engine").record_error(str(e))
    """

    def __init__(self) -> None:
        self._engines: Dict[str, EngineHealth] = {}

    def register(self, name: str) -> EngineHealth:
        """Register and return an EngineHealth for *name*."""
        if name not in self._engines:
            self._engines[name] = EngineHealth(name=name)
        return self._engines[name]

    def get(self, name: str) -> EngineHealth:
        """Get (or auto-register) an EngineHealth for *name*."""
        return self._engines.setdefault(name, EngineHealth(name=name))

    @property
    def all_healthy(self) -> bool:
        """True if every registered engine is READY."""
        return all(
            h.state == EngineHealthState.READY for h in self._engines.values()
        )

    def summary(self) -> Dict[str, str]:
        """Return {engine_name: state_value} for all engines."""
        return {name: h.state.value for name, h in self._engines.items()}

    def to_dict(self) -> dict:
        return {name: h.to_dict() for name, h in self._engines.items()}


# ── Global singleton ─────────────────────────────────────────────
_tracker: Optional[EngineHealthTracker] = None


def get_health_tracker() -> EngineHealthTracker:
    """Get the global engine health tracker."""
    global _tracker
    if _tracker is None:
        _tracker = EngineHealthTracker()
    return _tracker


def reset_health_tracker() -> None:
    """Reset the global health tracker (primarily for tests)."""
    global _tracker
    _tracker = None
