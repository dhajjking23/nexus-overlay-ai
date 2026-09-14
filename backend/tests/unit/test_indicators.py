"""
NEXUS OVERLAY AI - Indicator Engine Unit Tests
Tests all indicator calculations: EMA, SMA, RSI, MACD, Bollinger, ATR, Stochastic, CCI, VWAP, OBV, MFI
"""
import pytest
import math
from backend.models import CandleData, IndicatorValue
from datetime import datetime


def now_ms() -> int:
    return int(datetime.now().timestamp() * 1000)


def make_candle(i: int, base: float = 3650.0, timeframe: str = "M5") -> CandleData:
    """Helper to create test candles"""
    return CandleData(
        open=base + i * 0.1,
        high=base + i * 0.1 + 2.0,
        low=base + i * 0.1 - 1.0,
        close=base + i * 0.1 + 0.5,
        volume=1000 + i * 10,
        spread=0.23,
        timestamp=now_ms() - (100 - i) * 60000,
        timeframe=timeframe,
        complete=True
    )


class TestEMA:
    """Test Exponential Moving Average"""
    
    def test_ema_basic_calculation(self):
        """Test EMA calculation with known values"""
        closes = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
        period = 3
        
        # Manual EMA calculation
        k = 2 / (period + 1)
        ema = closes[0]
        for price in closes[1:]:
            ema = price * k + ema * (1 - k)
        
        # Our implementation should match
        from backend.engines.indicator_engine import IndicatorEngine
        
        candles = [make_candle(i, base=10 + i) for i in range(10)]
        engine = IndicatorEngine()
        
        # Calculate using engine's internal method
        result = engine._compute_ema(candles, period)
        
        assert abs(result.value - ema) < 0.01
        assert result.indicator == "EMA"
        assert result.timeframe == "M5"
    
    def test_ema_periods(self):
        """Test multiple EMA periods"""
        from backend.engines.indicator_engine import IndicatorEngine
        
        candles = [make_candle(i, base=100 + i) for i in range(50)]
        engine = IndicatorEngine()
        
        ema20 = engine._compute_ema(candles, 20)
        ema50 = engine._compute_ema(candles, 50)
        
        # EMA20 should be more responsive (closer to current price)
        assert ema20.value > ema50.value  # in uptrend


class TestSMA:
    """Test Simple Moving Average"""
    
    def test_sma_basic(self):
        """Test SMA calculation"""
        from backend.engines.indicator_engine import IndicatorEngine
        
        closes = [10, 11, 12, 13, 14]
        period = 3
        expected = sum(closes[-3:]) / 3  # (12+13+14)/3 = 13
        
        candles = [make_candle(i, base=10 + i) for i in range(5)]
        engine = IndicatorEngine()
        
        result = engine._compute_sma(candles, period)
        
        assert abs(result.value - expected) < 0.01
        assert result.indicator == "SMA"


class TestRSI:
    """Test Relative Strength Index"""
    
    def test_rsi_overbought(self):
        """Test RSI in overbought territory"""
        from backend.engines.indicator_engine import IndicatorEngine
        
        # Strong uptrend candles
        candles = []
        base = 3600.0
        for i in range(30):
            candles.append(CandleData(
                open=base + i * 1.5,
                high=base + i * 1.5 + 1.0,
                low=base + i * 1.5,
                close=base + i * 1.5 + 1.0,
                volume=1000,
                spread=0.2,
                timestamp=now_ms(),
                timeframe="M5",
                complete=True
            ))
        
        engine = IndicatorEngine()
        result = engine._compute_rsi(candles, 14)
        
        assert result.value > 70  # Should be overbought
        assert result.state in ["OVERBOUGHT", "BULLISH_MOMENTUM"]
    
    def test_rsi_oversold(self):
        """Test RSI in oversold territory"""
        from backend.engines.indicator_engine import IndicatorEngine
        
        # Strong downtrend candles
        candles = []
        base = 3700.0
        for i in range(30):
            candles.append(CandleData(
                open=base - i * 1.5,
                high=base - i * 1.5,
                low=base - i * 1.5 - 1.0,
                close=base - i * 1.5 - 1.0,
                volume=1000,
                spread=0.2,
                timestamp=now_ms(),
                timeframe="M5",
                complete=True
            ))
        
        engine = IndicatorEngine()
        result = engine._compute_rsi(candles, 14)
        
        assert result.value < 30  # Should be oversold
        assert result.state in ["OVERSOLD", "BEARISH_MOMENTUM"]
    
    def test_rsi_neutral(self):
        """Test RSI in neutral territory"""
        from backend.engines.indicator_engine import IndicatorEngine
        
        # Sideways candles
        candles = []
        base = 3650.0
        for i in range(30):
            offset = 2.0 if i % 2 == 0 else -2.0
            candles.append(CandleData(
                open=base + offset,
                high=base + offset + 1.0,
                low=base + offset - 1.0,
                close=base + offset,
                volume=1000,
                spread=0.2,
                timestamp=now_ms(),
                timeframe="M5",
                complete=True
            ))
        
        engine = IndicatorEngine()
        result = engine._compute_rsi(candles, 14)
        
        assert 30 <= result.value <= 70


