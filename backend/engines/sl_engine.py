"""
NEXUS OVERLAY AI - SL Engine
Calculates stop loss using ATR/structure/swing/zone methods.
"""
from __future__ import annotations
import logging
from typing import Any
from backend.models import (
    CandleData, SLTPCalculation, SLMethod, MarketStructure, TrendDirection,
    Zone, now_ms
)

logger = logging.getLogger(__name__)


class SLEngine:
    def __init__(self, config: dict[str, Any] | None = None, event_bus=None):
        self._config = config or {}
        self._event_bus = event_bus
        sc = self._config.get("sl", {})
        self._atr_mult = sc.get("atr_multiplier", 1.5)
        self._min_sl = sc.get("min_sl_pips", 5.0) * 0.01
        self._max_sl = sc.get("max_sl_pips", 100.0) * 0.01
        self._buffer = sc.get("buffer_pips", 1.0) * 0.01

    def calculate(self, candles: list[CandleData], entry_price: float,
                  direction: str, atr: float, structure: MarketStructure | None,
                  swing_highs: list[float], swing_lows: list[float],
                  zones: list[Zone]) -> SLTPCalculation:
        if not candles or entry_price <= 0:
            return SLTPCalculation(
                sl_method=SLMethod.ATR, sl_price=0.0, sl_reason="no_data",
                tp1_method=None, tp1_price=0.0, tp2_method=None, tp2_price=0.0,
                tp3_method=None, tp3_price=0.0, invalidation_reason="", timestamp=now_ms())
        is_buy = direction.upper() == "BUY"
        sl_price = 0.0
        method = SLMethod.ATR
        reason = ""

        if structure and structure.swing_lows and is_buy and structure.trend == TrendDirection.BULLISH:
            sl_price = max(structure.swing_lows[-1] - self._buffer, entry_price - self._max_sl)
            method = SLMethod.STRUCTURE
            reason = f"structure_swing_low_{sl_price:.2f}"
        elif structure and structure.swing_highs and not is_buy and structure.trend == TrendDirection.BEARISH:
            sl_price = min(structure.swing_highs[-1] + self._buffer, entry_price + self._max_sl)
            method = SLMethod.STRUCTURE
            reason = f"structure_swing_high_{sl_price:.2f}"
        elif zones:
            for z in zones:
                if is_buy and z.zone_type.value in ("SUPPORT", "DEMAND"):
                    sl_price = z.lower_price - self._buffer
                    method = SLMethod.ZONE
                    reason = f"zone_{z.zone_type.value}"
                    break
                if not is_buy and z.zone_type.value in ("RESISTANCE", "SUPPLY"):
                    sl_price = z.upper_price + self._buffer
                    method = SLMethod.ZONE
                    reason = f"zone_{z.zone_type.value}"
                    break

        if sl_price == 0.0:
            atr_dist = atr * self._atr_mult if atr > 0 else self._min_sl
            sl_price = entry_price - atr_dist if is_buy else entry_price + atr_dist
            method = SLMethod.ATR
            reason = f"atr_{self._atr_mult}x"

        sl_price = max(sl_price, entry_price - self._max_sl) if is_buy else min(sl_price, entry_price + self._max_sl)
        sl_price = min(sl_price, entry_price - self._min_sl) if is_buy else max(sl_price, entry_price + self._min_sl)

        invalidation = f"Close {'above' if not is_buy else 'below'} {sl_price:.2f}"
        return SLTPCalculation(
            sl_method=method, sl_price=sl_price, sl_reason=reason,
            tp1_method=None, tp1_price=0.0, tp2_method=None, tp2_price=0.0,
            tp3_method=None, tp3_price=0.0, invalidation_reason=invalidation, timestamp=now_ms()
        )