"""
NEXUS OVERLAY AI - Liquidity Engine
Detects equal highs/lows, sweeps, stop runs, false breakouts.
"""
from __future__ import annotations
import logging
from typing import Any
from backend.models import (
    CandleData, LiquidityEvent, LiquidityEventType,
    MarketStructure, TrendDirection, now_ms
)

logger = logging.getLogger(__name__)


class LiquidityEngine:
    def __init__(self, config: dict[str, Any] | None = None, event_bus=None):
        self._config = config or {}
        self._event_bus = event_bus
        lc = self._config.get("liquidity", {})
        self._tolerance = lc.get("equal_level_tolerance_pips", 2.0) * 0.01
        self._sweep_confirm_pips = lc.get("sweep_confirmation_pips", 1.0) * 0.01
        self._sweep_max_age = lc.get("sweep_max_age_candles", 20)

    def analyze(self, candles: list[CandleData], structure: MarketStructure | None = None,
                timeframe: str = "M5") -> list[LiquidityEvent]:
        if len(candles) < 10:
            return []
        events: list[LiquidityEvent] = []
        ts = now_ms()
        events.extend(self._find_equal_levels(candles, timeframe, ts))
        events.extend(self._find_day_levels(candles, timeframe, ts))
        events.extend(self._detect_sweeps(candles, timeframe, ts))
        return events

    def _find_equal_levels(self, candles: list[CandleData], tf: str, ts: int) -> list[LiquidityEvent]:
        events: list[LiquidityEvent] = []
        highs = [c.high for c in candles[-50:]]
        lows = [c.low for c in candles[-50:]]
        for i in range(len(highs)):
            for j in range(i + 1, len(highs)):
                if abs(highs[i] - highs[j]) < self._tolerance:
                    events.append(LiquidityEvent(
                        event=LiquidityEventType.EQUAL_HIGHS, direction="BUY_SIDE",
                        price=max(highs[i], highs[j]), timeframe=tf,
                        strength=0.7, timestamp=ts))
                    break
        for i in range(len(lows)):
            for j in range(i + 1, len(lows)):
                if abs(lows[i] - lows[j]) < self._tolerance:
                    events.append(LiquidityEvent(
                        event=LiquidityEventType.EQUAL_LOWS, direction="SELL_SIDE",
                        price=min(lows[i], lows[j]), timeframe=tf,
                        strength=0.7, timestamp=ts))
                    break
        return events

    def _find_day_levels(self, candles: list[CandleData], tf: str, ts: int) -> list[LiquidityEvent]:
        events: list[LiquidityEvent] = []
        if len(candles) < 20:
            return events
        recent = candles[-100:]
        day_high = max(c.high for c in recent[-48:])
        day_low = min(c.low for c in recent[-48:])
        current = candles[-1].close
        events.append(LiquidityEvent(
            event=LiquidityEventType.PREV_DAY_HIGH, direction="BUY_SIDE",
            price=day_high, timeframe=tf, strength=0.6, timestamp=ts))
        events.append(LiquidityEvent(
            event=LiquidityEventType.PREV_DAY_LOW, direction="SELL_SIDE",
            price=day_low, timeframe=tf, strength=0.6, timestamp=ts))
        return events

    def _detect_sweeps(self, candles: list[CandleData], tf: str, ts: int) -> list[LiquidityEvent]:
        events: list[LiquidityEvent] = []
        if len(candles) < 5:
            return events
        recent_highs = [c.high for c in candles[-30:-2]]
        recent_lows = [c.low for c in candles[-30:-2]]
        if not recent_highs or not recent_lows:
            return events
        resistance = max(recent_highs)
        support = min(recent_lows)
        c = candles[-1]
        prev = candles[-2]
        if c.high > resistance and c.close < resistance:
            events.append(LiquidityEvent(
                event=LiquidityEventType.LIQUIDITY_SWEEP, direction="BUY_SIDE",
                price=c.high, timeframe=tf, strength=0.8, timestamp=ts))
        if c.low < support and c.close > support:
            events.append(LiquidityEvent(
                event=LiquidityEventType.LIQUIDITY_SWEEP, direction="SELL_SIDE",
                price=c.low, timeframe=tf, strength=0.8, timestamp=ts))
        if prev.high > resistance and c.close < prev.close and c.close < prev.close:
            events.append(LiquidityEvent(
                event=LiquidityEventType.STOP_RUN, direction="BUY_SIDE",
                price=prev.high, timeframe=tf, strength=0.75, timestamp=ts))
        return events
