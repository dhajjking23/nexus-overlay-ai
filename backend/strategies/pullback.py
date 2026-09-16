"""
NEXUS OVERLAY AI - Pullback Strategy
Detects pullbacks within a trending market and identifies entry opportunities.
Uses EMA(50) as dynamic support/resistance with structure confirmation.
"""
from __future__ import annotations
from typing import Any, Optional

from backend.strategies.base import BaseStrategy, MarketState
from backend.models import (
    DecisionState,
    TrendDirection,
    StructureType,
    MarketRegime,
    PatternType,
    PriceActionPattern,
    now_ms,
)


class PullbackStrategy(BaseStrategy):
    """
    Pullback-to-trend strategy.
    
    Logic:
      1. Confirm a strong trend exists (ADX > 20, EMA alignment)
      2. Detect pullback: price moves against trend toward EMA(50)
      3. Confirm pullback proximity to EMA(50) (within tolerance)
      4. Require structure confirmation: HH/HL after pullback (buy side),
         or LH/LL after pullback (sell side)
      5. Optional: reversal pattern at the EMA(50) for extra confidence
    
    Best in: TRENDING_BULLISH/BEARISH with active pullback
    """

    name = "pullback"
    weight = 0.20
    min_data_quality = 40.0  # 0-100 scale
    min_candles = 15
    required_indicators = ["EMA_21", "EMA_50"]

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.pullback_tolerance_pct = self.config.get("pullback_tolerance_pct", 0.15)  # % of price
        self.min_trend_adx = self.config.get("min_trend_adx", 20.0)
        self.rsi_ob = self.config.get("rsi_overbought", 70.0)
        self.rsi_os = self.config.get("rsi_oversold", 30.0)

    def _is_pullback_toward_ema50(
        self, state: MarketState, trend: TrendDirection
    ) -> tuple[bool, str]:
        """
        Check if price is pulling back toward EMA(50).
        Bullish trend: price dropped from recent high toward EMA(50) from above.
        Bearish trend: price rallied from recent low toward EMA(50) from below.
        """
        ema_50 = state.get_indicator_value("EMA_50")
        if ema_50 is None or ema_50 <= 0:
            return False, "EMA(50) unavailable"

        tolerance = state.price * (self.pullback_tolerance_pct / 100.0)
        distance = abs(state.price - ema_50)

        if trend == TrendDirection.BULLISH:
            # Price should be near or slightly below EMA(50) during pullback
            # but not too far below (that would be a reversal)
            if distance <= tolerance:
                return True, f"Bullish pullback: price {state.price:.2f} near EMA50({ema_50:.2f}), dist={distance:.2f}"
            # Also accept if price just bounced off EMA(50)
            if len(state.candles) >= 3:
                recent_lows = [c.low for c in state.get_candles(3)]
                nearest_low = min(recent_lows)
                if abs(nearest_low - ema_50) <= tolerance and state.price > ema_50:
                    return True, f"Bullish bounce: recent low {nearest_low:.2f} touched EMA50({ema_50:.2f})"
        elif trend == TrendDirection.BEARISH:
            if distance <= tolerance:
                return True, f"Bearish pullback: price {state.price:.2f} near EMA50({ema_50:.2f}), dist={distance:.2f}"
            if len(state.candles) >= 3:
                recent_highs = [c.high for c in state.get_candles(3)]
                nearest_high = max(recent_highs)
                if abs(nearest_high - ema_50) <= tolerance and state.price < ema_50:
                    return True, f"Bearish rejection: recent high {nearest_high:.2f} touched EMA50({ema_50:.2f})"

        return False, f"No pullback detected: price={state.price:.2f}, EMA50={ema_50:.2f}, dist={distance:.2f}"

    def evaluate(self, state: MarketState) -> StrategyAssessment:
        passed, fail_reason = self._check_preconditions(state)
        if not passed:
            return self._no_signal(fail_reason)

        evidence: list[str] = []
        score = 0

        # --- Step 1: Confirm trend exists ---
        adx_val = state.get_indicator_value("ADX")
        if adx_val is not None and adx_val < self.min_trend_adx:
            return self._no_signal(f"ADX {adx_val:.1f} too low for trend pullback")

        # Determine dominant trend direction
        trend_direction: TrendDirection = TrendDirection.NEUTRAL
        if state.structure is not None:
            trend_direction = state.structure.trend
        elif state.mtf is not None:
            trend_direction = state.mtf.dominant_trend

        if trend_direction == TrendDirection.NEUTRAL:
            return self._no_signal("No dominant trend for pullback entry")

        if adx_val is not None:
            score += min(15, int(adx_val / 4))
            evidence.append(f"ADX={adx_val:.1f} confirms trend exists")

        # --- Step 2: Detect pullback ---
        is_pullback, pb_reason = self._is_pullback_toward_ema50(state, trend_direction)
        evidence.append(pb_reason)

        if not is_pullback:
            return self._no_signal("Not in a pullback phase")

        score += 25
        evidence.append("Pullback phase detected")

        # --- Step 3: EMA(21) relationship to EMA(50) ---
        ema_21 = state.get_indicator_value("EMA_21")
        ema_50 = state.get_indicator_value("EMA_50")
        if ema_21 is not None and ema_50 is not None:
            if trend_direction == TrendDirection.BULLISH and ema_21 > ema_50:
                score += 10
                evidence.append("EMA(21) > EMA(50) — trend intact during pullback")
            elif trend_direction == TrendDirection.BEARISH and ema_21 < ema_50:
                score += 10
                evidence.append("EMA(21) < EMA(50) — trend intact during pullback")
            else:
                # EMAs crossing against trend — potential trend break
                score -= 10
                evidence.append("EMA cross against trend — caution")

        # --- Step 4: Structure confirmation ---
        if state.structure is not None:
            if trend_direction == TrendDirection.BULLISH:
                if state.structure.structure in (StructureType.HL, StructureType.HH):
                    score += 20
                    evidence.append(f"Structure confirms bullish continuation: {state.structure.structure.value}")
                elif state.structure.structure in (StructureType.LL, StructureType.LH):
                    score -= 15
                    evidence.append(f"Structure contradicts bullish: {state.structure.structure.value}")
            elif trend_direction == TrendDirection.BEARISH:
                if state.structure.structure in (StructureType.LH, StructureType.LL):
                    score += 20
                    evidence.append(f"Structure confirms bearish continuation: {state.structure.structure.value}")
                elif state.structure.structure in (StructureType.HH, StructureType.HL):
                    score -= 15
                    evidence.append(f"Structure contradicts bearish: {state.structure.structure.value}")

        # --- Step 5: Reversal pattern at EMA(50) bonus ---
        for pattern in state.patterns:
            if trend_direction == TrendDirection.BULLISH and pattern.pattern in (
                PatternType.HAMMER, PatternType.BULLISH_ENGULFING, PatternType.PIN_BAR,
                PatternType.REJECTION_CANDLE,
            ):
                score += 15
                evidence.append(f"Reversal pattern at EMA50: {pattern.pattern.value} (strength={pattern.strength:.2f})")
                break
            elif trend_direction == TrendDirection.BEARISH and pattern.pattern in (
                PatternType.SHOOTING_STAR, PatternType.BEARISH_ENGULFING, PatternType.PIN_BAR,
                PatternType.REJECTION_CANDLE,
            ):
                score += 15
                evidence.append(f"Reversal pattern at EMA50: {pattern.pattern.value} (strength={pattern.strength:.2f})")
                break

        # --- Step 6: RSI divergence bonus ---
        rsi_val = state.get_indicator_value("RSI_14")
        if rsi_val is not None:
            if trend_direction == TrendDirection.BULLISH and rsi_val < self.rsi_os:
                score += 10
                evidence.append(f"RSI oversold ({rsi_val:.1f}) — strong bullish pullback")
            elif trend_direction == TrendDirection.BEARISH and rsi_val > self.rsi_ob:
                score += 10
                evidence.append(f"RSI overbought ({rsi_val:.1f}) — strong bearish pullback")
            elif trend_direction == TrendDirection.BULLISH and 40 <= rsi_val <= 55:
                score += 5
                evidence.append(f"RSI in pullback zone ({rsi_val:.1f})")
            elif trend_direction == TrendDirection.BEARISH and 45 <= rsi_val <= 60:
                score += 5
                evidence.append(f"RSI in pullback zone ({rsi_val:.1f})")

        # --- Regime check ---
        if state.regime not in (MarketRegime.TRENDING_BULLISH, MarketRegime.TRENDING_BEARISH):
            score = max(0, score - 10)
            evidence.append(f"Regime {state.regime.value} is suboptimal for pullback entries")

        # --- Determine direction ---
        if trend_direction == TrendDirection.BULLISH:
            direction = DecisionState.BUY
        else:
            direction = DecisionState.SELL

        # --- Minimum threshold ---
        if score < 30:
            return self._no_signal(f"Score {score} below pullback threshold")

        confidence = min(1.0, score / 75.0)

        evidence.insert(0, f"[Pullback] Direction={direction.value} Score={score}")

        return self._make_assessment(
            direction=direction,
            score=score,
            confidence=confidence,
            evidence=evidence,
            timeframe=state.timeframe,
        )
