"""
NEXUS OVERLAY AI - Mean Reversion Strategy
Bollinger Band extremes, RSI overbought/oversold, reversion to SMA/EMA.
"""
from __future__ import annotations
from typing import Any, Optional

from backend.strategies.base import BaseStrategy, MarketState
from backend.models import (
    DecisionState,
    MarketRegime,
    TrendDirection,
    PatternType,
    now_ms,
)


class MeanReversionStrategy(BaseStrategy):
    """
    Mean reversion strategy.
    
    Logic:
      1. Identify ranging/low-volatility regime (Bollinger Band squeeze, low ADX)
      2. Detect price at Bollinger Band extremes (upper/lower band touch)
      3. Confirm with RSI overbought/oversold
      4. Look for rejection/pattern at extreme
      5. Target reversion to SMA(20) or EMA(21) — the "mean"
      6. Avoid strong trending markets (ADX > 25)
    
    Best in: RANGE, LOW_VOLATILITY, CONSOLIDATION regimes
    Worst in: TRENDING, BREAKOUT, HIGH_VOLATILITY
    """

    name = "mean_reversion"
    weight = 0.10
    min_data_quality = 30.0  # 0-100 scale
    min_candles = 20
    required_indicators = ["BB_UPPER_20", "BB_LOWER_20", "BB_MIDDLE_20", "RSI_14", "ATR_14"]

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.rsi_ob = self.config.get("rsi_overbought", 70.0)
        self.rsi_os = self.config.get("rsi_oversold", 30.0)
        self.bb_touch_threshold = self.config.get("bb_touch_threshold", 0.005)  # 0.5% of price
        self.adx_max = self.config.get("adx_max", 25.0)  # reject if ADX above this
        self.atr_contraction_pct = self.config.get("atr_contraction_pct", 0.5)  # ATR vs 20-period avg

    def evaluate(self, state: MarketState) -> StrategyAssessment:
        passed, fail_reason = self._check_preconditions(state)
        if not passed:
            return self._no_signal(fail_reason)

        evidence: list[str] = []
        score = 0
        direction = DecisionState.WAIT

        # --- Get required indicators ---
        bb_upper = state.get_indicator_value("BB_UPPER_20")
        bb_lower = state.get_indicator_value("BB_LOWER_20")
        bb_mid = state.get_indicator_value("BB_MIDDLE_20")
        rsi = state.get_indicator_value("RSI_14")
        adx = state.get_indicator_value("ADX")
        atr = state.get_indicator_value("ATR_14")

        if None in (bb_upper, bb_lower, bb_mid, rsi):
            return self._no_signal("Missing BB or RSI indicators")

        # --- Step 1: Regime check — avoid trending ---
        if adx is not None and adx > self.adx_max:
            return self._no_signal(f"ADX {adx:.1f} > {self.adx_max} — trending market, mean reversion dangerous")

        if state.regime in (MarketRegime.TRENDING_BULLISH, MarketRegime.TRENDING_BEARISH,
                            MarketRegime.BREAKOUT, MarketRegime.HIGH_VOLATILITY):
            return self._no_signal(f"Regime {state.regime.value} unfavorable for mean reversion")

        score += 10  # base for favorable regime
        evidence.append(f"Regime {state.regime.value} suitable for mean reversion")

        # --- Step 2: Bollinger Band position ---
        # Calculate position within bands: 0 = lower, 1 = upper
        bb_range = bb_upper - bb_lower
        if bb_range <= 0:
            return self._no_signal("Invalid Bollinger Bands")

        bb_position = (state.price - bb_lower) / bb_range

        # Distance to nearest band
        dist_upper = abs(state.price - bb_upper)
        dist_lower = abs(state.price - bb_lower)
        threshold = state.price * self.bb_touch_threshold

        at_upper = dist_upper <= threshold
        at_lower = dist_lower <= threshold

        if not at_upper and not at_lower:
            return self._no_signal(f"Price not at BB extreme (pos={bb_position:.2f}, threshold={threshold:.4f})")

        # --- Step 3: Direction from band touch ---
        if at_upper:
            # Price at upper band → expect reversion down
            direction = DecisionState.SELL
            score += 25
            evidence.append(f"Price at BB upper ({bb_upper:.2f}) — expect reversion down")
        elif at_lower:
            direction = DecisionState.BUY
            score += 25
            evidence.append(f"Price at BB lower ({bb_lower:.2f}) — expect reversion up")

        # --- Step 4: RSI confirmation ---
        if direction == DecisionState.SELL and rsi >= self.rsi_ob:
            score += 20
            evidence.append(f"RSI overbought ({rsi:.1f} >= {self.rsi_ob}) — confirms sell")
        elif direction == DecisionState.BUY and rsi <= self.rsi_os:
            score += 20
            evidence.append(f"RSI oversold ({rsi:.1f} <= {self.rsi_os}) — confirms buy")
        else:
            # RSI not at extreme but price is at band — partial
            if direction == DecisionState.SELL and rsi > 50:
                score += 5
                evidence.append(f"RSI elevated ({rsi:.1f}) — partial confirmation")
            elif direction == DecisionState.BUY and rsi < 50:
                score += 5
                evidence.append(f"RSI depressed ({rsi:.1f}) — partial confirmation")
            else:
                evidence.append(f"RSI neutral ({rsi:.1f}) at band touch — weak signal")
                score -= 5

        # --- Step 5: Rejection pattern at band ---
        rejection_found = False
        for pattern in state.patterns:
            if pattern.strength < 0.4:
                continue
            if direction == DecisionState.SELL and pattern.pattern in (
                PatternType.SHOOTING_STAR, PatternType.BEARISH_ENGULFING,
                PatternType.PIN_BAR, PatternType.REJECTION_CANDLE,
                PatternType.DOJI, PatternType.EXHAUSTION_CANDLE,
            ):
                score += 15
                rejection_found = True
                evidence.append(f"Rejection at upper band: {pattern.pattern.value}")
                break
            elif direction == DecisionState.BUY and pattern.pattern in (
                PatternType.HAMMER, PatternType.BULLISH_ENGULFING,
                PatternType.PIN_BAR, PatternType.REJECTION_CANDLE,
                PatternType.DOJI, PatternType.EXHAUSTION_CANDLE,
            ):
                score += 15
                rejection_found = True
                evidence.append(f"Rejection at lower band: {pattern.pattern.value}")
                break

        if not rejection_found:
            evidence.append("No rejection pattern at band — waiting for confirmation")
            # Not a hard fail, but reduced confidence

        # --- Step 6: BB squeeze / contraction (volatility compression) ---
        # Tight bands = higher probability reversion (or breakout)
        if atr is not None and state.candles:
            # Check if ATR is relatively low (contraction)
            # We'd need ATR history; for now check BB width relative to price
            bb_width_pct = (bb_range / state.price) * 100
            if bb_width_pct < 1.0:  # less than 1% of price
                score += 10
                evidence.append(f"BB squeeze: width={bb_width_pct:.2f}% — high reversion probability")
            elif bb_width_pct > 3.0:
                score -= 10
                evidence.append(f"BB expanded: width={bb_width_pct:.2f}% — lower reversion probability")

        # --- Step 7: Distance to mean (target) ---
        dist_to_mid = abs(state.price - bb_mid)
        if dist_to_mid > 0:
            # Potential move distance
            evidence.append(f"Distance to mean (BB mid): {dist_to_mid:.2f}")

        # --- Step 8: MTF check — avoid fighting higher timeframe trend ---
        if state.mtf is not None:
            if direction == DecisionState.BUY and state.mtf.dominant_trend == TrendDirection.BEARISH:
                score -= 15
                evidence.append("WARNING: Fighting MTF bearish trend")
            elif direction == DecisionState.SELL and state.mtf.dominant_trend == TrendDirection.BULLISH:
                score -= 15
                evidence.append("WARNING: Fighting MTF bullish trend")

        # --- Minimum threshold ---
        if score < 25:
            return self._no_signal(f"Score {score} below mean reversion threshold")

        confidence = min(1.0, score / 70.0)

        evidence.insert(0, f"[MeanReversion] Direction={direction.value} Score={score}")

        return self._make_assessment(
            direction=direction,
            score=score,
            confidence=confidence,
            evidence=evidence,
            timeframe=state.timeframe,
        )