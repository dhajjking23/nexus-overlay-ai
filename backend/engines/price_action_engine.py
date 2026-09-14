"""
NEXUS OVERLAY AI - Price Action Engine
Detects candlestick patterns with contextual analysis.
"""
from __future__ import annotations
import logging
import math
from datetime import datetime
from typing import Any, Optional

from backend.models import (
    CandleData, PriceActionPattern, PatternType,
    MarketStructure, TrendDirection, now_ms
)

logger = logging.getLogger(__name__)


class PriceActionEngine:
    """Detects price action patterns with contextual filtering."""

    def __init__(self, config: dict[str, Any] | None = None, event_bus=None):
        self._config = config or {}
        self._event_bus = event_bus
        self._candle_range_cache: list[float] = []

    def analyze(self, candles: list[CandleData], structure: MarketStructure | None = None) -> list[PriceActionPattern]:
        if len(candles) < 5:
            return []
        self._candle_range_cache = [c.high - c.low for c in candles[-50:]]
        patterns: list[PriceActionPattern] = []
        idx = len(candles) - 1
        c = candles[idx]
        prev = candles[idx - 1]
        prev2 = candles[idx - 2] if idx >= 2 else None
        body = c.close - c.open
        body_abs = abs(body)
        candle_range = c.high - c.low
        upper_wick = c.high - max(c.open, c.close)
        lower_wick = min(c.open, c.close) - c.low
        avg_range = sum(self._candle_range_cache) / len(self._candle_range_cache) if self._candle_range_cache else 1.0

        ts = now_ms()
        tf = c.timeframe

        if self._is_engulfing_bullish(c, prev):
            patterns.append(self._make(PatternType.BULLISH_ENGULFING, tf, "BULLISH_CONFLUENCE", 0.85, ts))
        if self._is_engulfing_bearish(c, prev):
            patterns.append(self._make(PatternType.BEARISH_ENGULFING, tf, "BEARISH_CONFLUENCE", 0.85, ts))
        if self._is_pin_bar(c, avg_range):
            loc = "SUPPORT" if c.close > c.open else "RESISTANCE"
            patterns.append(self._make(PatternType.PIN_BAR, tf, loc, 0.75, ts))
        if self._is_hammer(c, avg_range):
            patterns.append(self._make(PatternType.HAMMER, tf, "SUPPORT", 0.70, ts))
        if self._is_shooting_star(c, avg_range):
            patterns.append(self._make(PatternType.SHOOTING_STAR, tf, "RESISTANCE", 0.70, ts))
        if self._is_inside_bar(c, prev):
            patterns.append(self._make(PatternType.INSIDE_BAR, tf, "COMPRESSION", 0.60, ts))
        if self._is_outside_bar(c, prev):
            patterns.append(self._make(PatternType.OUTSIDE_BAR, tf, "EXPANSION", 0.65, ts))
        if self._is_doji(c, avg_range):
            patterns.append(self._make(PatternType.DOJI, tf, "INDECISION", 0.55, ts))
        if self._is_momentum(c, avg_range):
            pt = PatternType.MOMENTUM_CANDLE
            loc = "BULLISH_MOMENTUM" if body > 0 else "BEARISH_MOMENTUM"
            patterns.append(self._make(pt, tf, loc, 0.70, ts))
        if self._is_exhaustion(c, prev, avg_range):
            patterns.append(self._make(PatternType.EXHAUSTION_CANDLE, tf, "WEAKENING", 0.65, ts))
        if self._is_rejection(c, prev, avg_range):
            patterns.append(self._make(PatternType.REJECTION_CANDLE, tf, "REJECTION", 0.70, ts))
        if self._is_breakout(c, candles, avg_range):
            patterns.append(self._make(PatternType.BREAKOUT, tf, "BREAKOUT", 0.80, ts))
        if self._is_false_breakout(c, candles, structure, avg_range):
            patterns.append(self._make(PatternType.FALSE_BREAKOUT, tf, "FALSE_BREAKOUT", 0.75, ts))
        if self._is_retest(c, candles, structure):
            patterns.append(self._make(PatternType.RETEST, tf, "RETEST", 0.72, ts))

        return patterns

    # --- pattern detectors ---
    def _is_engulfing_bullish(self, c: CandleData, p: CandleData) -> bool:
        return (p.close < p.open and c.close > c.open
                and c.open <= p.close and c.close >= p.open
                and abs(c.close - c.open) > abs(p.close - p.open))

    def _is_engulfing_bearish(self, c: CandleData, p: CandleData) -> bool:
        return (p.close > p.open and c.close < c.open
                and c.open >= p.close and c.close <= p.open
                and abs(c.close - c.open) > abs(p.close - p.open))

    def _is_pin_bar(self, c: CandleData, avg_range: float) -> bool:
        body = abs(c.close - c.open)
        total = c.high - c.low
        if total < avg_range * 0.6:
            return False
        upper_wick = c.high - max(c.open, c.close)
        lower_wick = min(c.open, c.close) - c.low
        if lower_wick > body * 2.5 and lower_wick > upper_wick * 2:
            return True
        if upper_wick > body * 2.5 and upper_wick > lower_wick * 2:
            return True
        return False

    def _is_hammer(self, c: CandleData, avg_range: float) -> bool:
        body = abs(c.close - c.open)
        lower_wick = min(c.open, c.close) - c.low
        upper_wick = c.high - max(c.open, c.close)
        total = c.high - c.low
        return (total >= avg_range * 0.5 and lower_wick >= body * 2.0
                and upper_wick < body * 0.5 and c.close > c.open)

    def _is_shooting_star(self, c: CandleData, avg_range: float) -> bool:
        body = abs(c.close - c.open)
        upper_wick = c.high - max(c.open, c.close)
        lower_wick = min(c.open, c.close) - c.low
        total = c.high - c.low
        return (total >= avg_range * 0.5 and upper_wick >= body * 2.0
                and lower_wick < body * 0.5 and c.close < c.open)

    def _is_inside_bar(self, c: CandleData, p: CandleData) -> bool:
        return c.high <= p.high and c.low >= p.low

    def _is_outside_bar(self, c: CandleData, p: CandleData) -> bool:
        return c.high > p.high and c.low < p.low

    def _is_doji(self, c: CandleData, avg_range: float) -> bool:
        body = abs(c.close - c.open)
        total = c.high - c.low
        return total > avg_range * 0.3 and body < total * 0.1

    def _is_momentum(self, c: CandleData, avg_range: float) -> bool:
        body = abs(c.close - c.open)
        return body > avg_range * 1.8 and (c.high - c.low) < body * 1.3

    def _is_exhaustion(self, c: CandleData, p: CandleData, avg_range: float) -> bool:
        prev_body = abs(p.close - p.open)
        curr_body = abs(c.close - c.open)
        return curr_body < prev_body * 0.3 and (c.high - c.low) < avg_range * 0.5

    def _is_rejection(self, c: CandleData, p: CandleData, avg_range: float) -> bool:
        total = c.high - c.low
        body = abs(c.close - c.open)
        upper = c.high - max(c.open, c.close)
        lower = min(c.open, c.close) - c.low
        if total < avg_range * 0.5:
            return False
        return upper > body * 3 or lower > body * 3

    def _is_breakout(self, c: CandleData, candles: list[CandleData], avg_range: float) -> bool:
        if len(candles) < 10:
            return False
        recent_highs = [x.high for x in candles[-10:-1]]
        recent_lows = [x.low for x in candles[-10:-1]]
        resistance = max(recent_highs)
        support = min(recent_lows)
        return c.close > resistance or c.close < support

    def _is_false_breakout(self, c: CandleData, candles: list[CandleData], structure: MarketStructure | None, avg_range: float) -> bool:
        if len(candles) < 5:
            return False
        recent_highs = [x.high for x in candles[-8:-1]]
        recent_lows = [x.low for x in candles[-8:-1]]
        resistance = max(recent_highs) if recent_highs else c.high
        support = min(recent_lows) if recent_lows else c.low
        if c.high > resistance and c.close < resistance:
            return True
        if c.low < support and c.close > support:
            return True
        return False

    def _is_retest(self, c: CandleData, candles: list[CandleData], structure: MarketStructure | None) -> bool:
        if len(candles) < 10 or structure is None:
            return False
        prev_closes = [x.close for x in candles[-10:-1]]
        if not prev_closes:
            return False
        prev_mid = sum(prev_closes) / len(prev_closes)
        return abs(c.close - prev_mid) < (c.high - c.low) * 0.3

    @staticmethod
    def _make(pattern: PatternType, tf: str, loc: str, strength: float, ts: int) -> PriceActionPattern:
        return PriceActionPattern(
            pattern=pattern, timeframe=tf, location=loc,
            strength=strength, confirmation=strength > 0.7,
            invalidation=0.0, timestamp=ts
        )
