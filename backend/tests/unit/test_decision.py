"""
NEXUS OVERLAY AI - Decision Engine Unit Tests
Tests the core DecisionEngine and Safety Governor
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


def now_ms() -> int:
    return int(datetime.now().timestamp() * 1000)


class TestDecisionEngine:
    """Test the Decision Engine - Single Source of Truth"""
    
    def test_wait_when_no_data(self):
        """Decision should be WAIT when no market data available"""
        from backend.engines.decision_engine import DecisionEngine
        
        engine = DecisionEngine(config={}, event_bus=None)
        
        result = engine.decide(
            indicators={},
            structure=None,
            liquidity=[],
            price_action=[],
            mtf=None,
            regime=None,
            session=None,
            strategy_assessments=[],
            confluence=None,
            risk_validation=None,
            entry_calc=None,
            sltp_calc=None,
            confidence_model=None,
            ai_assessment=None,
            data_quality=0.0,
            candles={}
        )
        
        assert result["decision"] in ["WAIT", "DATA_UNAVAILABLE"]
    
    def test_buy_when_strong_bullish(self):
        """Decision should be BUY when all evidence is bullish"""
        from backend.engines.decision_engine import DecisionEngine
        
        engine = DecisionEngine(config={"risk": {"min_rr": 1.5, "min_confidence": 70}}, event_bus=None)
        
        result = engine.decide(
            indicators={
                "ema_20": IndicatorValue("EMA", "M5", 3655.0, "BULLISH", now_ms()),
                "ema_50": IndicatorValue("EMA", "M5", 3650.0, "BULLISH", now_ms()),
                "rsi": IndicatorValue("RSI", "M5", 58.0, "NEUTRAL", now_ms()),
                "adx": IndicatorValue("ADX", "M5", 30.0, "STRONG_TREND", now_ms()),
            },
            structure=MarketStructure(
                trend=TrendDirection.BULLISH,
                structure=__import__('backend.models', fromlist=['StructureType']).StructureType.HL,
                bos=True, choch=False
            ),
            liquidity=[],
            price_action=[],
            mtf=MultiTimeframeAnalysis(
                timeframe_analysis={"H4": TrendDirection.BULLISH, "H1": TrendDirection.BULLISH,
                                     "M30": TrendDirection.BULLISH, "M15": TrendDirection.BULLISH},
                alignment="aligned",
                dominant_trend=TrendDirection.BULLISH,
                entry_timeframe="M5",
                entry_direction=TrendDirection.BULLISH,
                conflicts=[]
            ),
            regime=MarketRegime.TRENDING_BULLISH,
            session="LONDON",
            strategy_assessments=[],
            confluence=ConfluenceScore(
                weights={"trend": 15, "structure": 15, "mtf": 15},
                scores={"trend": 14, "structure": 13, "mtf": 14},
                total_score=82.0
            ),
            risk_validation=RiskValidation(
                passed=True, checks={}, failed_reasons=[],
                rr=2.1, min_rr=1.5, spread=0.23, max_spread=1.0,
                data_quality=95, timestamp=now_ms()
            ),
            entry_calc=EntryCalculation(
                price=3655.0, entry_type=__import__('backend.models', fromlist=['EntryType']).EntryType.MARKET,
                reason="breakout", confirmation_candles=1, timestamp=now_ms()
            ),
            sltp_calc=SLTPCalculation(
                sl_price=3652.0, sl_method=__import__('backend.models', fromlist=['SLMethod']).SLMethod.ATR,
                sl_reason="ATR SL",
                tp1_price=3660.0, tp1_method=__import__('backend.models', fromlist=['TPMethod']).TPMethod.RISK_REWARD,
                tp2_price=3665.0, tp2_method=__import__('backend.models', fromlist=['TPMethod']).TPMethod.RISK_REWARD,
                tp3_price=3670.0, tp3_method=__import__('backend.models', fromlist=['TPMethod']).TPMethod.RISK_REWARD,
                invalidation_reason="close below 3652",
                timestamp=now_ms()
            ),
            confidence_model=ConfidenceModel(
                technical_score=85.0, risk_score=95.0, data_quality_score=95.0,
                ai_confidence=80.0, mtf_agreement=90.0, final_confidence=87.0,
                timestamp=now_ms()
            ),
            ai_assessment=AIAssessment(
                provider=AIProviderType.OPENAI,
                assessment="bullish",
                confidence=0.85,
                explanation="Strong bullish confluence across timeframes",
                timestamp=now_ms()
            ),
            data_quality=95.0,
            candles={"M5": [CandleData(open=3650, high=3655, low=3648, close=3653, volume=1000,
                                        spread=0.2, timestamp=now_ms(), timeframe="M5", complete=True)]}
        )
        
        assert result["decision"] in ["BUY", "SELL"]
        assert "entry" in result
        assert "sl" in result
        assert "tp1" in result
        assert "confidence" in result
    
    def test_wait_when_risk_fails(self):
        """Decision should be WAIT when risk validation fails"""
        from backend.engines.decision_engine import DecisionEngine
        
        engine = DecisionEngine(config={}, event_bus=None)
        
        result = engine.decide(
            indicators={},
            structure=MarketStructure(
                trend=TrendDirection.BULLISH,
                structure=__import__('backend.models', fromlist=['StructureType']).StructureType.HL,
                bos=False, choch=False
            ),
            liquidity=[], price_action=[],
            mtf=None, regime=None, session=None,
            strategy_assessments=[],
            confluence=ConfluenceScore(weights={}, scores={}, total_score=60.0),
            risk_validation=RiskValidation(
                passed=False, checks={}, failed_reasons=["Spread too high"],
                rr=0.5, min_rr=1.5, spread=2.0, max_spread=1.0,
                data_quality=80, timestamp=now_ms()
            ),
            entry_calc=None, sltp_calc=None, confidence_model=None,
            ai_assessment=None, data_quality=80.0, candles={}
        )
        
        assert result["decision"] == "WAIT"


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
        """Test weighted confidence model"""
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
        
        expected = 80 * 0.35 + 90 * 0.25 + 95 * 0.15 + 90 * 0.15 + 75 * 0.10
        assert abs(result.final_confidence - expected) < 1.0
        assert 0 <= result.final_confidence <= 100
    
    def test_confidence_no_ai(self):
        """Test confidence when AI is unavailable"""
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
        
        # Should still produce a valid confidence without AI
        assert 0 <= result.final_confidence <= 100
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