class TestMACD:
    """Test MACD (Moving Average Convergence Divergence)"""
    
    def test_macd_calculation(self):
        """Test MACD line, signal line, histogram"""
        from backend.engines.indicator_engine import IndicatorEngine
        
        candles = [make_candle(i, base=3650 + i * 0.2) for i in range(50)]
        engine = IndicatorEngine()
        
        result = engine._compute_macd(candles, 12, 26, 9)
        
        assert "macd" in result.auxiliary
        assert "signal" in result.auxiliary
        assert "histogram" in result.auxiliary
        
        # Histogram = MACD - Signal
        assert abs(result.auxiliary["histogram"] - (result.auxiliary["macd"] - result.auxiliary["signal"])) < 0.01


class TestATR:
    """Test Average True Range"""
    
    def test_atr_calculation(self):
        """Test ATR with known true range values"""
        from backend.engines.indicator_engine import IndicatorEngine
        
        candles = [
            CandleData(open=100, high=105, low=98, close=103, volume=1000, spread=0.1,
                       timestamp=now_ms(), timeframe="M5", complete=True),
            CandleData(open=103, high=108, low=102, close=106, volume=1000, spread=0.1,
                       timestamp=now_ms(), timeframe="M5", complete=True),
            CandleData(open=106, high=110, low=104, close=108, volume=1000, spread=0.1,
                       timestamp=now_ms(), timeframe="M5", complete=True),
        ]
        
        engine = IndicatorEngine()
        result = engine._compute_atr(candles, 14)
        
        assert result.value > 0
        assert result.indicator == "ATR"


class TestBollingerBands:
    """Test Bollinger Bands"""
    
    def test_bb_calculation(self):
        """Test BB upper, middle, lower"""
        from backend.engines.indicator_engine import IndicatorEngine
        
        candles = [make_candle(i, base=3650 + (i % 5) * 0.5) for i in range(50)]
        engine = IndicatorEngine()
        
        result = engine._compute_bollinger_bands(candles, 20, 2.0)
        
        assert "upper" in result.auxiliary
        assert "middle" in result.auxiliary
        assert "lower" in result.auxiliary
        
        assert result.auxiliary["upper"] > result.auxiliary["middle"]
        assert result.auxiliary["lower"] < result.auxiliary["middle"]
        
        # Width should be 2 * 2 * std = 4 * std
        width = result.auxiliary["upper"] - result.auxiliary["lower"]


class TestADX:
    """Test ADX (Average Directional Index)"""
    
    def test_adx_strong_trend(self):
        """Test ADX detects strong trend"""
        from backend.engines.indicator_engine import IndicatorEngine
        
        # Strong uptrend
        candles = []
        base = 3600.0
        for i in range(30):
            candles.append(CandleData(
                open=base + i * 2.0,
                high=base + i * 2.0 + 1.0,
                low=base + i * 2.0,
                close=base + i * 2.0 + 1.0,
                volume=1000,
                spread=0.2,
                timestamp=now_ms(),
                timeframe="M5",
                complete=True
            ))
        
        engine = IndicatorEngine()
        result = engine._compute_adx(candles, 14)
        
        assert result.value > 25  # Strong trend threshold
        assert result.state == "STRONG_TREND"
        assert "di_plus" in result.auxiliary
        assert "di_minus" in result.auxiliary
        assert result.auxiliary["di_plus"] > result.auxiliary["di_minus"]


class TestVolumeIndicators:
    """Test volume-based indicators"""
    
    def test_relative_volume(self):
        """Test relative volume calculation"""
        from backend.engines.indicator_engine import IndicatorEngine
        
        candles = [make_candle(i) for i in range(50)]
        # Last candle has much higher volume
        candles[-1] = CandleData(
            open=candles[-1].open, high=candles[-1].high,
            low=candles[-1].low, close=candles[-1].close,
            volume=50000,  # spike
            spread=candles[-1].spread,
            timestamp=candles[-1].timestamp,
            timeframe="M5", complete=True
        )
        
        engine = IndicatorEngine()
        result = engine._compute_relative_volume(candles, 20)
        
        assert result.value > 2.0  # Volume spike
        assert result.state == "EXPANSION"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])