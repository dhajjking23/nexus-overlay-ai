"""
NEXUS OVERLAY AI - Scalping Strategy
M1/M3 focused, tight ranges, quick entries. Only active during volatile sessions.
"""
from __future__ import annotations
from typing import Any, Optional

from backend.strategies.base import BaseStrategy, MarketState
from backend.models import (
    DecisionState,
    SessionType,
    MarketRegime,
    PatternType,
    TrendDirection,
    now_ms,
)


class ScalpingStrategy(BaseStrategy):
    """
    Scalping strategy for quick entries on M1/M3 timeframes.
    
    Logic:
      1. Only active during volatile sessions (London, New York, Overlap)
      2. Detect tight range / compression on M1
      3. Look for micro-structure break (recent 3-5 candle range)
      4. Require volume spike on breakout candle
      5. Quick in-and-out: tight SL (1-2 ATR), target 1:1.5-2 RR
      6. Must have high spread awareness — avoid scalping during wide spreads
    
    Best in: Active sessions, moderate volatility
    """

    name = "scalping"
    weight = 0.10
    min_data_quality = 50.0  # 0-100 scale, higher quality needed for scalping
    min_candles = 10
    required_indicators = ["ATR_14"]

    # Scalping only during these sessions
    ACTIVE_SESSIONS = {SessionType.LONDON, SessionType.NEW_YORK, SessionType.OVERLAP}

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.max_spread_pips = self.config.get("max_spread_pips", 30.0)
        self.candle_range = self.config.get("candle_range", 5)  # number of recent candles for range
        self.min_body_ratio = self.config.get("min_body_ratio", 0.6)  # body/total ratio for momentum candle
        self.target_rr = self.config.get("target_rr", 1.5)
        self.sl_atr_mult = self.config.get("sl_atr_multiplier", 1.5)
        self.min_adx = self.config.get("min_adx", 15.0)

    def evaluate(self, state: MarketState) -> StrategyAssessment:
        passed, fail_reason = self._check_preconditions(state)
        if not passed:
            return self._no_signal(fail_reason)

        evidence: list[str] = []
        score = 0
        direction = DecisionState.WAIT

        # --- Session check ---
        if state.session not in self.ACTIVE_SESSIONS:
            return self._no_signal(f"Session {state.session.value} not active for scalping")

        score += 10
        evidence.append(f"Active session: {state.session.value}")

        # --- Spread check ---
        # For XAUUSD: 1 pip = 0.01 price
        spread_pips = state.spread / 0.01
        if spread_pips > self.max_spread_pips:
            return self._no_signal(f"Spread too wide for scalping: {spread_pips:.1f} pips")

        if spread_pips < 5:
            score += 5
            evidence.append(f"Tight spread: {spread_pips:.1f} pips — good for scalping")
        else:
            evidence.append(f"Spread: {spread_pips:.1f} pips")

        # --- ATR check — need some volatility ---
        atr = state.get_indicator_value("ATR_14")
        if atr is not None and atr > 0:
            # Check minimum volatility
            atr_pct = (atr / state.price) * 100
            if atr_pct < 0.05:
                return self._no_signal(f"ATR too low for scalping: {atr_pct:.3f}%")
            score += 10
            evidence.append(f"ATR={atr:.2f} ({atr_pct:.2f}%) — adequate volatility")
        else:
            return self._no_signal("ATR unavailable")

        # --- Detect micro-range (consolidation on current candles) ---
        if len(state.candles) < self.candle_range:
            return self._no_signal(f"Insufficient candles: {state.candle_count}")

        recent = state.get_candles(self.candle_range)
        range_high = max(c.high for c in recent)
        range_low = min(c.low for c in recent)
        micro_range = range_high - range_low
        range_atr = micro_range / atr if atr > 0 else 0

        if range_atr > 2.0:
            return self._no_signal(f"Micro-range too wide: {range_atr:.1f} ATR")
        elif range_atr < 0.5:
            return self._no_signal(f"Micro-range too tight: {range_atr:.1f} ATR — no breakout")

        score += 10
        evidence.append(f"Micro-range: {micro_range:.2f} ({range_atr:.1f} ATR)")

        # --- Detect momentum candle (breakout from micro-range) ---
        if not state.candles:
            return self._no_signal("No candle data")

        last_candle = state.candles[-1]
        candle_range = last_candle.high - last_candle.low
        if candle_range <= 0:
            return self._no_signal("Zero-range candle")

        body = abs(last_candle.close - last_candle.open)
        body_ratio = body / candle_range if candle_range > 0 else 0

        if body_ratio < self.min_body_ratio:
            return self._no_signal(f"Candle body ratio too low: {body_ratio:.2f} < {self.min_body_ratio}")

        # Determine candle direction
        bullish_candle = last_candle.close > last_candle.open
        bearish_candle = last_candle.close < last_candle.open

        if not bullish_candle and not bearish_candle:
            return self._no_signal("Doji candle — no direction")

        # --- Check if candle breaks micro-range ---
        if bullish_candle and last_candle.close > range_high:
            direction = DecisionState.BUY
            score += 25
            evidence.append(f"Bullish breakout candle: close {last_candle.close:.2f} > range high {range_high:.2f}")
        elif bearish_candle and last_candle.close < range_low:
            direction = DecisionState.SELL
            score += 25
            evidence.append(f"Bearish breakout candle: close {last_candle.close:.2f} < range low {range_low:.2f}")
        else:
            return self._no_signal("Candle did not break micro-range")

        # --- Volume confirmation ---
        if state.candles:
            vol_sma = state.get_indicator_value("VOLUME_SMA_20")
            if vol_sma and vol_sma > 0:
                vol_ratio = last_candle.volume / vol_sma
                if vol_ratio >= 1.3:
                    score += 15
                    evidence.append(f"Volume spike: {last_candle.volume} ({vol_ratio:.1f}x SMA)")
                elif vol_ratio >= 1.0:
                    score += 5
                    evidence.append(f"Average volume: {vol_ratio:.1f}x SMA")
                else:
                    evidence.append(f"Low volume: {vol_ratio:.1f}x SMA")
                    score -= 5

        # --- ADX check ---
        adx = state.get_indicator_value("ADX")
        if adx is not None:
            if adx < self.min_adx:
                # Scalping can work in low ADX, just reduce score
                score -= 5
                evidence.append(f"Low ADX ({adx:.1f}) — weaker directional bias")
            else:
                score += 5
                evidence.append(f"ADX {adx:.1f} — directional bias present")

        # --- Price action pattern bonus ---
        for pattern in state.patterns:
            if pattern.strength >= 0.6:
                if direction == DecisionState.BUY and pattern.pattern in (
                    PatternType.MOMENTUM_CANDLE, PatternType.EXPANSION,
                    PatternType.BULLISH_ENGULFING,
                ):
                    score += 10
                    evidence.append(f"Bullish pattern: {pattern.pattern.value}")
                    break
                elif direction == DecisionState.SELL and pattern.pattern in (
                    PatternType.MOMENTUM_CANDLE, PatternType.EXPANSION,
                    PatternType.BEARISH_ENGULFING,
                ):
                    score += 10
                    evidence.append(f"Bearish pattern: {pattern.pattern.value}")
                    break

        # --- EMA direction alignment ---
        ema_9 = state.get_indicator_value("EMA_9")
        ema_21 = state.get_indicator_value("EMA_21")
        if ema_9 is not None and ema_21 is not None:
            if direction == DecisionState.BUY and ema_9 > ema_21:
                score += 5
                evidence.append("EMA(9) > EMA(21) — aligned with direction")
            elif direction == DecisionState.SELL and ema_9 < ema_21:
                score += 5
                evidence.append("EMA(9) < EMA(21) — aligned with direction")
            else:
                evidence.append("EMA not aligned — counter-trend scalping risk")

        # --- Minimum threshold ---
        if score < 30:
            return self._no_signal(f"Score {score} below scalping threshold")

        confidence = min(1.0, score / 75.0)

        evidence.insert(0, f"[Scalping] Direction={direction.value} Score={score}")

        return self._make_assessment(
            direction=direction,
            score=score,
            confidence=confidence,
            evidence=evidence,
            timeframe=state.timeframe,
        )