"""
NEXUS OVERLAY AI - Confluence Engine
Weighted evidence matrix combining all analysis modules.
"""
from __future__ import annotations
import logging
from typing import Any
from backend.models import (
    IndicatorValue, MarketStructure, MultiTimeframeAnalysis,
    PriceActionPattern, LiquidityEvent, Zone, MarketRegime,
    ConfluenceScore, TrendDirection, now_ms
)

logger = logging.getLogger(__name__)


class ConfluenceEngine:
    def __init__(self, config: dict[str, Any] | None = None, event_bus=None):
        self._config = config or {}
        self._event_bus = event_bus
        self._weights = self._config.get("confluence", {
            "trend": 15, "structure": 15, "mtf": 15, "price_action": 10,
            "liquidity": 10, "momentum": 10, "volatility": 10,
            "zone": 5, "session": 5, "risk_reward": 5
        })

    def calculate(self, indicators: dict[str, IndicatorValue] | None = None,
                  structure: MarketStructure | None = None,
                  mtf: MultiTimeframeAnalysis | None = None,
                  price_action: list[PriceActionPattern] | None = None,
                  liquidity: list[LiquidityEvent] | None = None,
                  regime: dict | None = None,
                  risk_reward: float = 1.0,
                  session_active: bool = True,
                  volatility_atr: float = 0.0,
                  atr_avg: float = 0.0) -> ConfluenceScore:
        indicators = indicators or {}
        price_action = price_action or []
        liquidity = liquidity or []
        scores: dict[str, float] = {}
        evidence: list[str] = []
        total_w = sum(self._weights.values()) or 100

        # Trend
        trend_score = self._score_trend(indicators, evidence)
        scores["trend"] = trend_score * self._weights.get("trend", 15) / total_w

        # Structure
        struct_score = self._score_structure(structure, evidence)
        scores["structure"] = struct_score * self._weights.get("structure", 15) / total_w

        # MTF
        mtf_score = self._score_mtf(mtf, evidence)
        scores["mtf"] = mtf_score * self._weights.get("mtf", 15) / total_w

        # Price Action
        pa_score = self._score_price_action(price_action, evidence)
        scores["price_action"] = pa_score * self._weights.get("price_action", 10) / total_w

        # Liquidity
        liq_score = self._score_liquidity(liquidity, evidence)
        scores["liquidity"] = liq_score * self._weights.get("liquidity", 10) / total_w

        # Momentum
        mom_score = self._score_momentum(indicators, evidence)
        scores["momentum"] = mom_score * self._weights.get("momentum", 10) / total_w

        # Volatility
        vol_score = self._score_volatility(volatility_atr, atr_avg, evidence)
        scores["volatility"] = vol_score * self._weights.get("volatility", 10) / total_w

        # Session
        sess_score = 80 if session_active else 30
        if session_active:
            evidence.append("Active trading session")
        scores["session"] = sess_score * self._weights.get("session", 5) / total_w

        # RR
        rr_score = min(100, risk_reward * 40)
        scores["risk_reward"] = rr_score * self._weights.get("risk_reward", 5) / total_w

        total_score = sum(scores.values())
        return ConfluenceScore(weights=self._weights.copy(), scores=scores,
                               total_score=round(total_score, 2),
                               contributing_factors=evidence, timestamp=now_ms())

    def _score_trend(self, ind: dict, ev: list) -> float:
        score = 50.0
        ema20 = ind.get("ema_20")
        ema50 = ind.get("ema_50")
        if ema20 and ema50:
            if ema20.value > ema50.value:
                score += 30
                ev.append("EMA20 > EMA50 (bullish)")
            elif ema20.value < ema50.value:
                score -= 30
                ev.append("EMA20 < EMA50 (bearish)")
        return max(0, min(100, score))

    def _score_structure(self, struct: MarketStructure | None, ev: list) -> float:
        if struct is None:
            return 50
        if struct.trend == TrendDirection.BULLISH:
            ev.append(f"Bullish structure ({struct.structure.value})")
            return 80
        elif struct.trend == TrendDirection.BEARISH:
            ev.append(f"Bearish structure ({struct.structure.value})")
            return 20
        return 50

    def _score_mtf(self, mtf: MultiTimeframeAnalysis | None, ev: list) -> float:
        if mtf is None:
            return 50
        if mtf.alignment == "aligned":
            ev.append(f"MTF aligned {mtf.dominant_trend.value}")
            return 90
        elif mtf.alignment == "partially_aligned":
            ev.append(f"MTF partially aligned ({mtf.dominant_trend.value})")
            return 65
        elif mtf.alignment == "conflicting":
            ev.append("MTF conflicting")
            return 20
        return 50

    def _score_price_action(self, pa: list, ev: list) -> float:
        if not pa:
            return 50
        bullish = sum(1 for p in pa if "BULL" in p.location.upper() or "SUPPORT" in p.location.upper())
        bearish = sum(1 for p in pa if "BEAR" in p.location.upper() or "RESISTANCE" in p.location.upper())
        ev.append(f"PA: {len(pa)} patterns ({bullish}B/{bearish}S)")
        return 50 + (bullish - bearish) * 15

    def _score_liquidity(self, liq: list, ev: list) -> float:
        if not liq:
            return 50
        sweeps = sum(1 for e in liq if "SWEEP" in e.event.value)
        ev.append(f"Liquidity: {len(liq)} events ({sweeps} sweeps)")
        return 70 if sweeps > 0 else 50

    def _score_momentum(self, ind: dict, ev: list) -> float:
        rsi = ind.get("rsi")
        adx = ind.get("adx")
        score = 50
        if rsi:
            if rsi.value > 70:
                score += 20
                ev.append(f"RSI overbought ({rsi.value:.1f})")
            elif rsi.value < 30:
                score -= 20
                ev.append(f"RSI oversold ({rsi.value:.1f})")
        if adx and adx.value > 25:
            score += 15
            ev.append(f"ADX strong ({adx.value:.1f})")
        return max(0, min(100, score))

    def _score_volatility(self, current: float, avg: float, ev: list) -> float:
        if avg <= 0:
            return 50
        ratio = current / avg
        if ratio > 2.0:
            ev.append(f"High volatility (ATR ratio {ratio:.2f})")
            return 30
        elif ratio > 1.3:
            return 60
        elif ratio < 0.5:
            ev.append(f"Low volatility (ATR ratio {ratio:.2f})")
            return 40
        return 70
