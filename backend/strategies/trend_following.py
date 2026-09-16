"""
NEXUS OVERLAY AI - Trend Following Strategy
Identifies and trades with the prevailing trend using:
  - ADX strength (trend intensity)
  - EMA alignment (fast > mid > slow for bullish, reversed for bearish)
  - Market structure: HH/HL for uptrend, LH/LL for downtrend
  - BOS (break of structure) confirmation
"""
from __future__ import annotations
from typing import Any, Optional

from backend.strategies.base import BaseStrategy, MarketState
from backend.models import (
    DecisionState,
    StrategyAssessment,
    TrendDirection,
    StructureType,
    MarketRegime,
    now_ms,
)


class TrendFollowingStrategy(BaseStrategy):
    """
    Trend following strategy.
    
    Logic:
      1. Check ADX > threshold (default 25) to confirm trend exists
      2. Check EMA alignment: EMA(9) > EMA(21) > EMA(50) for bullish
      3. Check market structure: HH/HL pattern for bullish, LH/LL for bearish
      4. Confirm with BOS or strong directional candle
      5. Score based on number of confirming factors × ADX strength
    
    Best in: TRENDING_BULLISH, TRENDING_BEARISH regimes
    Worst in: RANGE, CONSOLIDATION regimes
    """

    name = "trend_following"
    weight = 0.25
    min_data_quality = 40.0  # 0-100 scale
    min_candles = 10
    required_indicators = ["ADX", "EMA_9", "EMA_21", "EMA_50"]

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.adx_threshold = self.config.get("adx_threshold", 25.0)
        self.adx_strong = self.config.get("adx_strong", 35.0)
        self.ema_gap_min = self.config.get("ema_gap_min", 0.0)  # min gap between EMAs in pips

    def evaluate(self, state: MarketState) -> StrategyAssessment:
        passed, fail_reason = self._check_preconditions(state)
        if not passed:
            return self._no_signal(fail_reason)

        evidence: list[str] = []
        score = 0
        direction_votes = {"BUY": 0, "SELL": 0}

        # --- ADX check ---
        adx_val = state.get_indicator_value("ADX")
        if adx_val is None:
            return self._no_signal("ADX not available")

        if adx_val < self.adx_threshold:
            return self._no_signal(f"ADX {adx_val:.1f} < {self.adx_threshold} — no trend")

        adx_score = min(30, int((adx_val / 60) * 30))  # cap at 30 points
        score += adx_score
        strength_label = "strong" if adx_val >= self.adx_strong else "moderate"
        evidence.append(f"ADX={adx_val:.1f} ({strength_label} trend)")

        # --- EMA alignment ---
        ema_9 = state.get_indicator_value("EMA_9")
        ema_21 = state.get_indicator_value("EMA_21")
        ema_50 = state.get_indicator_value("EMA_50")

        if ema_9 is None or ema_21 is None or ema_50 is None:
            return self._no_signal("EMA values incomplete")

        bullish_aligned = ema_9 > ema_21 > ema_50
        bearish_aligned = ema_9 < ema_21 < ema_50

        if bullish_aligned:
            score += 25
            direction_votes["BUY"] += 2
            evidence.append(f"EMA aligned bullish: 9({ema_9:.2f}) > 21({ema_21:.2f}) > 50({ema_50:.2f})")
        elif bearish_aligned:
            score += 25
            direction_votes["SELL"] += 2
            evidence.append(f"EMA aligned bearish: 9({ema_9:.2f}) < 21({ema_21:.2f}) < 50({ema_50:.2f})")
        else:
            # Partial alignment — only one pair aligned
            if ema_9 > ema_21:
                score += 5
                direction_votes["BUY"] += 1
                evidence.append("Partial bullish EMA: 9 > 21 but 21/50 not aligned")
            elif ema_9 < ema_21:
                score += 5
                direction_votes["SELL"] += 1
                evidence.append("Partial bearish EMA: 9 < 21 but 21/50 not aligned")
            else:
                evidence.append("EMAs compressed — no clear alignment")

        # --- Market structure ---
        if state.structure is not None:
            struct = state.structure
            if struct.trend == TrendDirection.BULLISH:
                if struct.structure in (StructureType.HH, StructureType.HL, StructureType.BOS):
                    score += 20
                    direction_votes["BUY"] += 2
                    evidence.append(f"Structure bullish: {struct.structure.value}, BOS={struct.bos}")
                else:
                    score += 5
                    direction_votes["BUY"] += 1
                    evidence.append(f"Structure mixed: {struct.structure.value}")
            elif struct.trend == TrendDirection.BEARISH:
                if struct.structure in (StructureType.LH, StructureType.LL, StructureType.BOS):
                    score += 20
                    direction_votes["SELL"] += 2
                    evidence.append(f"Structure bearish: {struct.structure.value}, BOS={struct.bos}")
                else:
                    score += 5
                    direction_votes["SELL"] += 1
                    evidence.append(f"Structure mixed: {struct.structure.value}")
            else:
                evidence.append(f"Structure neutral: {struct.structure.value}")
        else:
            evidence.append("No structure data available")

        # --- Regime bonus ---
        if state.regime == MarketRegime.TRENDING_BULLISH:
            score += 10
            direction_votes["BUY"] += 1
            evidence.append("Regime confirms bullish trend")
        elif state.regime == MarketRegime.TRENDING_BEARISH:
            score += 10
            direction_votes["SELL"] += 1
            evidence.append("Regime confirms bearish trend")
        elif state.regime in (MarketRegime.RANGE, MarketRegime.CONSOLIDATION):
            score = max(0, score - 15)
            evidence.append(f"Regime penalty: {state.regime.value} — trend following unreliable")

        # --- MTF alignment bonus ---
        if state.mtf is not None:
            if state.mtf.alignment == "aligned":
                score += 10
                evidence.append(f"MTF aligned ({state.mtf.alignment})")
            elif state.mtf.alignment == "conflicting":
                score = max(0, score - 10)
                evidence.append(f"MTF conflicting — reducing score")

        # --- Final direction ---
        if direction_votes["BUY"] > direction_votes["SELL"]:
            direction = DecisionState.BUY
        elif direction_votes["SELL"] > direction_votes["BUY"]:
            direction = DecisionState.SELL
        else:
            return self._no_signal("Conflicting direction signals")

        # --- Confidence from score ---
        confidence = min(1.0, score / 80.0)  # 80+ score = max confidence

        # Penalize if score is too low
        if score < 25:
            return self._no_signal(f"Score {score} below minimum threshold")

        evidence.insert(0, f"[TrendFollowing] Direction={direction.value} Score={score}")

        return self._make_assessment(
            direction=direction,
            score=score,
            confidence=confidence,
            evidence=evidence,
            timeframe=state.timeframe,
        )
