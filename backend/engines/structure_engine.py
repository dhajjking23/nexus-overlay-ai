"""
NEXUS OVERLAY AI - Market Structure Engine
Detects HH/HL/LH/LL, BOS, CHOCH, swing points, trend/range.
"""
from __future__ import annotations
import logging
from typing import Any, Optional
from backend.models import (
    CandleData, MarketStructure, TrendDirection, StructureType, now_ms
)

logger = logging.getLogger(__name__)


class StructureEngine:
    def __init__(self, config: dict[str, Any] | None = None, event_bus=None):
        self._config = config or {}
        self._event_bus = event_bus
        sc = self._config.get("structure", {})
        self._swing_lookback = sc.get("swing_lookback", 5)
        self._min_swing_distance = sc.get("min_swing_distance_pips", 10) * 0.01

    def analyze(self, candles: list[CandleData]) -> MarketStructure:
        if len(candles) < self._swing_lookback * 2 + 1:
            return MarketStructure(trend=TrendDirection.NEUTRAL, structure=StructureType.RANGE,
                                   bos=False, choch=False, timeframe=candles[-1].timeframe if candles else "M5")
        swing_highs, swing_lows = self._find_swings(candles)
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return MarketStructure(trend=TrendDirection.NEUTRAL, structure=StructureType.RANGE,
                                   bos=False, choch=False, swing_highs=swing_highs, swing_lows=swing_lows,
                                   timeframe=candles[-1].timeframe)
        points = self._build_swing_points(swing_highs, swing_lows, candles)
        hhs, lhs, hls, lls = 0, 0, 0, 0
        for i in range(1, len(points)):
            p = points[i]
            prev = points[i - 1]
            if p["type"] == "high":
                if p["price"] > prev["price"]:
                    hhs += 1
                else:
                    lhs += 1
            else:
                if p["price"] > prev["price"]:
                    hls += 1
                else:
                    lls += 1
        bos = False
        choch = False
        if hhs > 0 and hls > 0 and lhs == 0 and lls == 0:
            structure_type = StructureType.HH
            trend = TrendDirection.BULLISH
        elif lhs > 0 and lls > 0 and hhs == 0 and hls == 0:
            structure_type = StructureType.LL
            trend = TrendDirection.BEARISH
        elif hhs > 0 and hls > 0:
            structure_type = StructureType.HL
            trend = TrendDirection.BULLISH
            bos = True
        elif lhs > 0 and lls > 0:
            structure_type = StructureType.LH
            trend = TrendDirection.BEARISH
            bos = True
        else:
            structure_type = StructureType.RANGE
            trend = TrendDirection.NEUTRAL
        if lhs > 0 and hhs > 0 and lls > hls:
            choch = True
            trend = TrendDirection.BEARISH
        elif hls > 0 and lls > 0 and hhs > lhs:
            if hhs == 0:
                choch = True
                trend = TrendDirection.BULLISH
        return MarketStructure(
            trend=trend, structure=structure_type, bos=bos, choch=choch,
            swing_highs=swing_highs, swing_lows=swing_lows,
            timeframe=candles[-1].timeframe, timestamp=now_ms()
        )

    def _find_swings(self, candles: list[CandleData]) -> tuple[list[float], list[float]]:
        lb = self._swing_lookback
        highs: list[float] = []
        lows: list[float] = []
        for i in range(lb, len(candles) - lb):
            if all(candles[i].high >= candles[j].high for j in range(i - lb, i + lb + 1)):
                highs.append(candles[i].high)
            if all(candles[i].low <= candles[j].low for j in range(i - lb, i + lb + 1)):
                lows.append(candles[i].low)
        return highs, lows

    def _build_swing_points(self, highs: list[float], lows: list[float], candles: list[CandleData]) -> list[dict]:
        points = []
        for h in highs:
            points.append({"type": "high", "price": h})
        for l in lows:
            points.append({"type": "low", "price": l})
        points.sort(key=lambda p: p["price"], reverse=True)
        merged: list[dict] = []
        for p in points:
            if not merged:
                merged.append(p)
            else:
                last = merged[-1]
                if abs(p["price"] - last["price"]) < self._min_swing_distance:
                    continue
                merged.append(p)
        return merged
