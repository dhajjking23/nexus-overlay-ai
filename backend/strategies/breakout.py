"""
NEXUS OVERLAY AI - Breakout Strategy
Detects consolidation breaks with volume confirmation.
Lower confidence in RANGE regime.
"""
from __future__ import annotations
from typing import Any, Optional

from backend.strategies.base import BaseStrategy, MarketState
from backend.models import (
    DecisionState,
    MarketRegime,
    StructureType,
    now_ms,
)


class BreakoutStrategy(BaseStrategy):
    """
    Breakout strategy.
    
    Logic:
      1. Detect consolidation range (recent high/low compression)
      2. Wait for price to break above resistance (bullish) or below support (bearish)
      3. Confirm with volume spike on breakout candle
      4. Require candle close beyond level (not just wick)
      5. Penalize in RANGE regime (false breakouts common)
      6. Bonus for retest of broken level
    
    Best in: BREAKOUT, CONSOLIDATION→TRENDING transition regimes
    """

    name = "breakout"
    weight = 0.15
    min_data_quality = 40.0  # 0-100 scale
    min_candles = 20
    required_indicators = ["ATR_14", "VOLUME_SMA_20"]

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.lookback = self.config.get("lookback", 20)
        self.volume_mult = self.config.get("volume_multiplier", 1.5)
        self.atr_mult = self.config.get("atr_breakout_mult", 1.0)
        self.retest_lookback = self.config.get("retest_lookback", 5)
        self.max_range_atr = self.config.get("max_range_atr", 3.0)  # max range size in ATR

    def _detect_consolidation(self, state: MarketState) -> tuple[bool, float, float, str]:
        """
        Detect a tight consolidation range.
        Returns: (is_consolidating, range_high, range_low, reason)
        """
        if len(state.candles) < self.lookback:
            return False, 0.0, 0.0, "Insufficient candles"

        recent = state.get_candles(self.lookback)
        highs = [c.high for c in recent]
        lows = [c.low for c in recent]
        range_high = max(highs)
        range_low = min(lows)
        range_size = range_high - range_low

        # ATR normalization
        atr = state.get_indicator_value("ATR_14")
        if atr is not None and atr > 0:
            range_atr = range_size / atr
            if range_atr > self.max_range_atr:
                return False, range_high, range_low, f"Range too wide: {range_atr:.1f} ATR > {self.max_range_atr}"
        else:
            # Fallback: range as % of price
            range_pct = (range_size / state.price) * 100
            if range_pct > 2.0:  # 2% max
                return False, range_high, range_low, f"Range too wide: {range_pct:.2f}%"

        # Check for compression (range shrinking)
        if len(state.candles) >= self.lookback * 2:
            older = state.get_candles(self.lookback * 2)[:self.lookback]
            older_high = max(c.high for c in older)
            older_low = min(c.low for c in older)
            older_range = older_high - older_low
            if older_range > 0:
                compression = range_size / older_range
                if compression > 0.8:
                    return True, range_high, range_low, f"Compression ratio {compression:.2f} — not tight enough"

        return True, range_high, range_low, f"Consolidation detected: range={range_size:.2f}"

    def evaluate(self, state: MarketState) -> StrategyAssessment:
        passed, fail_reason = self._check_preconditions(state)
        if not passed:
            return self._no_signal(fail_reason)

        evidence: list[str] = []
        score = 0
        direction = DecisionState.WAIT

        # --- Step 1: Detect consolidation ---
        is_consol, range_high, range_low, consol_reason = self._detect_consolidation(state)
        evidence.append(consol_reason)

        if not is_consol:
            return self._no_signal(consol_reason)

        score += 15
        evidence.append(f"Range: {range_low:.2f} - {range_high:.2f}")

        # --- Step 2: Check for breakout ---
        atr = state.get_indicator_value("ATR_14")
        atr_threshold = atr * self.atr_mult if atr else 0

        bullish_break = state.price > range_high
        bearish_break = state.price < range_low

        # Need candle CLOSE beyond level, not just current price
        if state.candles:
            last_close = state.candles[-1].close
            bullish_break = last_close > range_high
            bearish_break = last_close < range_low

        if not bullish_break and not bearish_break:
            return self._no_signal("No breakout — price inside range")

        # --- Step 3: Volume confirmation ---
        volume_confirmed = False
        vol_sma = state.get_indicator_value("VOLUME_SMA_20")
        if vol_sma and vol_sma > 0 and state.candles:
            last_vol = state.candles[-1].volume
            if last_vol >= vol_sma * self.volume_mult:
                volume_confirmed = True
                score += 20
                evidence.append(f"Volume confirmed: {last_vol} >= {vol_sma * self.volume_mult:.0f} ({self.volume_mult}x SMA)")
            else:
                evidence.append(f"Volume weak: {last_vol} < {vol_sma * self.volume_mult:.0f}")
                score -= 10
        else:
            evidence.append("Volume SMA unavailable — skipping volume confirmation")

        # --- Step 4: Breakout direction ---
        if bullish_break:
            direction = DecisionState.BUY
            score += 25
            evidence.append(f"Bullish breakout: close {last_close:.2f} > resistance {range_high:.2f}")
        elif bearish_break:
            direction = DecisionState.SELL
            score += 25
            evidence.append(f"Bearish breakout: close {last_close:.2f} < support {range_low:.2f}")

        # --- Step 5: Retest confirmation (bonus) ---
        if len(state.candles) >= self.retest_lookback:
            recent = state.get_candles(self.retest_lookback)
            if direction == DecisionState.BUY:
                # Look for retest of broken resistance (now support)
                for c in recent:
                    if c.low <= range_high * 1.0005 and c.close > range_high:
                        score += 15
                        evidence.append(f"Retest confirmed: low {c.low:.2f} held above broken resistance")
                        break
            elif direction == DecisionState.SELL:
                # Look for retest of broken support (now resistance)
                for c in recent:
                    if c.high >= range_low * 0.9995 and c.close < range_low:
                        score += 15
                        evidence.append(f"Retest confirmed: high {c.high:.2f} held below broken support")
                        break

        # --- Step 6: Structure confirmation ---
        if state.structure is not None:
            if direction == DecisionState.BUY and state.structure.bos:
                score += 15
                evidence.append("BOS (Break of Structure) confirms breakout")
            elif direction == DecisionState.SELL and state.structure.bos:
                score += 15
                evidence.append("BOS (Break of Structure) confirms breakout")
            elif state.structure.choch:
                score += 10
                evidence.append("CHoCH (Change of Character) supports direction")

        # --- Step 7: Regime adjustment ---
        if state.regime == MarketRegime.RANGE:
            score -= 20
            evidence.append("Regime=RANGE — high false breakout risk, penalty applied")
        elif state.regime == MarketRegime.CONSOLIDATION:
            score += 5
            evidence.append("Regime=CONSOLIDATION — favorable for breakout")
        elif state.regime == MarketRegime.BREAKOUT:
            score += 15
            evidence.append("Regime=BREAKOUT — strong confirmation")

        # --- Step 8: ATR expansion check ---
        if atr is not None and state.candles:
            recent_atr = state.get_indicator_value("ATR_14")
            if recent_atr is not None:
                # Check if ATR is expanding (volatility increasing)
                if len(state.candles) >= 5:
                    # Can't easily check without history, but we can use ATR vs price
                    pass

        # --- Final score ---
        if score < 25:
            return self._no_signal(f"Score {score} below breakout threshold")

        confidence = min(1.0, score / 80.0)

        evidence.insert(0, f"[Breakout] Direction={direction.value} Score={score}")

        return self._make_assessment(
            direction=direction,
            score=score,
            confidence=confidence,
            evidence=evidence,
            timeframe=state.timeframe,
        )