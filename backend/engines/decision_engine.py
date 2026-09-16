"""
NEXUS OVERLAY AI - Decision Engine
THE SINGLE SOURCE OF TRUTH for all trading decisions.

Takes a TradeThesis (built from all engine outputs) and produces a
structured DecisionResult with machine-readable reason codes.

Possible states: BUY, SELL, WAIT, NO_TRADE
Internal states: DATA_UNAVAILABLE, DATA_STALE, RISK_REJECTED,
  CONFLICT, NO_SETUP, AI_UNAVAILABLE, MARKET_CLOSED

DESIGN:
  TradeThesis (input) → Decision Gates → DecisionResult (output)

The DecisionResult includes:
  - decision: BUY / SELL / WAIT / NO_TRADE
  - reason_codes: machine-readable codes (HTF_BEARISH, BOS, etc.)
  - score: 0-100 decision score (NOT probability)
  - evidence_summary: top supporting + counter evidence
  - risk_flags: active risk concerns
  - The original TradeThesis reference

Design ref: audit sections 79-80 (TradeThesis, Reason Codes)
"""
from __future__ import annotations
import asyncio
import uuid
import logging
import time
from datetime import datetime
from typing import Any, List, Optional, Set

from backend.engines.trade_thesis import (
    TradeThesis,
    Direction,
    SetupType,
    MarketRegime,
    HTFBias,
    EvidenceRef,
    RiskFlag,
)
from backend.engines.evidence_graph import (
    EvidenceGraph,
    EvidenceAssessment,
    ConflictSeverity,
)
from backend.engines.market_snapshot import MarketSnapshot, generate_snapshot_id
from backend.event_bus import EventType, get_event_bus
from backend.config_loader import get_config

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# MACHINE-READABLE REASON CODES (audit section 80)
# ═══════════════════════════════════════════════════════════

class ReasonCode:
    """All machine-readable reason codes for the decision engine.

    Free-text explanations are generated separately for the user.
    These codes are for machine consumption, audit, and replay.
    """

    # Higher Timeframe Bias
    HTF_BEARISH = "HTF_BEARISH"
    HTF_BULLISH = "HTF_BULLISH"
    HTF_NEUTRAL = "HTF_NEUTRAL"
    HTF_CONFLICTING = "HTF_CONFLICTING"

    # Structure
    BOS = "BOS"
    BOS_BULLISH = "BOS_BULLISH"
    BOS_BEARISH = "BOS_BEARISH"
    CHOCH = "CHOCH"
    CHOCH_BULLISH = "CHOCH_BULLISH"
    CHOCH_BEARISH = "CHOCH_BEARISH"
    HH_HL = "HH_HL"  # Bullish structure (Higher High, Higher Low)
    LH_LL = "LH_LL"  # Bearish structure (Lower High, Lower Low)

    # Liquidity
    LIQUIDITY_SWEEP = "LIQUIDITY_SWEEP"
    LIQUIDITY_SWEEP_BUY = "LIQUIDITY_SWEEP_BUY"
    LIQUIDITY_SWEEP_SELL = "LIQUIDITY_SWEEP_SELL"
    FALSE_BREAKOUT = "FALSE_BREAKOUT"
    DISPLACEMENT = "DISPLACEMENT"
    EQUAL_HIGHS = "EQUAL_HIGHS"
    EQUAL_LOWS = "EQUAL_LOWS"

    # Price Action
    BEARISH_REJECTION = "BEARISH_REJECTION"
    BULLISH_REJECTION = "BULLISH_REJECTION"
    BEARISH_ENGULFING = "BEARISH_ENGULFING"
    BULLISH_ENGULFING = "BULLISH_ENGULFING"
    PIN_BAR = "PIN_BAR"
    HAMMER = "HAMMER"
    SHOOTING_STAR = "SHOOTING_STAR"
    MOMENTUM_CANDLE = "MOMENTUM_CANDLE"
    EXHAUSTION_CANDLE = "EXHAUSTION_CANDLE"

    # Indicators
    EMA_ALIGNMENT = "EMA_ALIGNMENT"
    RSI_MOMENTUM = "RSI_MOMENTUM"
    RSI_OVERBOUGHT = "RSI_OVERBOUGHT"
    RSI_OVERSOLD = "RSI_OVERSOLD"
    MACD_CROSSOVER = "MACD_CROSSOVER"

    # Volatility
    ATR_NORMAL = "ATR_NORMAL"
    ATR_HIGH = "ATR_HIGH"
    ATR_LOW = "ATR_LOW"

    # Session
    SESSION_ACTIVE = "SESSION_ACTIVE"
    SESSION_INACTIVE = "SESSION_INACTIVE"
    SESSION_TRANSITION = "SESSION_TRANSITION"

    # Risk
    SPREAD_OK = "SPREAD_OK"
    SPREAD_RISK = "SPREAD_RISK"
    RR_OK = "RR_OK"
    RR_RISK = "RR_RISK"
    NEWS_OK = "NEWS_OK"
    NEWS_RISK = "NEWS_RISK"
    NEWS_UNKNOWN = "NEWS_UNKNOWN"

    # Data Quality
    DATA_OK = "DATA_OK"
    DATA_STALE = "DATA_STALE"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"

    # Conflict
    MTF_CONFLICT = "MTF_CONFLICT"
    MTF_ALIGNED = "MTF_ALIGNED"
    MTF_PARTIAL = "MTF_PARTIAL"
    DIRECTIONAL_CONFLICT = "DIRECTIONAL_CONFLICT"

    # Strategy
    STRATEGY_AGREEMENT = "STRATEGY_AGREEMENT"
    STRATEGY_CONFLICT = "STRATEGY_CONFLICT"
    NO_SETUP = "NO_SETUP"
    RISK_REJECTED = "RISK_REJECTED"

    # Signal
    SIGNAL_FRESH = "SIGNAL_FRESH"
    SIGNAL_AGE_RISK = "SIGNAL_AGE_RISK"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"

    # Market state
    MARKET_OPEN = "MARKET_OPEN"
    MARKET_CLOSED = "MARKET_CLOSED"


