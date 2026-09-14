"""
NEXUS OVERLAY AI - Regime Engine
Classifies market regime: trending, range, volatility, breakout, etc.
"""
from __future__ import annotations
import logging
from typing import Any
from backend.models import CandleData, IndicatorValue, MarketRegime, now_ms

logger = logging.getLogger(__name__)


class RegimeEngine:
    def __init__(self, config: dict[str, Any] | None = None, event_bus=None):
        self._config = config or {}
        self._event_bus = event_bus
        rc = self._config.get("regime", {})
        self._adx_strong = rc.get("trend_adx_threshold", 25)
        self._vol_mult_high = rc.get("volatility_atr_multiplier", 1.5)
        self._vol_mult_low = rc.get("range_atr_multiplier", 0.8)
        self._breakout_candles = rc.get("breakout_confirmation_candles", 3)
        self._consolidation_candles = rc.get("consolidation_candles", 10)

    def analyze(self, candles: list[CandleData], indicators: dict[str, IndicatorValue] | None = None) -> dict:
        if not candles or len(candles) < 20:
            return {"regime": MarketRegime.UNCERTAIN, "confidence": 0.3, "reason": "insufficient_data"}
        indicators = indicators or {}
        adx_val = 20.0
        for k, v in indicators.items():
            if v.indicator == "ADX":
                adx_val = v.value
                break
        closes = [c.close for c in candles[-50:]]
        ranges = [c.high - c.low for c in candles[-50:]]
        avg_range = sum(ranges[-20:]) / 20 if len(ranges) >= 20 else sum(ranges) / len(ranges) if ranges else 1.0
        long_avg_range = sum(ranges) / len(ranges) if ranges else 1.0
        recent_change = abs(closes[-1] - closes[-20]) if len(closes) >= 20 else 0
        vol_ratio = avg_range / long_avg_range if long_avg_range > 0 else 1.0
        is_expanding = vol_ratio > self._vol_mult_high
        is_contracting = vol_ratio < self._vol_mult_low
        bullish_candles = sum(1 for c in candles[-self._breakout_candles:] if c.close > c.open)
        bearish_candles = sum(1 for c in candles[-self._breakout_candles:] if c.close < c.open)
        if adx_val >= self._adx_strong:
            if closes[-1] > closes[-20]:
                return {"regime": MarketRegime.TRENDING_BULLISH, "confidence": 0.85,
                        "reason": f"ADX={adx_val:.1f},strong_up", "adx": adx_val, "vol_ratio": vol_ratio}
            else:
                return {"regime": MarketRegime.TRENDING_BEARISH, "confidence": 0.85,
                        "reason": f"ADX={adx_val:.1f},strong_down", "adx": adx_val, "vol_ratio": vol_ratio}
        if is_expanding and (bullish_candles == self._breakout_candles or bearish_candles == self._breakout_candles):
            direction = "bullish" if bullish_candles > bearish_candles else "bearish"
            return {"regime": MarketRegime.BREAKOUT, "confidence": 0.80,
                    "reason": f"expansion+directional_{direction}", "adx": adx_val, "vol_ratio": vol_ratio}
        if is_expanding:
            return {"regime": MarketRegime.HIGH_VOLATILITY, "confidence": 0.75,
                    "reason": f"high_vol_ratio={vol_ratio:.2f}", "adx": adx_val, "vol_ratio": vol_ratio}
        if is_contracting:
            return {"regime": MarketRegime.CONSOLIDATION, "confidence": 0.70,
                    "reason": f"low_vol_ratio={vol_ratio:.2f}", "adx": adx_val, "vol_ratio": vol_ratio}
        if adx_val < self._adx_strong - 5:
            return {"regime": MarketRegime.RANGE, "confidence": 0.70,
                    "reason": f"ADX={adx_val:.1f},low", "adx": adx_val, "vol_ratio": vol_ratio}
        return {"regime": MarketRegime.UNCERTAIN, "confidence": 0.40,
                "reason": "mixed_signals", "adx": adx_val, "vol_ratio": vol_ratio}
