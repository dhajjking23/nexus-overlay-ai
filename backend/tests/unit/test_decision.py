"""
NEXUS OVERLAY AI - Decision Engine Unit Tests
Tests the core DecisionEngine (evaluate_thesis API), Safety Governor,
Confidence Model, and Risk Engine.
"""
import pytest
from datetime import datetime
from backend.models import (
    DecisionState, SignalLifecycleState, RiskValidation,
    EntryCalculation, SLTPCalculation, ConfidenceModel,
    AIAssessment, AIProviderType, MultiTimeframeAnalysis,
    ConfluenceScore, TrendDirection, MarketRegime,
    IndicatorValue, PriceActionPattern, MarketStructure,
    LiquidityEvent, Zone, CandleData
)
from backend.engines.trade_thesis import (
    TradeThesis, Direction, SetupType, MarketRegime as ThesisMarketRegime,
    HTFBias, RiskFlag,
)
from backend.engines.market_snapshot import MarketSnapshot, generate_snapshot_id


def now_ms() -> int:
    return int(datetime.now().timestamp() * 1000)


# ═══════════════════════════════════════════════════════════════════
# Helper builders for the new evaluate_thesis() API
# ═══════════════════════════════════════════════════════════════════

def _good_snapshot(**overrides) -> MarketSnapshot:
    """A market snapshot that passes the data gate."""
    defaults = dict(
        symbol="XAUUSD",
        bid=3652.0,
        ask=3652.23,
        data_quality=95.0,
        data_age_ms=500,
        market_open=True,
        transport_connected=True,
    )
    defaults.update(overrides)
    return MarketSnapshot(**defaults)


def _bad_snapshot(**overrides) -> MarketSnapshot:
    """A snapshot that fails the data gate (no price data)."""
    defaults = dict(
        symbol="XAUUSD",
        bid=0.0,
        ask=0.0,
        data_quality=0.0,
        data_age_ms=0,
        market_open=True,
        transport_connected=True,
    )
    defaults.update(overrides)
    return MarketSnapshot(**defaults)


