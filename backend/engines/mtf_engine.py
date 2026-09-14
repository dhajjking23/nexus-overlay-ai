"""
NEXUS OVERLAY AI - Multi-Timeframe Engine
Hierarchical analysis from H4 down to M1.
"""
from __future__ import annotations
import logging
from typing import Any
from backend.models import (
    CandleData, MultiTimeframeAnalysis, TrendDirection, now_ms
)

logger = logging.getLogger(__name__)

TF_ORDER = ["H4", "H1", "M30", "M15", "M5", "M3", "M1"]


class MTFEngine:
    def __init__(self, config: dict[str, Any] | None = None, event_bus=None):
        self._config = config or {}
        self._event_bus = event_bus

    def analyze(self, mtf_candles: dict[str, list[CandleData]],
                indicators_per_tf: dict[str, dict] | None = None) -> MultiTimeframeAnalysis:
        tf_trends: dict[str, TrendDirection] = {}
        for tf in TF_ORDER:
            candles = mtf_candles.get(tf, [])
            if not candles or len(candles) < 20:
                tf_trends[tf] = TrendDirection.NEUTRAL
                continue
            tf_trends[tf] = self._detect_trend(candles)
        bullish_count = sum(1 for t in tf_trends.values() if t == TrendDirection.BULLISH)
        bearish_count = sum(1 for t in tf_trends.values() if t == TrendDirection.BEARISH)
        total = len([t for t in tf_trends.values() if t != TrendDirection.NEUTRAL])
        if total == 0:
            alignment = "neutral"
            dominant = TrendDirection.NEUTRAL
        elif bullish_count == total:
            alignment = "aligned"
            dominant = TrendDirection.BULLISH
        elif bearish_count == total:
            alignment = "aligned"
            dominant = TrendDirection.BEARISH
        elif bullish_count >= total * 0.6:
            alignment = "partially_aligned"
            dominant = TrendDirection.BULLISH
        elif bearish_count >= total * 0.6:
            alignment = "partially_aligned"
            dominant = TrendDirection.BEARISH
        else:
            alignment = "conflicting"
            dominant = TrendDirection.NEUTRAL
        conflicts = [f"{tf}:{tf_trends[tf].value}" for tf in TF_ORDER if tf_trends[tf] != dominant and tf_trends[tf] != TrendDirection.NEUTRAL]
        entry_tf = "M5"
        entry_dir = tf_trends.get(entry_tf, TrendDirection.NEUTRAL)
        return MultiTimeframeAnalysis(
            timeframe_analysis=tf_trends, alignment=alignment,
            dominant_trend=dominant, entry_timeframe=entry_tf,
            entry_direction=entry_dir, conflicts=conflicts, timestamp=now_ms()
        )

    def _detect_trend(self, candles: list[CandleData]) -> TrendDirection:
        if len(candles) < 20:
            return TrendDirection.NEUTRAL
        closes = [c.close for c in candles]
        ema20 = self._ema(closes, 20)
        ema50 = self._ema(closes, min(50, len(closes) - 1))
        recent_change = closes[-1] - closes[-20]
        avg_range = sum(c.high - c.low for c in candles[-20:]) / 20
        if ema20 > ema50 and recent_change > avg_range * 0.5:
            return TrendDirection.BULLISH
        elif ema20 < ema50 and recent_change < -avg_range * 0.5:
            return TrendDirection.BEARISH
        elif ema20 > ema50:
            return TrendDirection.BULLISH
        elif ema20 < ema50:
            return TrendDirection.BEARISH
        return TrendDirection.NEUTRAL

    @staticmethod
    def _ema(data: list[float], period: int) -> float:
        if not data or period <= 0:
            return 0.0
        k = 2.0 / (period + 1)
        ema = data[0]
        for v in data[1:]:
            ema = v * k + ema * (1 - k)
        return ema
