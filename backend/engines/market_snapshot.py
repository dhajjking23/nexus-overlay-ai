"""
NEXUS OVERLAY AI - Market Snapshot

The MarketSnapshot is an atomic snapshot of all market data at decision time.
It serves as the single source of truth for a decision cycle.

Every decision must reference its snapshot_id for audit and reproducibility.
No data can change after snapshot creation — this prevents TOCTOU bugs.

Design ref: audit sections 63, 64, 79 (decision audit trail, reproducibility)

Snapshot ID format: SNAP-{unix_ms}-{sequence}
Example: SNAP-1694890800123-0042
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# Global sequence counter for snapshot IDs
_snapshot_sequence: int = 0


def _next_sequence() -> int:
    """Get the next snapshot sequence number."""
    global _snapshot_sequence
    _snapshot_sequence += 1
    return _snapshot_sequence


def generate_snapshot_id() -> str:
    """Generate a unique snapshot ID: SNAP-{timestamp_ms}-{seq}."""
    ts_ms = int(time.time() * 1000)
    seq = _next_sequence()
    return f"SNAP-{ts_ms}-{seq:04d}"


@dataclass
class ClockDiscipline:
    """All timestamps for latency tracking.

    From audit section XVII: Must track broker_time, server_time,
    local_time, received_time, processed_time, decision_time.

    Latency chain:
      broker_time_ms  ──market_to_backend──▶  received_time_ms
                                              │
                                       processed_time_ms
                                              │
                                    ──analysis_latency──▶
                                              │
                                    ──decision_latency──▶ decision_time_ms
                                              │
                                  ──broadcast_latency──▶ broadcast_time_ms

    Total: end_to_end_latency = broker → broadcast
    """
    broker_time_ms: int = 0       # When the broker generated the tick/candle
    server_time_ms: int = 0       # VPS wall-clock when data object was created
    received_time_ms: int = 0     # When VPS received the data
    processed_time_ms: int = 0    # When engines started processing
    decision_time_ms: int = 0     # When decision was made
    broadcast_time_ms: int = 0    # When signal was broadcast to Android

    # ── Latency measurement properties ──────────────────────────────────

    @property
    def market_to_backend_ms(self) -> float:
        """Market (broker) → VPS receipt latency."""
        if self.received_time_ms > 0 and self.broker_time_ms > 0:
            return self.received_time_ms - self.broker_time_ms
        return 0.0

    @property
    def analysis_latency_ms(self) -> float:
        """Engine processing start → analysis complete (pre-decision)."""
        if self.decision_time_ms > 0 and self.processed_time_ms > 0:
            # Analysis is the bulk of processing before final decision
            return self.decision_time_ms - self.processed_time_ms
        return 0.0

    @property
    def decision_latency_ms(self) -> float:
        """Decision computation time (from processed to decision)."""
        if self.decision_time_ms > 0 and self.processed_time_ms > 0:
            return self.decision_time_ms - self.processed_time_ms
        return 0.0

    @property
    def broadcast_latency_ms(self) -> float:
        """Decision → broadcast to Android."""
        if self.broadcast_time_ms > 0 and self.decision_time_ms > 0:
            return self.broadcast_time_ms - self.decision_time_ms
        return 0.0

    @property
    def end_to_end_latency_ms(self) -> float:
        """Total latency from broker to broadcast. Primary KPI."""
        end = self.broadcast_time_ms if self.broadcast_time_ms > 0 else self.decision_time_ms
        if end > 0 and self.broker_time_ms > 0:
            return end - self.broker_time_ms
        return 0.0

    # ── Backward-compatible aliases ──────────────────────────────────────

    @property
    def ingestion_latency_ms(self) -> float:
        """Alias for market_to_backend_ms (backward compat)."""
        return self.market_to_backend_ms

    @property
    def processing_latency_ms(self) -> float:
        """Alias for analysis_latency_ms (backward compat)."""
        return self.analysis_latency_ms

    def snapshot(self) -> Dict[str, int]:
        """Return all timestamps as a dictionary for serialization."""
        return {
            "broker_time_ms": self.broker_time_ms,
            "server_time_ms": self.server_time_ms,
            "received_time_ms": self.received_time_ms,
            "processed_time_ms": self.processed_time_ms,
            "decision_time_ms": self.decision_time_ms,
            "broadcast_time_ms": self.broadcast_time_ms,
        }

    def latency_report(self) -> Dict[str, float]:
        """Return all latency measurements as a dictionary."""
        return {
            "market_to_backend_ms": self.market_to_backend_ms,
            "analysis_latency_ms": self.analysis_latency_ms,
            "decision_latency_ms": self.decision_latency_ms,
            "broadcast_latency_ms": self.broadcast_latency_ms,
            "end_to_end_latency_ms": self.end_to_end_latency_ms,
        }


@dataclass
class DataSource:
    """Tracks the source of market data — native vs derived."""
    source_type: str = "NATIVE"  # NATIVE (broker) or DERIVED (aggregated)
    formation_method: str = ""  # e.g. "broker_m1", "aggregated_from_m1_ticks"
    closed: bool = True
    first_tick_ms: int = 0
    last_tick_ms: int = 0
    broker_timestamp_ms: int = 0
    received_timestamp_ms: int = 0


@dataclass
class SymbolSpecification:
    """Dynamic broker symbol specification — source of truth, not config."""
    name: str = "XAUUSD"
    digits: int = 2
    point: float = 0.01
    tick_size: float = 0.01
    tick_value: float = 1.0
    contract_size: float = 100.0
    min_lot: float = 0.01
    max_lot: float = 100.0
    step_lot: float = 0.01
    spread: float = 0.0  # Current spread in points


@dataclass
class MarketSnapshot:
    """
    Atomic snapshot of all market data at decision time.

    This is THE single source of truth for a decision cycle.
    Created once, consumed by all engines, never modified after creation.

    The snapshot_id enables:
      - Decision reproducibility (section 64)
      - Audit trail (section 63)
      - AI snapshot caching (section 76)
      - State resync on reconnect (section 47)
    """

    # Identity
    snapshot_id: str = field(default_factory=generate_snapshot_id)
    symbol: str = "XAUUSD"
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    # Clock discipline
    clock: ClockDiscipline = field(default_factory=ClockDiscipline)

    # Symbol specification (from broker, not config)
    symbol_spec: SymbolSpecification = field(default_factory=SymbolSpecification)

    # Price data
    bid: float = 0.0
    ask: float = 0.0
    spread: float = 0.0
    last_price: float = 0.0

    # Tick data
    tick_volume: int = 0
    tick_flags: int = 0

    # Candle data (latest closed candle on each timeframe)
    candles: Dict[str, Dict[str, float]] = field(default_factory=dict)
    # e.g. {"M1": {"o": 1.0, "h": 2.0, "l": 0.5, "c": 1.8, "v": 100, "spread": 20}}

    # Data source tracking
    candle_sources: Dict[str, DataSource] = field(default_factory=dict)

    # Engine outputs (populated during analysis cycle)
    indicators: Dict[str, Any] = field(default_factory=dict)
    structure: Any = None  # MarketStructure
    liquidity: List[Any] = field(default_factory=list)  # List[LiquidityEvent]
    price_action: List[Any] = field(default_factory=list)  # List[PriceActionPattern]
    zones: List[Any] = field(default_factory=list)  # List[Zone]
    mtf: Any = None  # MultiTimeframeAnalysis
    session_active: bool = False
    session_name: str = ""
    regime: str = "UNCERTAIN"

    # Risk & quality metrics
    data_quality: float = 100.0  # 0-100 scale
    data_age_ms: int = 0

    # Market status
    market_open: bool = True
    transport_connected: bool = True

    # Connection health
    mt5_connected: bool = False
    mt5_last_heartbeat_ms: int = 0
    mt5_last_tick_ms: int = 0

    # Intermarket context (optional)
    intermarket: Dict[str, Any] = field(default_factory=dict)
    # e.g. {"DXY": 105.2, "US10Y": 4.5, "VIX": 15.3}

    # News context (optional)
    news_status: str = "UNKNOWN"  # UNKNOWN, CLEAR, HIGH_IMPACT_IMMINENT
    news_events: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Compute derived fields."""
        if self.bid > 0 and self.ask > 0:
            self.spread = self.ask - self.bid
            self.last_price = (self.bid + self.ask) / 2.0

    @property
    def mid_price(self) -> float:
        """Mid-market price."""
        if self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2.0
        return self.last_price

    @property
    def data_age_seconds(self) -> float:
        """Data age in seconds."""
        return self.data_age_ms / 1000.0

    @property
    def is_stale(self) -> bool:
        """Check if data is stale (older than 30 seconds)."""
        return self.data_age_ms > 30_000

    def to_dict(self) -> Dict:
        """Serialize snapshot for transport/storage."""
        return {
            "snapshot_id": self.snapshot_id,
            "symbol": self.symbol,
            "timestamp_ms": self.timestamp_ms,
            "bid": self.bid,
            "ask": self.ask,
            "spread": self.spread,
            "last_price": self.last_price,
            "data_quality": self.data_quality,
            "data_age_ms": self.data_age_ms,
            "market_open": self.market_open,
            "session_active": self.session_active,
            "session_name": self.session_name,
            "regime": self.regime,
            "clock": {
                **self.clock.snapshot(),
                "latency": self.clock.latency_report(),
            },
            "symbol_spec": {
                "digits": self.symbol_spec.digits,
                "point": self.symbol_spec.point,
                "tick_size": self.symbol_spec.tick_size,
                "contract_size": self.symbol_spec.contract_size,
            },
        }