class TestDecisionEngine:
    """Test the Decision Engine — evaluate_thesis() API"""

    def test_wait_when_no_data(self):
        """Decision should be WAIT when no market data available"""
        from backend.engines.decision_engine import DecisionEngine

        engine = DecisionEngine(config={})

        # Build a BUY thesis that would normally pass
        thesis = TradeThesis(
            direction=Direction.BUY,
            setup_type=SetupType.TREND_FOLLOWING,
            market_regime=ThesisMarketRegime.TRENDING_BULLISH,
            higher_timeframe_bias=HTFBias.BULLISH,
            entry_reason=["EMA_ALIGNMENT", "BOS_BULLISH"],
            entry=3655.0, sl=3652.0, tp1=3660.0, tp2=3665.0, tp3=3670.0,
            rr=1.67,
            risk_flags=[],
            snapshot_id="test",
        )

        # Snapshot with no price data → DATA_GATE should produce WAIT
        snapshot = _bad_snapshot()

        result = engine.evaluate_thesis(thesis, snapshot)

        assert result.decision in (Direction.WAIT, Direction.NO_TRADE)
        assert result.score == 0

    def test_buy_when_strong_bullish(self):
        """Decision should be BUY when all evidence is bullish and gates pass"""
        from backend.engines.decision_engine import DecisionEngine
        from backend.engines.evidence_graph import (
            EvidenceGraph, EvidenceAssessment, EvidenceItem, ConflictSeverity,
        )
        from backend.engines.evidence_graph import Direction as EvDirection

        engine = DecisionEngine(config={
            "min_confidence": 55,
            "max_data_age_ms": 30_000,
            "min_data_quality": 30.0,
            "min_rr": 1.0,
        })

        thesis = TradeThesis(
            direction=Direction.BUY,
            setup_type=SetupType.TREND_FOLLOWING,
            market_regime=ThesisMarketRegime.TRENDING_BULLISH,
            higher_timeframe_bias=HTFBias.BULLISH,
            entry_reason=["EMA_ALIGNMENT", "BOS_BULLISH", "HTF_BULLISH"],
            supporting_evidence=[],
            counter_evidence=[],
            entry=3655.0,
            sl=3652.0,
            tp1=3660.0,
            tp2=3665.0,
            tp3=3670.0,
            rr=1.67,
            risk_flags=[],
            strategy_sources=["TREND_FOLLOWING"],
            snapshot_id="test-snap-001",
        )

        snapshot = _good_snapshot()

        # Build evidence assessment with strong bullish evidence
        graph = EvidenceGraph()
        graph.add_evidence(EvidenceItem(
            source="structure", reason_code="BOS_BULLISH",
            direction=EvDirection.BULLISH, strength=85.0,
            description="H1 bullish break of structure", timeframe="H1",
        ))
        graph.add_evidence(EvidenceItem(
            source="mtf", reason_code="MTF_ALIGNED",
            direction=EvDirection.BULLISH, strength=90.0,
            description="Multi-timeframe aligned bullish", timeframe="H4",
        ))
        graph.add_evidence(EvidenceItem(
            source="price_action", reason_code="BULLISH_ENGULFING",
            direction=EvDirection.BULLISH, strength=75.0,
            description="M5 bullish engulfing", timeframe="M5",
        ))
        evidence = graph.assess()

        result = engine.evaluate_thesis(thesis, snapshot, evidence_assessment=evidence)

        assert result.decision == Direction.BUY
        assert result.score > 0
        assert result.thesis is thesis
        assert result.snapshot_id == snapshot.snapshot_id
        assert result.thesis.entry == 3655.0
        assert result.thesis.sl == 3652.0
        assert result.thesis.tp1 == 3660.0

    def test_wait_when_risk_fails(self):
        """Decision should be WAIT when risk validation has CRITICAL flags"""
        from backend.engines.decision_engine import DecisionEngine

        from backend.engines.decision_engine import DecisionEngine
        from backend.engines.evidence_graph import EvidenceGraph, EvidenceItem
        from backend.engines.evidence_graph import Direction as EvDirection

        engine = DecisionEngine(config={})

        thesis = TradeThesis(
            direction=Direction.BUY,
            setup_type=SetupType.TREND_FOLLOWING,
            market_regime=ThesisMarketRegime.TRENDING_BULLISH,
            higher_timeframe_bias=HTFBias.BULLISH,
            entry_reason=["BOS_BULLISH"],
            entry=3655.0,
            sl=3652.0,
            tp1=3660.0,
            rr=1.67,
            risk_flags=[
                RiskFlag(code="SPREAD_RISK", severity="CRITICAL",
                         description="Spread too high: 3.5 pips"),
            ],
            snapshot_id="test-risk",
        )

        snapshot = _good_snapshot()

        # Provide evidence so evidence gate passes, then risk gate catches CRITICAL flag
        graph = EvidenceGraph()
        graph.add_evidence(EvidenceItem(
            source="structure", reason_code="BOS_BULLISH",
            direction=EvDirection.BULLISH, strength=85.0,
            description="H1 bullish BOS", timeframe="H1",
        ))
        evidence = graph.assess()

        result = engine.evaluate_thesis(thesis, snapshot, evidence_assessment=evidence)

        assert result.decision == Direction.WAIT
        assert "RISK_REJECTED" in result.reason_codes

    def test_wait_when_htf_conflicting(self):
        """Decision should be WAIT when higher timeframe is conflicting"""
        from backend.engines.decision_engine import DecisionEngine
        from backend.engines.evidence_graph import (
            EvidenceGraph, EvidenceItem,
        )
        from backend.engines.evidence_graph import Direction as EvDirection

        engine = DecisionEngine(config={})

        thesis = TradeThesis(
            direction=Direction.BUY,
            setup_type=SetupType.TREND_FOLLOWING,
            market_regime=ThesisMarketRegime.TRENDING_BULLISH,
            higher_timeframe_bias=HTFBias.CONFLICTING,
            entry_reason=["BOS_BULLISH"],
            entry=3655.0, sl=3652.0, tp1=3660.0, rr=1.67,
            risk_flags=[],
            snapshot_id="test-htf",
        )

        snapshot = _good_snapshot()

        # Provide valid evidence so evidence gate passes
        graph = EvidenceGraph()
        graph.add_evidence(EvidenceItem(
            source="structure", reason_code="BOS_BULLISH",
            direction=EvDirection.BULLISH, strength=85.0,
            description="H1 bullish BOS", timeframe="H1",
        ))
        graph.add_evidence(EvidenceItem(
            source="mtf", reason_code="MTF_CONFLICT",
            direction=EvDirection.BEARISH, strength=70.0,
            description="H4 bearish but M5 bullish", timeframe="H4",
        ))
        evidence = graph.assess()

        result = engine.evaluate_thesis(thesis, snapshot, evidence_assessment=evidence)

        assert result.decision == Direction.WAIT
        assert "MTF_CONFLICT" in result.reason_codes

    def test_no_trade_when_thesis_is_no_trade(self):
        """Decision should be NO_TRADE when thesis direction is NO_TRADE"""
        from backend.engines.decision_engine import DecisionEngine

        engine = DecisionEngine(config={})

        thesis = TradeThesis(
            direction=Direction.NO_TRADE,
            setup_type=SetupType.TREND_FOLLOWING,
            market_regime=ThesisMarketRegime.UNCERTAIN,
            higher_timeframe_bias=HTFBias.UNKNOWN,
            entry_reason=["NO_SETUP"],
            risk_flags=[],
            snapshot_id="test-no-trade",
        )

        snapshot = _good_snapshot()

        result = engine.evaluate_thesis(thesis, snapshot)

        assert result.decision == Direction.NO_TRADE


