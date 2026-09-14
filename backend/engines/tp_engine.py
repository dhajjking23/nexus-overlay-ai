"""
NEXUS OVERLAY AI - TP Engine
Calculates TP1/TP2/TP3 using multiple methods.
"""
from __future__ import annotations
import logging
from typing import Any
from backend.models import TPMethod, now_ms

logger = logging.getLogger(__name__)


class TPEngine:
    def __init__(self, config: dict[str, Any] | None = None, event_bus=None):
        self._config = config or {}
        self._event_bus = event_bus
        tc = self._config.get("tp", {})
        self._rr_ratios = (tc.get("tp1_rr", 1.5), tc.get("tp2_rr", 2.5), tc.get("tp3_rr", 3.5))

    def calculate(self, entry_price: float, sl_price: float, direction: str,
                  atr: float, liquidity_levels: list[float], sr_levels: list[float]) -> dict:
        if entry_price <= 0 or sl_price <= 0:
            return {"tp1": 0.0, "tp2": 0.0, "tp3": 0.0,
                    "tp1_method": TPMethod.RISK_REWARD, "tp2_method": TPMethod.RISK_REWARD,
                    "tp3_method": TPMethod.RISK_REWARD}
        is_buy = direction.upper() == "BUY"
        risk = abs(entry_price - sl_price)
        tps = []
        methods = []
        for rr in self._rr_ratios:
            tps.append(entry_price + risk * rr if is_buy else entry_price - risk * rr)
            methods.append(TPMethod.RISK_REWARD)
        if liquidity_levels:
            levels = sorted([l for l in liquidity_levels if l > entry_price] if is_buy
                            else [l for l in liquidity_levels if l < entry_price],
                            reverse=not is_buy)
            for i in range(min(3, len(levels))):
                tps[i] = levels[i]
                methods[i] = TPMethod.LIQUIDITY
        if atr > 0:
            for i, rr in enumerate(self._rr_ratios):
                if methods[i] == TPMethod.RISK_REWARD:
                    tps[i] = entry_price + atr * rr if is_buy else entry_price - atr * rr
                    methods[i] = TPMethod.ATR_PROJECTION
        return {
            "tp1": round(tps[0], 2), "tp2": round(tps[1], 2), "tp3": round(tps[2], 2),
            "tp1_method": methods[0], "tp2_method": methods[1], "tp3_method": methods[2]
        }