class DecisionResult:
    """
    Structured decision output with machine-readable reason codes.

    This replaces free-text evidence strings with structured data
    that can be audited, replayed, and consumed by the Android overlay.

    Every decision references its snapshot_id for atomic reproducibility
    (audit section XLIV). decision_timestamp_ms records when the decision
    was finalized (from snapshot.clock.decision_time_ms).
    """

    def __init__(
        self,
        decision: Direction,
        reason_codes: List[str],
        score: int,
        evidence_summary: Dict[str, List[str]],
        risk_flags: List[str],
        thesis: TradeThesis,
        snapshot_id: str,
        timestamp_ms: int,
        decision_timestamp_ms: int = 0,
    ) -> None:
        self.decision = decision
        self.reason_codes = reason_codes
        self.score = max(0, min(100, score))
        self.evidence_summary = evidence_summary
        self.risk_flags = risk_flags
        self.thesis = thesis
        self.snapshot_id = snapshot_id
        self.timestamp_ms = timestamp_ms
        # Explicit decision timestamp (from snapshot clock discipline)
        self.decision_timestamp_ms = decision_timestamp_ms or timestamp_ms
        self.signal_id: str = ""  # Set when signal is created

    @property
    def primary_reason_codes(self) -> List[str]:
        """Top reason codes (first 5)."""
        return self.reason_codes[:5]

    @property
    def has_critical_risk(self) -> bool:
        """Whether any risk flag is CRITICAL."""
        return "CRITICAL" in [
            rf.split(":")[1] if ":" in rf else "LOW"
            for rf in self.risk_flags
        ]

    @property
    def is_actionable(self) -> bool:
        """Whether this decision represents an actionable trade."""
        return self.decision in (Direction.BUY, Direction.SELL)

    def to_dict(self) -> Dict:
        """Serialize for transport/storage."""
        return {
            "decision": self.decision.value,
            "reason_codes": self.reason_codes,
            "score": self.score,
            "evidence_summary": self.evidence_summary,
            "risk_flags": self.risk_flags,
            "thesis_id": self.thesis.thesis_id,
            "snapshot_id": self.snapshot_id,
            "timestamp_ms": self.timestamp_ms,
            "decision_timestamp_ms": self.decision_timestamp_ms,
            "signal_id": self.signal_id,
            "entry": self.thesis.entry,
            "sl": self.thesis.sl,
            "tp1": self.thesis.tp1,
            "tp2": self.thesis.tp2,
            "tp3": self.thesis.tp3,
            "rr": self.thesis.rr,
            "symbol": self.thesis.symbol,
            "direction": self.decision.value,
        }


