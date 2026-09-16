"""
NEXUS OVERLAY AI - Trade Thesis

The TradeThesis is the canonical representation of a trading idea.
It contains everything needed to evaluate, explain, and audit a decision.

Every decision the engine makes MUST be backed by a TradeThesis.
The Decision Engine consumes this thesis — not free text, not AI prompts.

Design ref: audit section 79 (P0 — TRADE THESIS OBJECT)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class Direction(Enum):
    BUY = "BUY"
    SELL = "SELL"
    WAIT = "WAIT"
    NO_TRADE = "NO_TRADE"


class SetupType(Enum):
    TREND_FOLLOWING = "TREND_FOLLOWING"
    PULLBACK = "PULLBACK"
    BREAKOUT = "BREAKOUT"
    LIQUIDITY_SWEEP = "LIQUIDITY_SWEEP"
    MEAN_REVERSION = "MEAN_REVERSION"
    SCALPING = "SCALPING"
    ZONE_REACTION = "ZONE_REACTION"
    STRUCTURE_REACTION = "STRUCTURE_REACTION"
    REVERSAL = "REVERSAL"


class MarketRegime(Enum):
    TRENDING_BULLISH = "TRENDING_BULLISH"
    TRENDING_BEARISH = "TRENDING_BEARISH"
    RANGE = "RANGE"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    BREAKOUT = "BREAKOUT"
    CONSOLIDATION = "CONSOLIDATION"
    REVERSAL = "REVERSAL"
    UNCERTAIN = "UNCERTAIN"


class HTFBias(Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    CONFLICTING = "CONFLICTING"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class EvidenceRef:
    """A reference to an evidence item, for the thesis."""
    source: str
    reason_code: str
    description: str
    strength: float = 0.0
    timeframe: str = ""


@dataclass(frozen=True)
class RiskFlag:
    """A risk flag attached to the thesis."""
    code: str  # e.g. "SPREAD_RISK", "MTF_CONFLICT"
    severity: str  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    description: str


@dataclass
class TradeThesis:
    """
    The canonical trading thesis — everything about why a trade exists.

    This is the deterministic, auditable, machine-readable representation
    of a trading idea. No free text used for decisions — all reasoning
    flows through structured fields.

    Every field serves a purpose:
      direction:     BUY / SELL / WAIT / NO_TRADE
      setup_type:    What kind of setup (trend, pullback, breakout, etc.)
      market_regime: What the market is doing right now
      htf_bias:      What higher timeframes say
      entry_reason:  Why this specific entry (machine-readable reason codes)
      supporting:    Evidence that agrees with the direction
      counter:       Evidence that disagrees (must be addressed)
      entry/sl/tp:   The trade parameters
      rr:            Risk-reward ratio
      risk_flags:    Active risk concerns
      strategy_sources: Which strategies proposed this thesis
      snapshot_id:   The exact market snapshot this thesis was built from
    """

    direction: Direction
    setup_type: SetupType
    market_regime: MarketRegime
    higher_timeframe_bias: HTFBias
    entry_reason: List[str]  # Machine-readable reason codes
    supporting_evidence: List[EvidenceRef] = field(default_factory=list)
    counter_evidence: List[EvidenceRef] = field(default_factory=list)
    missing_confirmation: List[str] = field(default_factory=list)
    entry: float = 0.0
    sl: float = 0.0
    tp1: float = 0.0
    tp2: float = 0.0
    tp3: float = 0.0
    rr: float = 0.0
    risk_flags: List[RiskFlag] = field(default_factory=list)
    strategy_sources: List[str] = field(default_factory=list)
    snapshot_id: str = ""

    # Metadata
    symbol: str = "XAUUSD"
    timeframe: str = "M1"
    timestamp_ms: int = 0
    thesis_id: str = ""  # Unique ID for this thesis

    def __post_init__(self) -> None:
        """Auto-compute RR if not explicitly set."""
        if self.rr == 0.0 and self.entry > 0 and self.sl > 0 and self.tp1 > 0:
            risk = abs(self.entry - self.sl)
            reward = abs(self.tp1 - self.entry)
            if risk > 0:
                self.rr = round(reward / risk, 2)

    @property
    def is_actionable(self) -> bool:
        """Whether this thesis represents an actionable trade."""
        return self.direction in (Direction.BUY, Direction.SELL)

    @property
    def has_critical_risk(self) -> bool:
        """Whether any risk flag is CRITICAL."""
        return any(rf.severity == "CRITICAL" for rf in self.risk_flags)

    @property
    def risk_flag_codes(self) -> List[str]:
        """Get list of active risk flag codes."""
        return [rf.code for rf in self.risk_flags]

    @property
    def supporting_reason_codes(self) -> List[str]:
        """Get list of supporting evidence reason codes."""
        return [ev.reason_code for ev in self.supporting_evidence]

    @property
    def counter_reason_codes(self) -> List[str]:
        """Get list of counter evidence reason codes."""
        return [ev.reason_code for ev in self.counter_evidence]

    @property
    def supporting_count(self) -> int:
        return len(self.supporting_evidence)

    @property
    def counter_count(self) -> int:
        return len(self.counter_evidence)

    @property
    def net_evidence(self) -> int:
        """Net evidence count (supporting minus counter)."""
        return self.supporting_count - self.counter_count

    @property
    def sl_distance(self) -> float:
        """Distance from entry to SL in price terms."""
        return abs(self.entry - self.sl)

    @property
    def tp1_distance(self) -> float:
        """Distance from entry to TP1 in price terms."""
        return abs(self.tp1 - self.entry) if self.tp1 > 0 else 0.0

    def to_dict(self) -> Dict:
        """Serialize thesis for transport/storage."""
        return {
            "thesis_id": self.thesis_id,
            "direction": self.direction.value,
            "setup_type": self.setup_type.value,
            "market_regime": self.market_regime.value,
            "higher_timeframe_bias": self.higher_timeframe_bias.value,
            "entry_reason": self.entry_reason,
            "supporting_reason_codes": self.supporting_reason_codes,
            "counter_reason_codes": self.counter_reason_codes,
            "missing_confirmation": self.missing_confirmation,
            "entry": self.entry,
            "sl": self.sl,
            "tp1": self.tp1,
            "tp2": self.tp2,
            "tp3": self.tp3,
            "rr": self.rr,
            "risk_flags": self.risk_flag_codes,
            "strategy_sources": self.strategy_sources,
            "snapshot_id": self.snapshot_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timestamp_ms": self.timestamp_ms,
            "supporting_count": self.supporting_count,
            "counter_count": self.counter_count,
            "net_evidence": self.net_evidence,
        }


def create_wait_thesis(
    reason_codes: List[str],
    snapshot_id: str = "",
    timestamp_ms: int = 0,
    risk_flags: Optional[List[RiskFlag]] = None,
) -> TradeThesis:
    """Convenience: create a WAIT thesis with given reason codes."""
    return TradeThesis(
        direction=Direction.WAIT,
        setup_type=SetupType.TREND_FOLLOWING,  # placeholder
        market_regime=MarketRegime.UNCERTAIN,
        higher_timeframe_bias=HTFBias.UNKNOWN,
        entry_reason=reason_codes,
        risk_flags=risk_flags or [],
        snapshot_id=snapshot_id,
        timestamp_ms=timestamp_ms,
    )


def create_no_trade_thesis(
    reason_codes: List[str],
    snapshot_id: str = "",
    timestamp_ms: int = 0,
    risk_flags: Optional[List[RiskFlag]] = None,
) -> TradeThesis:
    """Convenience: create a NO_TRADE thesis."""
    return TradeThesis(
        direction=Direction.NO_TRADE,
        setup_type=SetupType.TREND_FOLLOWING,  # placeholder
        market_regime=MarketRegime.UNCERTAIN,
        higher_timeframe_bias=HTFBias.UNKNOWN,
        entry_reason=reason_codes,
        risk_flags=risk_flags or [],
        snapshot_id=snapshot_id,
        timestamp_ms=timestamp_ms,
    )
