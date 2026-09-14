"""
NEXUS OVERLAY AI - Test Configuration
Shared pytest fixtures for unit and integration tests
"""
import asyncio
import pytest
import sys
import os
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def now_ms() -> int:
    return int(datetime.now().timestamp() * 1000)


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_candles():
    """Generate sample candle data for testing"""
    from backend.models import CandleData
    
    base_price = 3650.0
    candles = []
    for i in range(100):
        o = base_price + (i * 0.5)
        h = o + 2.0 + (i % 5)
        l = o - 1.5 - (i % 3)
        c = o + 0.5 - (i % 2)
        candles.append(CandleData(
            open=o, high=h, low=l, close=c,
            volume=1000 + (i * 50), spread=0.23,
            timestamp=now_ms() - (100 - i) * 60000,
            timeframe="M5", complete=True
        ))
    return candles


@pytest.fixture
def sample_ticks():
    """Generate sample tick data"""
    from backend.models import TickData
    
    ticks = []
    base = 3652.0
    for i in range(500):
        ticks.append(TickData(
            bid=base + (i * 0.01),
            ask=base + 0.23 + (i * 0.01),
            spread=0.23,
            volume=10 + (i % 20),
            timestamp=now_ms() - (500 - i) * 100
        ))
    return ticks


@pytest.fixture
def sample_config():
    """Minimal test configuration"""
    return {
        "symbol": {"name": "XAUUSD", "digits": 2, "point": 0.01},
        "timeframes": {
            "primary": "M1",
            "analysis": ["M1", "M3", "M5", "M15", "M30", "H1", "H4"],
            "candle_history": {"M1": 100, "M5": 100, "M15": 50, "H1": 50, "H4": 30}
        },
        "indicators": {
            "trend": {"ema_periods": [20, 50, 100, 200]},
            "momentum": {"rsi_period": 14, "rsi_oversold": 30, "rsi_overbought": 70},
            "volatility": {"atr_period": 14},
            "trend_strength": {"adx_period": 14}
        },
        "risk": {"min_rr": 1.5, "min_confidence": 70, "max_spread": 1.0},
        "confluence": {
            "trend": 15, "structure": 15, "mtf": 15,
            "price_action": 10, "liquidity": 10, "momentum": 10,
            "volatility": 10, "zone": 5, "session": 5, "risk_reward": 5
        }
    }


@pytest.fixture
def bullish_trend_candles():
    """Candles showing clear bullish trend"""
    from backend.models import CandleData
    
    candles = []
    base = 3640.0
    for i in range(200):
        price = base + i * 0.3
        candles.append(CandleData(
            open=price, high=price + 1.5,
            low=price - 0.5, close=price + 1.0,
            volume=1000 + i * 10, spread=0.2,
            timestamp=now_ms() - (200 - i) * 60000,
            timeframe="M5", complete=True
        ))
    return candles


@pytest.fixture
def bearish_trend_candles():
    """Candles showing clear bearish trend"""
    from backend.models import CandleData
    
    candles = []
    base = 3700.0
    for i in range(200):
        price = base - i * 0.3
        candles.append(CandleData(
            open=price, high=price + 0.5,
            low=price - 1.5, close=price - 1.0,
            volume=1000 + i * 10, spread=0.2,
            timestamp=now_ms() - (200 - i) * 60000,
            timeframe="M5", complete=True
        ))
    return candles


@pytest.fixture
def ranging_candles():
    """Candles showing range-bound market"""
    from backend.models import CandleData
    
    import math
    candles = []
    base = 3650.0
    for i in range(200):
        offset = math.sin(i * 0.1) * 5.0
        price = base + offset
        candles.append(CandleData(
            open=price, high=price + 1.0,
            low=price - 1.0, close=price + offset * 0.01,
            volume=800 + int(abs(offset) * 20), spread=0.25,
            timestamp=now_ms() - (200 - i) * 60000,
            timeframe="M5", complete=True
        ))
    return candles