# Backward-compatible type alias
from typing import Dict


class DecisionEngineOutput:
    """Container for all upstream engine outputs consumed by DecisionEngine.

    Kept for backward compatibility. New code should use TradeThesis directly.
    """

    def __init__(self) -> None:
        # From strategy engine
        from backend.models import (
            StrategyAssessment, ConfluenceScore, MultiTimeframeAnalysis,
            RiskValidation, EntryCalculation, SLTPCalculation,
            AIAssessment, ConfidenceModel, MarketRegime,
        )
        self.strategy_assessments: list[StrategyAssessment] = []
        self.confluence: Optional[ConfluenceScore] = None
        self.risk_validation: Optional[RiskValidation] = None
        self.entry_calc: Optional[EntryCalculation] = None
        self.sltp_calc: Optional[SLTPCalculation] = None
        self.ai_assessment: Optional[AIAssessment] = None
        self.ai_available: bool = True
        self.confidence_model: Optional[ConfidenceModel] = None
        self.symbol: str = "XAUUSD"
        self.price: float = 0.0
        self.spread: float = 0.0
        self.trend: str = "NEUTRAL"
        self.regime: MarketRegime = MarketRegime.UNCERTAIN
        self.data_quality: float = 1.0
        self.data_age_ms: int = 0
        self.market_open: bool = True
        self.transport_connected: bool = True
        self.mtf: Optional[MultiTimeframeAnalysis] = None
        self.structure_summary: str = ""
        self.liquidity_state: str = ""
        # P0 — uncertainty and eligibility (audit sections 24, 26)
        self.uncertainty = None   # UncertaintyAssessment
        self.eligibility = None   # DecisionEligibilityResult


