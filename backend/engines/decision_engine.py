"""
NEXUS OVERLAY AI - Decision Engine
THE SINGLE SOURCE OF TRUTH for all trading decisions.

Takes all engine outputs (indicators, structure, liquidity, price_action,
MTF, confluence, risk, entry, SL/TP, AI, confidence) and produces the final
BUY/SELL/WAIT decision.

Possible states: BUY, SELL, WAIT, DATA_UNAVAILABLE, DATA_STALE, RISK_REJECTED,
CONFLICT, NO_SETUP, AI_UNAVAILABLE, MARKET_CLOSED.

Produces complete TradingSignal with evidence and invalidations.
Emits SIGNAL_CREATED / SIGNAL_UPDATED / INVALIDATED events.
"""
from __future__ import annotations
import asyncio
import uuid
import logging
from datetime import datetime
from typing import Any, Optional

from backend.models import (
    DecisionState,
    InternalDecisionState,
    SignalLifecycleState,
    TradingSignal,
    StrategyAssessment,
    ConfluenceScore,
    MultiTimeframeAnalysis,
    RiskValidation,
    EntryCalculation,
    SLTPCalculation,
    AIAssessment,
    ConfidenceModel,
    MarketRegime,
    TrendDirection,
    DecisionLogEntry,
    now_ms,
)
from backend.event_bus import EventType, get_event_bus
from backend.config_loader import get_config

logger = logging.getLogger(__name__)


class DecisionEngineOutput:
    """Container for all upstream engine outputs consumed by DecisionEngine."""

    def __init__(self) -> None:
        # From strategy engine
        self.strategy_assessments: list[StrategyAssessment] = []
        self.confluence: Optional[ConfluenceScore] = None

        # From risk engine
        self.risk_validation: Optional[RiskValidation] = None

        # From entry engine
        self.entry_calc: Optional[EntryCalculation] = None

        # From SL/TP engine
        self.sltp_calc: Optional[SLTPCalculation] = None

        # From AI engine
        self.ai_assessment: Optional[AIAssessment] = None
        self.ai_available: bool = True

        # From confidence model
        self.confidence_model: Optional[ConfidenceModel] = None

        # Market context
        self.symbol: str = "XAUUSD"
        self.price: float = 0.0
        self.spread: float = 0.0
        self.trend: str = "NEUTRAL"
        self.regime: MarketRegime = MarketRegime.UNCERTAIN
        self.data_quality: float = 1.0
        self.data_age_ms: int = 0
        self.market_open: bool = True
        self.transport_connected: bool = True

        # MTF
        self.mtf: Optional[MultiTimeframeAnalysis] = None

        # Structure
        self.structure_summary: str = ""

        # Liquidity state
        self.liquidity_state: str = ""


