"""
NEXUS OVERLAY AI - Zone Engine
Detects S/R, Supply/Demand, Order Blocks, Fair Value Gaps.
"""
from __future__ import annotations
import logging
from typing import Any
from backend.models import (
    CandleData, Zone, ZoneType, now_ms
)

logger = logging.getLogger(__name__)


class ZoneEngine:
    def __init__(self, config: dict[str, Any] | None = None, event_bus=None):
        self._config = config or {}
        self._event_bus = event_bus
        zc = self._config.get("zones", {})
        self._ob_lookback = zc.get("order_block_lookback", 20)
        self._fvg_min_gap = zc.get("fvg_min_gap_pips", 1.0) * 0.01
        self._merge_tolerance = zc.get("zone_merge_tolerance_pips", 5.0) * 0.01

    def analyze(self, candles: list[CandleData], timeframe: str = "M5") -> list[Zone]:
        if len(candles) < 10:
            return []
        zones: list[Zone] = []
        ts = now_ms()
        zones.extend(self._find_sr_levels(candles, timeframe, ts))
        zones.extend(self._find_order_blocks(candles, timeframe, ts))
        zones.extend(self._find_fvg(candles, timeframe, ts))
        return self._merge_zones(zones)

    def _find_sr_levels(self, candles: list[CandleData], tf: str, ts: int) -> list[Zone]:
        zones: list[Zone] = []
        highs = [c.high for c in candles[-100:]]
        lows = [c.low for c in candles[-100:]]
        if not highs or not lows:
            return zones
        resistance = max(highs)
        support = min(lows)
        for level in [resistance, support]:
            zt = ZoneType.RESISTANCE if level == resistance else ZoneType.SUPPORT
            touches = sum(1 for c in candles[-50:] if abs(c.high - level) < 0.05 or abs(c.low - level) < 0.05)
            strength = min(1.0, touches / 5.0) * 0.8
            zones.append(Zone(zone_type=zt, upper_price=level + 0.10, lower_price=level - 0.10,
                              midpoint=level, timeframe=tf, strength=strength,
                              freshness=len(candles), touches=touches, invalidation=level + 0.5 if zt == ZoneType.SUPPORT else level - 0.5,
                              timestamp=ts))
        return zones

    def _find_order_blocks(self, candles: list[CandleData], tf: str, ts: int) -> list[Zone]:
        zones: list[Zone] = []
        lb = min(self._ob_lookback, len(candles))
        for i in range(len(candles) - lb, len(candles)):
            if i < 2:
                continue
            c = candles[i]
            nxt = candles[i + 1] if i + 1 < len(candles) else None
            if nxt is None:
                continue
            body = abs(c.close - c.open)
            next_body = abs(nxt.close - nxt.open)
            if c.close < c.open and nxt.close > nxt.open and next_body > body * 1.5:
                zones.append(Zone(
                    zone_type=ZoneType.DEMAND, upper_price=c.high, lower_price=c.low,
                    midpoint=(c.high + c.low) / 2, timeframe=tf, strength=0.75,
                    freshness=len(candles) - i, touches=1, invalidation=c.low - 0.5, timestamp=ts))
            if c.close > c.open and nxt.close < nxt.open and next_body > body * 1.5:
                zones.append(Zone(
                    zone_type=ZoneType.SUPPLY, upper_price=c.high, lower_price=c.low,
                    midpoint=(c.high + c.low) / 2, timeframe=tf, strength=0.75,
                    freshness=len(candles) - i, touches=1, invalidation=c.high + 0.5, timestamp=ts))
        return zones

    def _find_fvg(self, candles: list[CandleData], tf: str, ts: int) -> list[Zone]:
        zones: list[Zone] = []
        for i in range(2, len(candles)):
            c1, c2, c3 = candles[i - 2], candles[i - 1], candles[i]
            if c3.low > c1.high and (c3.low - c1.high) >= self._fvg_min_gap:
                gap = c3.low - c1.high
                zones.append(Zone(
                    zone_type=ZoneType.FAIR_VALUE_GAP, upper_price=c3.low,
                    lower_price=c1.high, midpoint=(c3.low + c1.high) / 2,
                    timeframe=tf, strength=min(1.0, gap / 0.5) * 0.8,
                    freshness=len(candles) - i, touches=0, invalidation=c1.high - 0.1,
                    timestamp=ts))
            if c3.high < c1.low and (c1.low - c3.high) >= self._fvg_min_gap:
                gap = c1.low - c3.high
                zones.append(Zone(
                    zone_type=ZoneType.FAIR_VALUE_GAP, upper_price=c1.low,
                    lower_price=c3.high, midpoint=(c1.low + c3.high) / 2,
                    timeframe=tf, strength=min(1.0, gap / 0.5) * 0.8,
                    freshness=len(candles) - i, touches=0, invalidation=c1.low + 0.1,
                    timestamp=ts))
        return zones

    def _merge_zones(self, zones: list[Zone]) -> list[Zone]:
        if not zones:
            return zones
        merged: list[Zone] = []
        sorted_zones = sorted(zones, key=lambda z: z.midpoint)
        for z in sorted_zones:
            if not merged:
                merged.append(z)
            else:
                last = merged[-1]
                if abs(z.midpoint - last.midpoint) < self._merge_tolerance and z.zone_type == last.zone_type:
                    merged[-1] = Zone(
                        zone_type=last.zone_type,
                        upper_price=max(last.upper_price, z.upper_price),
                        lower_price=min(last.lower_price, z.lower_price),
                        midpoint=(max(last.upper_price, z.upper_price) + min(last.lower_price, z.lower_price)) / 2,
                        timeframe=last.timeframe, strength=max(last.strength, z.strength),
                        freshness=min(last.freshness, z.freshness),
                        touches=last.touches + z.touches,
                        invalidation=last.invalidation, timestamp=last.timestamp)
                else:
                    merged.append(z)
        return merged
