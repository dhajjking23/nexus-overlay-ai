"""
NEXUS OVERLAY AI - Data Models Unit Tests
Tests protocol messages, dataclasses, and utility functions
"""
import json
import pytest
from backend.models import (
    ProtocolMessage, MessageType, DecisionState, SignalLifecycleState,
    TickData, CandleData, SymbolInfo, IndicatorValue, MarketRegime,
    TrendDirection, PatternType, StructureType, LiquidityEventType,
    ZoneType, EntryType, SLMethod, TPMethod, AIProviderType,
    pips_to_price, price_to_pips, now_ms,
    TradingSignal, DecisionLogEntry, SystemStatus, ConfidenceModel
)


class TestProtocolMessage:
    """Test protocol message serialization"""
    
    def test_message_to_json(self):
        """Test serializing message to JSON"""
        msg = ProtocolMessage(
            message_type=MessageType.MARKET_TICK,
            sequence=100,
            symbol="XAUUSD",
            timeframe="M5",
            payload={"bid": 3652.42, "ask": 3652.65, "spread": 0.23}
        )
        
        json_str = msg.to_json()
        data = json.loads(json_str)
        
        assert data["message_type"] == "MARKET_TICK"
        assert data["sequence"] == 100
        assert data["symbol"] == "XAUUSD"
        assert data["payload"]["bid"] == 3652.42
    
    def test_message_from_json(self):
        """Test deserializing message from JSON"""
        msg = ProtocolMessage(
            message_type=MessageType.CANDLE_CLOSED,
            sequence=200,
            symbol="XAUUSD",
            timeframe="H1",
            payload={"open": 3650.0, "high": 3655.0, "low": 3648.0, "close": 3652.0}
        )
        
        json_str = msg.to_json()
        restored = ProtocolMessage.from_json(json_str)
        
        assert restored.message_type == MessageType.CANDLE_CLOSED
        assert restored.sequence == 200
        assert restored.timeframe == "H1"
        assert restored.payload["open"] == 3650.0
    
    def test_message_roundtrip(self):
        """Test serialize -> deserialize roundtrip"""
        original = ProtocolMessage(
            message_type=MessageType.MARKET_SNAPSHOT,
            sequence=999999,
            symbol="XAUUSD",
            payload={"price": 3652.42, "confidence": 87, "evidence": ["test1", "test2"]}
        )
        
        restored = ProtocolMessage.from_json(original.to_json())
        assert restored.payload["evidence"] == ["test1", "test2"]
        assert restored.payload["confidence"] == 87


class TestEnums:
    """Test enum definitions"""
    
    def test_decision_states(self):
        """Verify all decision states exist"""
        assert DecisionState.BUY.value == "BUY"
        assert DecisionState.SELL.value == "SELL"
        assert DecisionState.WAIT.value == "WAIT"
    
    def test_signal_lifecycle(self):
        """Verify signal lifecycle states"""
        states = [s.value for s in SignalLifecycleState]
        assert "NEW" in states
        assert "CONFIRMED" in states
        assert "ACTIVE" in states
        assert "WEAKENING" in states
        assert "INVALIDATED" in states
        assert "EXPIRED" in states
        assert "COMPLETED" in states
    
    def test_market_regimes(self):
        """Verify market regime values"""
        assert MarketRegime.TRENDING_BULLISH.value == "TRENDING_BULLISH"
        assert MarketRegime.RANGE.value == "RANGE"
        assert MarketRegime.UNCERTAIN.value == "UNCERTAIN"


class TestUtilityFunctions:
    """Test utility functions"""
    
    def test_pips_to_price_xauusd(self):
        """XAUUSD: 10 pips = 0.10 price"""
        assert pips_to_price(10, digits=2) == 0.10
        assert pips_to_price(1, digits=2) == 0.01
    
    def test_price_to_pips_xauusd(self):
        """XAUUSD: 0.50 price = 50 pips"""
        assert price_to_pips(0.50, digits=2) == 50.0
        assert price_to_pips(1.0, digits=2) == 100.0
    
    def test_pips_roundtrip(self):
        """pips -> price -> pips should be identity"""
        original = 42.5
        price = pips_to_price(original, 2)
        result = price_to_pips(price, 2)
        assert abs(result - original) < 0.01
    
    def test_now_ms(self):
        """now_ms should return current timestamp in milliseconds"""
        result = now_ms()
        assert result > 1700000000000  # After 2023


class TestTradingSignal:
    """Test TradingSignal dataclass"""
    
    def test_signal_to_dict(self):
        """Test serializing signal to dict"""
        signal = TradingSignal(
            decision=DecisionState.SELL,
            confidence=87,
            symbol="XAUUSD",
            entry=3652.40,
            sl=3655.10,
            tp1=3649.70,
            tp2=3646.80,
            tp3=3643.90,
            rr=2.1,
            trend="BEARISH",
            regime="TRENDING_BEARISH",
            evidence=["test evidence"],
            invalidations=["test invalidation"],
            timestamp=now_ms()
        )
        
        d = signal.to_dict()
        
        assert d["decision"] == "SELL"
        assert d["confidence"] == 87
        assert d["entry"] == 3652.40
        assert d["sl"] == 3655.10
        assert len(d["evidence"]) == 1
    
    def test_signal_defaults(self):
        """Test signal default values"""
        signal = TradingSignal(
            decision=DecisionState.WAIT,
            confidence=0,
            symbol="XAUUSD",
            entry=0, sl=0, tp1=0, tp2=0, tp3=0,
            rr=0, trend="NEUTRAL", regime="UNCERTAIN",
            evidence=[], invalidations=[], timestamp=0
        )
        
        assert signal.lifecycle_state == SignalLifecycleState.NEW
        assert signal.data_quality_score == 100.0
        assert signal.signal_id == ""


class TestSystemStatus:
    """Test system status"""
    
    def test_system_status_fields(self):
        """Verify SystemStatus has all required fields"""
        status = SystemStatus(
            status="ONLINE",
            mt5_connected=True,
            data_live=True,
            ai_ready=True,
            decision_ready=True,
            websocket_clients=2,
            last_tick=now_ms(),
            last_candle=now_ms(),
            data_quality=95.0,
            engine_status={"indicators": "OK", "structure": "OK"},
            memory_mb=128.0,
            cpu_percent=15.0
        )
        
        assert status.status == "ONLINE"
        assert status.websocket_clients == 2
        assert "indicators" in status.engine_status


class TestConfidenceModel:
    """Test confidence model dataclass"""
    
    def test_confidence_fields(self):
        """All confidence components must exist"""
        cm = ConfidenceModel(
            technical_score=85.0,
            risk_score=90.0,
            data_quality_score=95.0,
            ai_confidence=80.0,
            mtf_agreement=90.0,
            final_confidence=87.0,
            timestamp=now_ms()
        )
        
        assert cm.technical_score == 85.0
        assert cm.final_confidence == 87.0
        assert cm.timestamp > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])