class DecisionEngine:
    """
    THE SINGLE SOURCE OF TRUTH.

    Decision flow:
      1. DATA GATE: Check data quality, staleness, market open, transport
      2. THESIS GATE: Validate TradeThesis structure
      3. HTF GATE: Higher timeframe bias alignment
      4. EVIDENCE GATE: Check EvidenceGraph assessment
      5. CONFLICT GATE: Conflict severity check
      6. RISK GATE: Check risk flags
      7. AI GATE: AI assessment alignment (optional)
      8. BUILD RESULT: Assemble DecisionResult with reason codes
    """

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        self._config = config or get_config().all()
        self._logger = logging.getLogger("nexus.engine.decision")
        self._running = False
        self._cycle_count = 0

        # Thresholds from config (0-100 scale)
        self._min_score = self._config.get("min_confidence", 55)
        self._max_data_age_ms = self._config.get("max_data_age_ms", 30_000)
        self._min_data_quality = self._config.get("min_data_quality", 30.0)
        self._min_rr = self._config.get("min_rr", 1.0)
        self._max_spread = self._config.get("max_spread", 60.0)
        self._ai_weight = self._config.get("ai_weight", 0.15)

        # Active signal tracking
        self._active_thesis: Optional[TradeThesis] = None
        self._thesis_history: List[TradeThesis] = []

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._logger.info("Decision engine started")

    async def stop(self) -> None:
        self._running = False
        self._logger.info("Decision engine stopped")

    def _check_data_gate(self, snapshot: MarketSnapshot) -> Optional[DecisionResult]:
        """GATE 1: Data quality, staleness, market open, transport."""
        reason_codes: List[str] = []
        risk_flags: List[str] = []

        if not snapshot.transport_connected:
            reason_codes.append(ReasonCode.DATA_UNAVAILABLE)
            return self._build_wait_result(
                reason_codes, risk_flags,
                snapshot.snapshot_id, "Transport disconnected"
            )

        if not snapshot.market_open:
            reason_codes.append(ReasonCode.MARKET_CLOSED)
            return self._build_wait_result(
                reason_codes, risk_flags,
                snapshot.snapshot_id, "Market is closed"
            )

        if snapshot.bid <= 0 or snapshot.ask <= 0:
            reason_codes.append(ReasonCode.DATA_UNAVAILABLE)
            return self._build_wait_result(
                reason_codes, risk_flags,
                snapshot.snapshot_id, "Invalid price data"
            )

        if snapshot.data_quality < self._min_data_quality:
            reason_codes.append(ReasonCode.DATA_STALE)
            return self._build_wait_result(
                reason_codes, risk_flags,
                snapshot.snapshot_id,
                f"Data quality {snapshot.data_quality:.0f} < {self._min_data_quality}"
            )

        if snapshot.data_age_ms > self._max_data_age_ms:
            reason_codes.append(ReasonCode.DATA_STALE)
            return self._build_wait_result(
                reason_codes, risk_flags,
                snapshot.snapshot_id,
                f"Data stale: {snapshot.data_age_ms}ms"
            )

        reason_codes.append(ReasonCode.DATA_OK)
        return None  # Gate passed

    def _check_thesis_gate(self, thesis: TradeThesis) -> Optional[DecisionResult]:
        """GATE 2: Validate TradeThesis has a direction and basic structure."""
        if thesis.direction == Direction.WAIT:
            return self._build_wait_result(
                thesis.entry_reason,
                [rf.code for rf in thesis.risk_flags],
                thesis.snapshot_id,
                "Thesis direction is WAIT"
            )

        if thesis.direction == Direction.NO_TRADE:
            return self._build_no_trade_result(
                thesis.entry_reason,
                [rf.code for rf in thesis.risk_flags],
                thesis.snapshot_id,
            )

        return None  # Gate passed

    def _check_htf_gate(
        self,
        thesis: TradeThesis,
        reason_codes: List[str],
    ) -> Optional[DecisionResult]:
        """GATE 3: Higher timeframe bias alignment."""
        if thesis.higher_timeframe_bias == HTFBias.CONFLICTING:
            reason_codes.append(ReasonCode.MTF_CONFLICT)
            return self._build_wait_result(
                reason_codes,
                [rf.code for rf in thesis.risk_flags],
                thesis.snapshot_id,
                "Higher TF conflicting"
            )

        # Check HTF alignment with thesis direction
        if thesis.direction == Direction.BUY and thesis.higher_timeframe_bias == HTFBias.BEARISH:
            reason_codes.append(ReasonCode.HTF_BEARISH)
            # Don't block — but note the conflict
        elif thesis.direction == Direction.SELL and thesis.higher_timeframe_bias == HTFBias.BULLISH:
            reason_codes.append(ReasonCode.HTF_BULLISH)
            # Don't block — but note the conflict
        elif thesis.higher_timeframe_bias == HTFBias.BULLISH:
            reason_codes.append(ReasonCode.HTF_BULLISH)
        elif thesis.higher_timeframe_bias == HTFBias.BEARISH:
            reason_codes.append(ReasonCode.HTF_BEARISH)
        else:
            reason_codes.append(ReasonCode.HTF_NEUTRAL)

        return None  # Gate passed (may have conflicting HTF but not blocking)

    def _check_evidence_gate(
        self,
        evidence_assessment: Optional[EvidenceAssessment],
        thesis: TradeThesis,
        reason_codes: List[str],
    ) -> Optional[DecisionResult]:
        """GATE 4: Evidence graph assessment."""
        if evidence_assessment is None:
            reason_codes.append(ReasonCode.NO_SETUP)
            return self._build_wait_result(
                reason_codes,
                [rf.code for rf in thesis.risk_flags],
                thesis.snapshot_id,
                "No evidence assessment available"
            )

        ea = evidence_assessment

        # Check for critical conflict
        if ea.conflict_severity == ConflictSeverity.CRITICAL:
            reason_codes.append(ReasonCode.MTF_CONFLICT)
            reason_codes.append(ReasonCode.DIRECTIONAL_CONFLICT)
            return self._build_wait_result(
                reason_codes,
                [rf.code for rf in thesis.risk_flags],
                thesis.snapshot_id,
                "Critical directional conflict"
            )

        # Check net directional score is meaningful
        if abs(ea.net_directional_score) < 5:
            reason_codes.append(ReasonCode.NO_SETUP)
            return self._build_wait_result(
                reason_codes,
                [rf.code for rf in thesis.risk_flags],
                thesis.snapshot_id,
                f"Net directional score too weak: {ea.net_directional_score:.1f}"
            )

        # Check agreement ratio
        if ea.agreement_ratio < 0.5:
            reason_codes.append(ReasonCode.DIRECTIONAL_CONFLICT)

        return None  # Gate passed

    def _check_risk_gate(
        self,
        thesis: TradeThesis,
        reason_codes: List[str],
    ) -> Optional[DecisionResult]:
        """GATE 5: Risk flags check."""
        risk_codes = [rf.code for rf in thesis.risk_flags]
        has_critical = any(rf.severity == "CRITICAL" for rf in thesis.risk_flags)
        has_high = any(rf.severity == "HIGH" for rf in thesis.risk_flags)

        if has_critical:
            reason_codes.append(ReasonCode.RISK_REJECTED)
            return self._build_wait_result(
                reason_codes, risk_codes,
                thesis.snapshot_id,
                "Critical risk flag present"
            )

        if thesis.rr > 0 and thesis.rr < self._min_rr:
            reason_codes.append(ReasonCode.RR_RISK)
        elif thesis.rr >= self._min_rr:
            reason_codes.append(ReasonCode.RR_OK)

        # Spread check
        if thesis.risk_flags and any(rf.code == "SPREAD_RISK" for rf in thesis.risk_flags):
            reason_codes.append(ReasonCode.SPREAD_RISK)
        else:
            reason_codes.append(ReasonCode.SPREAD_OK)

        # High risk but not blocking — note it
        if has_high:
            reason_codes.append(ReasonCode.HIGH_VOLATILITY)

        return None  # Gate passed

    def _compute_score(self, thesis: TradeThesis, evidence: Optional[EvidenceAssessment]) -> int:
        """Compute a 0-100 decision score. NOT probability."""
        score = 50  # Base

        # Evidence strength contribution
        if evidence:
            score += int(evidence.net_directional_score * 0.2)
            score += int(evidence.agreement_ratio * 20)
            score -= int(evidence.conflict_score * 0.1)

        # Supporting vs counter evidence
        net = thesis.net_evidence
        score += min(15, max(-15, net * 3))

        # RR contribution
        if thesis.rr >= 2.0:
            score += 10
        elif thesis.rr >= 1.5:
            score += 5
        elif thesis.rr < 1.0:
            score -= 15

        # Risk penalty
        critical_count = sum(1 for rf in thesis.risk_flags if rf.severity == "CRITICAL")
        high_count = sum(1 for rf in thesis.risk_flags if rf.severity == "HIGH")
        score -= critical_count * 20
        score -= high_count * 10

        # HTF alignment bonus
        if thesis.higher_timeframe_bias == HTFBias.BULLISH and thesis.direction == Direction.BUY:
            score += 10
        elif thesis.higher_timeframe_bias == HTFBias.BEARISH and thesis.direction == Direction.SELL:
            score += 10
        elif thesis.higher_timeframe_bias == HTFBias.CONFLICTING:
            score -= 15

        return max(0, min(100, score))

    def _build_wait_result(
        self,
        reason_codes: List[str],
        risk_flags: List[str],
        snapshot_id: str,
        _description: str,
    ) -> DecisionResult:
        """Build a WAIT decision result."""
        thesis = TradeThesis(
            direction=Direction.WAIT,
            setup_type=SetupType.TREND_FOLLOWING,
            market_regime=MarketRegime.UNCERTAIN,
            higher_timeframe_bias=HTFBias.UNKNOWN,
            entry_reason=reason_codes,
            risk_flags=[RiskFlag(code=rc, severity="MEDIUM", description=rc)
                       for rc in risk_flags],
            snapshot_id=snapshot_id,
        )
        return DecisionResult(
            decision=Direction.WAIT,
            reason_codes=reason_codes,
            score=0,
            evidence_summary={"supporting": [], "counter": []},
            risk_flags=risk_flags,
            thesis=thesis,
            snapshot_id=snapshot_id,
            timestamp_ms=int(time.time() * 1000),
        )

    def _build_no_trade_result(
        self,
        reason_codes: List[str],
        risk_flags: List[str],
        snapshot_id: str,
    ) -> DecisionResult:
        """Build a NO_TRADE decision result."""
        thesis = TradeThesis(
            direction=Direction.NO_TRADE,
            setup_type=SetupType.TREND_FOLLOWING,
            market_regime=MarketRegime.UNCERTAIN,
            higher_timeframe_bias=HTFBias.UNKNOWN,
            entry_reason=reason_codes,
            risk_flags=[RiskFlag(code=rc, severity="MEDIUM", description=rc)
                       for rc in risk_flags],
            snapshot_id=snapshot_id,
        )
        return DecisionResult(
            decision=Direction.NO_TRADE,
            reason_codes=reason_codes,
            score=0,
            evidence_summary={"supporting": [], "counter": []},
            risk_flags=risk_flags,
            thesis=thesis,
            snapshot_id=snapshot_id,
            timestamp_ms=int(time.time() * 1000),
        )

    def evaluate_thesis(
        self,
        thesis: TradeThesis,
        snapshot: MarketSnapshot,
        evidence_assessment: Optional[EvidenceAssessment] = None,
    ) -> DecisionResult:
        """
        THE PRIMARY ENTRY POINT for decision making.

        Takes a TradeThesis and MarketSnapshot, runs through all gates,
        produces a structured DecisionResult.

        Args:
            thesis: The trading thesis from strategy engines.
            snapshot: Atomic market snapshot at decision time.
            evidence_assessment: Optional pre-computed evidence assessment.

        Returns:
            DecisionResult with machine-readable reason codes.
        """
        self._cycle_count += 1
        reason_codes: List[str] = []

        # ── GATE 1: DATA GATE ──
        data_result = self._check_data_gate(snapshot)
        if data_result is not None:
            return data_result

        # ── GATE 2: THESIS GATE ──
        thesis_result = self._check_thesis_gate(thesis)
        if thesis_result is not None:
            return thesis_result

        # ── GATE 3: HTF GATE ──
        htf_result = self._check_htf_gate(thesis, reason_codes)
        if htf_result is not None:
            return htf_result

        # ── GATE 4: EVIDENCE GATE ──
        evidence_result = self._check_evidence_gate(
            evidence_assessment, thesis, reason_codes
        )
        if evidence_result is not None:
            return evidence_result

        # ── GATE 5: RISK GATE ──
        risk_result = self._check_risk_gate(thesis, reason_codes)
        if risk_result is not None:
            return risk_result

        # ── ALL GATES PASSED → BUILD RESULT ──

        # Add strategy agreement codes
        reason_codes.append(ReasonCode.STRATEGY_AGREEMENT)

        # Compute score
        score = self._compute_score(thesis, evidence_assessment)

        # Build evidence summary
        evidence_summary = {"supporting": [], "counter": []}
        if evidence_assessment:
            evidence_summary["supporting"] = [
                f"{e.reason_code}: {e.description}"
                for e in evidence_assessment.supporting_evidence[:3]
            ]
            evidence_summary["counter"] = [
                f"{e.reason_code}: {e.description}"
                for e in evidence_assessment.counter_evidence[:3]
            ]

        risk_flags = thesis.risk_flag_codes
        risk_flags.extend([
            rc for rc in reason_codes
            if rc in (
                ReasonCode.SPREAD_RISK, ReasonCode.RR_RISK,
                ReasonCode.NEWS_RISK, ReasonCode.HIGH_VOLATILITY,
                ReasonCode.SIGNAL_AGE_RISK,
            )
        ])

        result = DecisionResult(
            decision=thesis.direction,
            reason_codes=reason_codes,
            score=score,
            evidence_summary=evidence_summary,
            risk_flags=risk_flags,
            thesis=thesis,
            snapshot_id=snapshot.snapshot_id,
            timestamp_ms=int(time.time() * 1000),
            decision_timestamp_ms=(
                snapshot.clock.decision_time_ms
                if snapshot.clock.decision_time_ms > 0
                else int(time.time() * 1000)
            ),
        )

        return result

    async def evaluate_legacy(
        self, output: DecisionEngineOutput
    ) -> DecisionResult:
        """
        Legacy entry point for backward compatibility.

        Converts DecisionEngineOutput to TradeThesis + MarketSnapshot,
        then runs through the standard decision flow.
        """
        # Build snapshot from legacy output
        snapshot = MarketSnapshot(
            symbol=output.symbol,
            bid=output.price - output.spread / 2 if output.spread > 0 else output.price,
            ask=output.price + output.spread / 2 if output.spread > 0 else output.price,
            data_quality=output.data_quality * 100,
            data_age_ms=output.data_age_ms,
            market_open=output.market_open,
            transport_connected=output.transport_connected,
        )

        # Build thesis from legacy output
        direction = Direction.WAIT
        if output.strategy_assessments:
            buy_count = sum(1 for a in output.strategy_assessments
                          if a.direction.value == "BUY")
            sell_count = sum(1 for a in output.strategy_assessments
                           if a.direction.value == "SELL")
            if buy_count > sell_count:
                direction = Direction.BUY
            elif sell_count > buy_count:
                direction = Direction.SELL

        strategy_sources = [
            a.strategy for a in output.strategy_assessments
            if a.direction.value != "WAIT"
        ]

        entry = output.entry_calc.price if output.entry_calc else output.price
        sl = output.sltp_calc.sl_price if output.sltp_calc else 0.0
        tp1 = output.sltp_calc.tp1_price if output.sltp_calc else 0.0
        tp2 = output.sltp_calc.tp2_price if output.sltp_calc else 0.0
        tp3 = output.sltp_calc.tp3_price if output.sltp_calc else 0.0

        htf_bias = HTFBias.UNKNOWN
        if output.mtf:
            if output.mtf.alignment == "aligned":
                if output.mtf.dominant_trend.value == "BULLISH":
                    htf_bias = HTFBias.BULLISH
                elif output.mtf.dominant_trend.value == "BEARISH":
                    htf_bias = HTFBias.BEARISH
            elif output.mtf.alignment == "conflicting":
                htf_bias = HTFBias.CONFLICTING
            elif output.mtf.alignment == "partially_aligned":
                if output.mtf.dominant_trend.value == "BULLISH":
                    htf_bias = HTFBias.BULLISH
                elif output.mtf.dominant_trend.value == "BEARISH":
                    htf_bias = HTFBias.BEARISH

        thesis = TradeThesis(
            direction=direction,
            setup_type=SetupType.TREND_FOLLOWING,
            market_regime=MarketRegime(output.regime.value)
            if hasattr(output.regime, 'value') else MarketRegime.UNCERTAIN,
            higher_timeframe_bias=htf_bias,
            entry_reason=["LEGACY_CONVERSION"],
            entry=entry,
            sl=sl,
            tp1=tp1,
            tp2=tp2,
            tp3=tp3,
            strategy_sources=strategy_sources,
            snapshot_id=snapshot.snapshot_id,
            symbol=output.symbol,
        )

        return self.evaluate_thesis(thesis, snapshot)

    async def evaluate(self, output: DecisionEngineOutput) -> DecisionResult:
        """Alias for evaluate_legacy for backward compatibility."""
        return await self.evaluate_legacy(output)

    def get_active_thesis(self) -> Optional[TradeThesis]:
        """Get the currently active thesis."""
        return self._active_thesis

    def get_thesis_history(self, limit: int = 10) -> List[TradeThesis]:
        """Get recent thesis history."""
        return self._thesis_history[-limit:]

    def get_stats(self) -> dict[str, Any]:
        """Get decision engine statistics."""
        return {
            "cycle_count": self._cycle_count,
            "running": self._running,
            "has_active_thesis": self._active_thesis is not None,
            "active_thesis_id": (
                self._active_thesis.thesis_id if self._active_thesis else None
            ),
            "thesis_history_count": len(self._thesis_history),
            "config": {
                "min_score": self._min_score,
                "max_data_age_ms": self._max_data_age_ms,
                "min_data_quality": self._min_data_quality,
                "min_rr": self._min_rr,
                "max_spread": self._max_spread,
            },
        }