class TestSafetyGovernor:
    """Test Safety Governor - global safety layer"""

    def test_stale_data_rejected(self):
        """Should reject when data is stale"""
        from backend.engines.safety_governor import SafetyGovernor

        governor = SafetyGovernor(config={"safety": {"stale_data": True}})

        result = governor.check(
            last_tick_age_ms=15000,  # 15 seconds old
            spread=0.23,
            volatility_atr=2.5,
            atr_avg=2.0,
            mtf_aligned=True,
            data_quality=80.0,
            connected=True
        )

        assert result["passed"] is False
        assert any("stale" in r.lower() or "data" in r.lower() for r in result["failed_reasons"])

    def test_excessive_spread_rejected(self):
        """Should reject when spread is too high"""
        from backend.engines.safety_governor import SafetyGovernor

        governor = SafetyGovernor(config={"safety": {"excessive_spread": True, "max_spread": 1.0}})

        result = governor.check(
            last_tick_age_ms=1000,
            spread=3.5,
            volatility_atr=2.0,
            atr_avg=2.0,
            mtf_aligned=True,
            data_quality=95.0,
            connected=True
        )

        assert result["passed"] is False
        assert any("spread" in r.lower() for r in result["failed_reasons"])

    def test_disconnected_rejected(self):
        """Should reject when transport is disconnected"""
        from backend.engines.safety_governor import SafetyGovernor

        governor = SafetyGovernor(config={"safety": {"transport_disconnected": True}})

        result = governor.check(
            last_tick_age_ms=1000,
            spread=0.23,
            volatility_atr=2.0,
            atr_avg=2.0,
            mtf_aligned=True,
            data_quality=95.0,
            connected=False
        )

        assert result["passed"] is False
        assert any("connect" in r.lower() for r in result["failed_reasons"])

    def test_all_good(self):
        """Should pass when everything is fine"""
        from backend.engines.safety_governor import SafetyGovernor

        governor = SafetyGovernor(config={"safety": {"max_spread": 1.0}})

        result = governor.check(
            last_tick_age_ms=500,
            spread=0.23,
            volatility_atr=2.0,
            atr_avg=2.0,
            mtf_aligned=True,
            data_quality=95.0,
            connected=True
        )

        assert result["passed"] is True
        assert len(result["failed_reasons"]) == 0