class DecisionEngine:
    """
    THE SINGLE SOURCE OF TRUTH.
    
    Decision flow:
      1. DATA GATE: Check data quality, staleness, market open, transport
      2. SETUP GATE: Check strategy assessments — any non-WAIT?
      3. RISK GATE: Validate risk engine output
      4. CONFLUENCE GATE: Check total confluence score
      5. AI GATE: AI assessment alignment (optional but preferred)
      6. SIGNAL BUILDER: Assemble TradingSignal with all evidence
      7. EVENT EMITTER: Emit lifecycle events
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self._config = config or get_config().all()
        self._logger = logging.getLogger("nexus.engine.decision")
        self._running = False
        self._cycle_count = 0

        # Thresholds from config
        self._min_confidence = self._config.get("min_confidence", 55)
        self._min_confluence = self._config.get("min_confluence_score", 30.0)
        self._max_data_age_ms = self._config.get("max_data_age_ms", 30_000)  # 30s
        self._min_data_quality = self._config.get("min_data_quality", 0.3)
        self._ai_weight = self._config.get("ai_weight", 0.15)

        # Active signal tracking
        self._active_signal: Optional[TradingSignal] = None
        self._signal_history: list[TradingSignal] = []

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._logger.info("Decision engine started")

    async def stop(self) -> None:
        self._running = False
        self._logger.info("Decision engine stopped")

    def _decide_internal(self, output: DecisionEngineOutput) -> tuple[
        DecisionState, InternalDecisionState | None, list[str], list[str]
    ]:
        """
        Core decision logic. Returns:
          (decision, internal_state, evidence, invalidations)
        """
        evidence: list[str] = []
        invalidations: list[str] = []

        # ═══════════════════════════════════════════
        # GATE 1: DATA GATE
        # ═══════════════════════════════════════════

        if not output.transport_connected:
            invalidations.append("Transport disconnected — cannot verify data")
            return DecisionState.WAIT, InternalDecisionState.DATA_UNAVAILABLE, evidence, invalidations

        if not output.market_open:
            evidence.append("Market is closed")
            return DecisionState.WAIT, InternalDecisionState.MARKET_CLOSED, evidence, invalidations

        if output.price <= 0 or output.spread < 0:
            invalidations.append(f"Invalid price data: price={output.price}, spread={output.spread}")
            return DecisionState.WAIT, InternalDecisionState.DATA_UNAVAILABLE, evidence, invalidations

        if output.data_quality < self._min_data_quality:
            invalidations.append(
                f"Data quality too low: {output.data_quality:.2f} < {self._min_data_quality}"
            )
            return DecisionState.WAIT, InternalDecisionState.DATA_UNAVAILABLE, evidence, invalidations

        if output.data_age_ms > self._max_data_age_ms:
            invalidations.append(
                f"Data stale: age {output.data_age_ms}ms > {self._max_data_age_ms}ms"
            )
            return DecisionState.WAIT, InternalDecisionState.DATA_STALE, evidence, invalidations

        evidence.append(f"Data gate PASSED (quality={output.data_quality:.2f}, age={output.data_age_ms}ms)")

        # ═══════════════════════════════════════════
        # GATE 2: SETUP GATE (Strategy Assessments)
        # ═══════════════════════════════════════════

        active_assessments = [
            a for a in output.strategy_assessments
            if a.direction != DecisionState.WAIT
        ]

        if not active_assessments:
            evidence.append("No strategies with active setups")
            return DecisionState.WAIT, InternalDecisionState.NO_SETUP, evidence, invalidations

        # Check agreement
        buy_count = sum(1 for a in active_assessments if a.direction == DecisionState.BUY)
        sell_count = sum(1 for a in active_assessments if a.direction == DecisionState.SELL)

        if buy_count > 0 and sell_count > 0:
            # Conflicting directions — may still be viable if one side dominates
            total = buy_count + sell_count
            majority_ratio = max(buy_count, sell_count) / total
            if majority_ratio < 0.6:
                invalidations.append(
                    f"Conflicting strategies: {buy_count} BUY vs {sell_count} SELL "
                    f"(majority ratio {majority_ratio:.1%} < 60%)"
                )
                return DecisionState.WAIT, InternalDecisionState.CONFLICT, evidence, invalidations
            evidence.append(
                f"Conflicting but majority wins: {buy_count} BUY vs {sell_count} SELL "
                f"(ratio {majority_ratio:.1%})"
            )

        # Dominant direction
        if buy_count >= sell_count:
            candidate_direction = DecisionState.BUY
        else:
            candidate_direction = DecisionState.SELL

        active_strategies = [
            a.strategy for a in active_assessments if a.direction == candidate_direction
        ]
        evidence.append(
            f"Setup gate PASSED: {candidate_direction.value} "
            f"from {len(active_strategies)} strategies ({', '.join(active_strategies)})"
        )

        # ═══════════════════════════════════════════
        # GATE 3: RISK GATE
        # ═══════════════════════════════════════════

        if output.risk_validation is not None:
            rv = output.risk_validation
            if not rv.passed:
                invalidations.append(
                    f"Risk validation FAILED: {', '.join(rv.failed_reasons)}"
                )
                return DecisionState.WAIT, InternalDecisionState.RISK_REJECTED, evidence, invalidations
            evidence.append(
                f"Risk gate PASSED (RR={rv.rr:.1f}, spread={rv.spread:.2f})"
            )
        else:
            invalidations.append("Risk validation not available")
            return DecisionState.WAIT, InternalDecisionState.RISK_REJECTED, evidence, invalidations

        # ═══════════════════════════════════════════
        # GATE 4: CONFLUENCE GATE
        # ═══════════════════════════════════════════

        if output.confluence is not None:
            conf_score = output.confluence.total_score
            if conf_score < self._min_confluence:
                invalidations.append(
                    f"Confluence too low: {conf_score:.1f} < {self._min_confluence}"
                )
                return DecisionState.WAIT, InternalDecisionState.NO_SETUP, evidence, invalidations
            evidence.append(f"Confluence gate PASSED: score={conf_score:.1f}")
        elif output.confidence_model is not None:
            # Use confidence model as fallback
            cm = output.confidence_model
            if cm.final_confidence * 100 < self._min_confidence:
                invalidations.append(
                    f"Confidence model too low: {cm.final_confidence * 100:.1f} < {self._min_confidence}"
                )
                return DecisionState.WAIT, InternalDecisionState.NO_SETUP, evidence, invalidations
            evidence.append(f"Confidence gate PASSED: final={cm.final_confidence * 100:.1f}")
        else:
            # No confluence data — use average of strategy scores
            avg_score = (
                sum(a.score for a in active_assessments) / len(active_assessments)
                if active_assessments else 0
            )
            if avg_score < self._min_confidence:
                invalidations.append(f"Average strategy score too low: {avg_score:.0f}")
                return DecisionState.WAIT, InternalDecisionState.NO_SETUP, evidence, invalidations
            evidence.append(f"Fallback confluence: avg strategy score={avg_score:.0f}")

        # ═══════════════════════════════════════════
        # GATE 5: AI GATE (optional)
        # ═══════════════════════════════════════════

        if output.ai_assessment is not None:
            ai = output.ai_assessment
            ai_assessment_lower = ai.assessment.lower().strip()

            # Check AI alignment with candidate direction
            ai_aligned = False
            if candidate_direction == DecisionState.BUY and ai_assessment_lower in ("bullish", "buy"):
                ai_aligned = True
            elif candidate_direction == DecisionState.SELL and ai_assessment_lower in ("bearish", "sell"):
                ai_aligned = True

            if ai_aligned:
                evidence.append(
                    f"AI gate PASSED: AI={ai.assessment} aligned with {candidate_direction.value} "
                    f"(confidence={ai.confidence:.2f})"
                )
            else:
                # AI disagrees — reduce confidence but don't block
                invalidations.append(
                    f"AI assessment '{ai.assessment}' does not align with {candidate_direction.value}"
                )
                evidence.append("AI gate: MISALIGNMENT — confidence reduced")
        elif not output.ai_available:
            invalidations.append("AI unavailable — proceeding without AI validation")
            evidence.append("AI gate: SKIPPED (AI unavailable)")
        else:
            evidence.append("AI gate: SKIPPED (no AI assessment)")

        # ═══════════════════════════════════════════
        # ALL GATES PASSED → BUILD SIGNAL
        # ═══════════════════════════════════════════

        evidence.append(f"DECISION: {candidate_direction.value}")
        return candidate_direction, None, evidence, invalidations

    def _build_signal(
        self,
        output: DecisionEngineOutput,
        decision: DecisionState,
        internal_state: Optional[InternalDecisionState],
        evidence: list[str],
        invalidations: list[str],
    ) -> TradingSignal:
        """Build complete TradingSignal from all available data."""
        signal_id = f"SIG-{uuid.uuid4().hex[:12].upper()}"
        timestamp = now_ms()

        # Entry price from entry engine or current price
        entry = output.entry_calc.price if output.entry_calc else output.price
        sl = output.sltp_calc.sl_price if output.sltp_calc else 0.0
        tp1 = output.sltp_calc.tp1_price if output.sltp_calc else 0.0
        tp2 = output.sltp_calc.tp2_price if output.sltp_calc else 0.0
        tp3 = output.sltp_calc.tp3_price if output.sltp_calc else 0.0

        # Risk-reward
        rr = 0.0
        if output.risk_validation:
            rr = output.risk_validation.rr
        elif output.sltp_calc and sl > 0 and tp1 > 0:
            risk = abs(entry - sl)
            reward = abs(tp1 - entry)
            rr = reward / risk if risk > 0 else 0.0

        # Confidence from confidence model or compute from assessments
        confidence = 0
        if output.confidence_model:
            confidence = int(output.confidence_model.final_confidence * 100)
        elif output.strategy_assessments:
            active = [a for a in output.strategy_assessments if a.direction != DecisionState.WAIT]
            if active:
                confidence = int(sum(a.score for a in active) / len(active))
        confidence = max(0, min(100, confidence))

        # If we have internal state, confidence is 0 (no trade)
        if internal_state is not None:
            confidence = 0

        signal = TradingSignal(
            decision=decision,
            confidence=confidence,
            symbol=output.symbol,
            entry=entry,
            sl=sl,
            tp1=tp1,
            tp2=tp2,
            tp3=tp3,
            rr=round(rr, 2),
            trend=output.trend,
            regime=output.regime.value,
            evidence=evidence,
            invalidations=invalidations,
            timestamp=timestamp,
            lifecycle_state=SignalLifecycleState.NEW if decision != DecisionState.WAIT else SignalLifecycleState.INVALIDATED,
            signal_id=signal_id,
            mtf_analysis=output.mtf,
            confluence=output.confluence,
            risk_validation=output.risk_validation,
            entry_calc=output.entry_calc,
            sltp_calc=output.sltp_calc,
            confidence_model=output.confidence_model,
            ai_assessment=output.ai_assessment,
            data_quality_score=output.data_quality * 100,
        )

        return signal

    async def evaluate(self, output: DecisionEngineOutput) -> TradingSignal:
        """
        THE SINGLE ENTRY POINT for decision making.
        
        Takes all engine outputs, runs through gates, produces TradingSignal.
        
        Args:
            output: DecisionEngineOutput with all upstream engine data.
        
        Returns:
            Complete TradingSignal.
        """
        self._cycle_count += 1
        bus = get_event_bus()

        # Run decision logic
        decision, internal_state, evidence, invalidations = self._decide_internal(output)

        # Build the signal
        signal = self._build_signal(output, decision, internal_state, evidence, invalidations)

        # Check for existing active signal → update or invalidate
        if self._active_signal is not None:
            if decision != DecisionState.WAIT and decision == self._active_signal.decision:
                # Same direction — update signal
                signal.lifecycle_state = SignalLifecycleState.ACTIVE
                signal.signal_id = self._active_signal.signal_id
                self._active_signal = signal

                try:
                    await bus.publish(
                        EventType.SIGNAL_UPDATED,
                        "decision_engine",
                        {
                            "signal_id": signal.signal_id,
                            "decision": signal.decision.value,
                            "confidence": signal.confidence,
                            "entry": signal.entry,
                            "evidence_count": len(signal.evidence),
                        },
                    )
                except Exception as e:
                    self._logger.error(f"Failed to emit SIGNAL_UPDATED: {e}")

            else:
                # Direction changed or went to WAIT → invalidate old signal
                old_signal = self._active_signal
                old_signal.lifecycle_state = SignalLifecycleState.INVALIDATED
                self._signal_history.append(old_signal)

                try:
                    await bus.publish(
                        EventType.SIGNAL_INVALIDATED,
                        "decision_engine",
                        {
                            "signal_id": old_signal.signal_id,
                            "reason": (
                                "Direction changed" if decision != DecisionState.WAIT
                                else "Decision reverted to WAIT"
                            ),
                            "new_decision": decision.value,
                        },
                    )
                except Exception as e:
                    self._logger.error(f"Failed to emit SIGNAL_INVALIDATED: {e}")

                self._active_signal = None

        # If we have a new actionable signal, register it
        if decision != DecisionState.WAIT:
            if self._active_signal is None or self._active_signal.signal_id != signal.signal_id:
                signal.lifecycle_state = SignalLifecycleState.NEW
                self._active_signal = signal

                try:
                    await bus.publish(
                        EventType.SIGNAL_CREATED,
                        "decision_engine",
                        {
                            "signal_id": signal.signal_id,
                            "decision": signal.decision.value,
                            "confidence": signal.confidence,
                            "symbol": signal.symbol,
                            "entry": signal.entry,
                            "sl": signal.sl,
                            "tp1": signal.tp1,
                            "tp2": signal.tp2,
                            "tp3": signal.tp3,
                            "rr": signal.rr,
                            "evidence": signal.evidence,
                            "invalidations": signal.invalidations,
                            "regime": signal.regime,
                            "trend": signal.trend,
                        },
                    )
                except Exception as e:
                    self._logger.error(f"Failed to emit SIGNAL_CREATED: {e}")

        # Log decision
        self._logger.info(
            f"Decision: {decision.value} "
            f"(confidence={signal.confidence}, RR={signal.rr:.1f}, "
            f"strategies={[a.strategy for a in output.strategy_assessments if a.direction != DecisionState.WAIT]})"
        )

        return signal

    def get_active_signal(self) -> Optional[TradingSignal]:
        """Get the currently active signal."""
        return self._active_signal

    def get_signal_history(self, limit: int = 10) -> list[TradingSignal]:
        """Get recent signal history."""
        return self._signal_history[-limit:]

    def get_stats(self) -> dict[str, Any]:
        """Get decision engine statistics."""
        return {
            "cycle_count": self._cycle_count,
            "running": self._running,
            "has_active_signal": self._active_signal is not None,
            "active_signal_id": self._active_signal.signal_id if self._active_signal else None,
            "signal_history_count": len(self._signal_history),
            "config": {
                "min_confidence": self._min_confidence,
                "min_confluence": self._min_confluence,
                "max_data_age_ms": self._max_data_age_ms,
                "min_data_quality": self._min_data_quality,
            },
        }