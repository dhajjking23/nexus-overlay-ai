"""
NEXUS OVERLAY AI - Liquidity Sweep Strategy
Uses liquidity engine events (sweeps, stop runs) to identify reversal opportunities.
High confidence when combined with structure reversal.
"""
from __future__ import annotations
from typing import Any, Optional

from backend.strategies.base import BaseStrategy, MarketState
from backend.models import (
    DecisionState,
    LiquidityEventType,
    StructureType,
    TrendDirection,
    PatternType,
    MarketRegime,
    now_ms,
)


class LiquiditySweepStrategy(BaseStrategy):
    """
    Liquidity sweep strategy.
    
    Logic:
      1. Detect liquidity events: LIQUIDITY_SWEEP, STOP_RUN, FALSE_BREAKOUT
      2. Determine sweep direction (BUY_SIDE swept = bullish opportunity,
         SELL_SIDE swept = bearish opportunity)
      3. Confirm structure reversal: CHOCH or change from HH/HL to LH/LL
      4. Require reaction (rejection candle) at swept level
      5. Bonus for confluence with demand/supply zones
      6. Higher confidence when MTF supports reversal
    
    Liquidity sweep = price takes out a level (trapping retail) then reverses.
    BUY_SIDE swept means price went above highs, took buy-side stops → now sells.
    SELL_SIDE swept means price went below lows, took sell-side stops → now buys.
    """

    name = "liquidity_sweep"
    weight = 0.20
    min_data_quality = 40.0  # 0-100 scale
    min_candles = 5

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.min_sweep_strength = self.config.get("min_sweep_strength", 0.5)
        self.sweep_validity_ms = self.config.get("sweep_validity_ms", 300_000)  # 5 minutes

    def evaluate(self, state: MarketState) -> StrategyAssessment:
        passed, fail_reason = self._check_preconditions(state)
        if not passed:
            return self._no_signal(fail_reason)

        # --- Must have liquidity events ---
        if not state.liquidity_events:
            return self._no_signal("No liquidity events detected")

        evidence: list[str] = []
        score = 0
        direction = DecisionState.WAIT

        # --- Filter for relevant sweep-type events ---
        sweep_events = [
            e for e in state.liquidity_events
            if e.event in (
                LiquidityEventType.LIQUIDITY_SWEEP,
                LiquidityEventType.STOP_RUN,
                LiquidityEventType.FALSE_BREAKOUT,
            )
            and e.strength >= self.min_sweep_strength
            # Only consider recent events
            and (state.timestamp - e.timestamp) <= self.sweep_validity_ms
        ]

        if not sweep_events:
            # Check for equal highs/lows (potential pre-sweep)
            equal_events = [
                e for e in state.liquidity_events
                if e.event in (LiquidityEventType.EQUAL_HIGHS, LiquidityEventType.EQUAL_LOWS)
            ]
            if equal_events:
                evidence.append(
                    f"Found {len(equal_events)} potential liquidity pools "
                    f"({', '.join(e.event.value for e in equal_events)}) — awaiting sweep"
                )
            return self._no_signal("No recent sweep/stop-run events meeting criteria")

        # --- Analyze the strongest sweep event ---
        primary_event = max(sweep_events, key=lambda e: e.strength)
        evidence.append(
            f"Primary event: {primary_event.event.value} at {primary_event.price:.2f} "
            f"(strength={primary_event.strength:.2f}, {primary_event.timeframe})"
        )

        score += 20

        # --- Determine direction from sweep ---
        if primary_event.direction == "BUY_SIDE":
            # Buy-side liquidity taken → price went up and swept stops above highs
            # Expect reversal to the downside (bearish)
            direction = DecisionState.SELL
            evidence.append("BUY_SIDE swept → expectation: bearish reversal")
        elif primary_event.direction == "SELL_SIDE":
            # Sell-side liquidity taken → price went down and swept stops below lows
            # Expect reversal to the upside (bullish)
            direction = DecisionState.BUY
            evidence.append("SELL_SIDE swept → expectation: bullish reversal")
        else:
            return self._no_signal(f"Unknown sweep direction: {primary_event.direction}")

        # --- Structure reversal confirmation ---
        if state.structure is not None:
            struct = state.structure
            # CHOCH = strong reversal signal
            if struct.choch:
                score += 25
                evidence.append(f"CHOCH (Change of Character) confirmed — strong reversal signal")

            # BOS in the direction of the reversal
            if struct.bos:
                if direction == DecisionState.BUY and struct.trend == TrendDirection.BEARISH:
                    score += 10
                    evidence.append("BOS in bearish trend — possible reversal point")
                elif direction == DecisionState.SELL and struct.trend == TrendDirection.BULLISH:
                    score += 10
                    evidence.append("BOS in bullish trend — possible reversal point")

            # Check for structure shift
            if struct.structure == StructureType.SWING_LOW and direction == DecisionState.BUY:
                score += 15
                evidence.append("Swing low formed — supports bullish reversal")
            elif struct.structure == StructureType.SWING_HIGH and direction == DecisionState.SELL:
                score += 15
                evidence.append("Swing high formed — supports bearish reversal")
        else:
            evidence.append("No structure data — reversal unconfirmed")
            score -= 10

        # --- Rejection candle pattern at sweep level ---
        rejection_found = False
        for pattern in state.patterns:
            if pattern.strength < 0.5:
                continue
            if direction == DecisionState.BUY and pattern.pattern in (
                PatternType.HAMMER, PatternType.BULLISH_ENGULFING,
                PatternType.PIN_BAR, PatternType.REJECTION_CANDLE,
            ):
                score += 15
                rejection_found = True
                evidence.append(
                    f"Rejection pattern: {pattern.pattern.value} "
                    f"(strength={pattern.strength:.2f})"
                )
                break
            elif direction == DecisionState.SELL and pattern.pattern in (
                PatternType.SHOOTING_STAR, PatternType.BEARISH_ENGULFING,
                PatternType.PIN_BAR, PatternType.REJECTION_CANDLE,
            ):
                score += 15
                rejection_found = True
                evidence.append(
                    f"Rejection pattern: {pattern.pattern.value} "
                    f"(strength={pattern.strength:.2f})"
                )
                break

        if not rejection_found:
            evidence.append("No rejection pattern at sweep level — reduced confidence")
            score -= 5

        # --- Multiple sweeps (cluster) bonus ---
        if len(sweep_events) > 1:
            score += 10
            evidence.append(f"Multiple sweep events ({len(sweep_events)}) — clustered liquidity")

        # --- MTF confirmation ---
        if state.mtf is not None:
            if direction == DecisionState.BUY and state.mtf.dominant_trend == TrendDirection.BEARISH:
                score += 10
                evidence.append("MTF bearish → bullish sweep reversal aligns with MTF structure")
            elif direction == DecisionState.SELL and state.mtf.dominant_trend == TrendDirection.BULLISH:
                score += 10
                evidence.append("MTF bullish → bearish sweep reversal aligns with MTF structure")
            elif state.mtf.alignment == "conflicting":
                score -= 5
                evidence.append("MTF conflicting — partial penalty")

        # --- Minimum threshold ---
        if score < 25:
            return self._no_signal(f"Score {score} below liquidity sweep threshold")

        confidence = min(1.0, score / 75.0)

        evidence.insert(0, f"[LiquiditySweep] Direction={direction.value} Score={score}")

        return self._make_assessment(
            direction=direction,
            score=score,
            confidence=confidence,
            evidence=evidence,
            timeframe=state.timeframe,
        )