class TestConfidenceModel:
    """Test structured confidence calculation"""

    def test_confidence_calculation(self):
        """Test weighted confidence model — deterministic_score is AI-free"""
        from backend.engines.confidence_model import ConfidenceModelEngine

        engine = ConfidenceModelEngine(config={
            "decision": {
                "confidence_weights": {
                    "technical_confluence": 0.35,
                    "mtf_agreement": 0.25,
                    "risk_quality": 0.15,
                    "data_quality": 0.15,
                    "ai_assessment": 0.10
                }
            }
        })

        result = engine.calculate(
            technical_confluence=80.0,
            mtf_agreement=90.0,
            risk_quality=95.0,
            data_quality=90.0,
            ai_confidence=75.0
        )

        # deterministic_score excludes AI — only technical, mtf, risk, data
        w_sum = 0.35 + 0.25 + 0.15 + 0.15
        expected_det = (80 * 0.35 + 90 * 0.25 + 95 * 0.15 + 90 * 0.15) / w_sum
        assert abs(result.deterministic_score - expected_det) < 1.0
        assert 0 <= result.deterministic_score <= 100

        # ai_advisory_score is separate
        assert result.ai_advisory_score == 75.0

    def test_confidence_no_ai(self):
        """Test confidence when AI is unavailable — deterministic_score unchanged"""
        from backend.engines.confidence_model import ConfidenceModelEngine

        engine = ConfidenceModelEngine(config={
            "decision": {
                "confidence_weights": {
                    "technical_confluence": 0.35,
                    "mtf_agreement": 0.25,
                    "risk_quality": 0.15,
                    "data_quality": 0.15,
                    "ai_assessment": 0.10
                }
            }
        })

        result = engine.calculate(
            technical_confluence=80.0,
            mtf_agreement=90.0,
            risk_quality=95.0,
            data_quality=90.0,
            ai_confidence=0.0  # AI unavailable
        )

        # deterministic_score is identical regardless of AI
        w_sum = 0.35 + 0.25 + 0.15 + 0.15
        expected_det = (80 * 0.35 + 90 * 0.25 + 95 * 0.15 + 90 * 0.15) / w_sum
        assert 0 <= result.deterministic_score <= 100
        assert abs(result.deterministic_score - expected_det) < 1.0
        assert result.ai_advisory_score == 0.0
        assert result.ai_confidence == 0.0


class TestRiskEngine:
    """Test Risk Engine validation"""

    def test_risk_passes_on_good_setup(self):
        """Risk should pass for valid setup"""
        from backend.engines.risk_engine import RiskEngine

        engine = RiskEngine(config={"risk": {"min_rr": 1.5, "max_spread": 1.0}})

        result = engine.validate(
            spread=0.23,
            volatility_atr=2.5,
            rr=2.1,
            sl_distance=3.0,
            tp1_distance=6.3,
            regime=MarketRegime.TRENDING_BULLISH,
            data_quality=95.0,
            session_active=True,
            signal_age_candles=1,
            mtf_conflicts=0,
            last_tick_age_ms=1000
        )

        assert result.passed is True

    def test_risk_rejects_low_rr(self):
        """Risk should reject when RR is too low"""
        from backend.engines.risk_engine import RiskEngine

        engine = RiskEngine(config={"risk": {"min_rr": 1.5, "max_spread": 1.0}})

        result = engine.validate(
            spread=0.23,
            volatility_atr=2.5,
            rr=0.8,
            sl_distance=5.0,
            tp1_distance=4.0,
            regime=MarketRegime.TRENDING_BULLISH,
            data_quality=95.0,
            session_active=True,
            signal_age_candles=1,
            mtf_conflicts=0,
            last_tick_age_ms=1000
        )

        assert result.passed is False
        assert any("rr" in r.lower() or "risk" in r.lower() for r in result.failed_reasons)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
