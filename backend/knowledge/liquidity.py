"""
NEXUS OVERLAY AI - Liquidity Knowledge Base

Codifies liquidity concepts as deterministic data.
Smart money concepts: sweep, false breakout, displacement, equal highs/lows.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List


class Bias(Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class LiquiditySide(Enum):
    BUY_SIDE = "BUY_SIDE"   # Liquidity above price (stop losses of shorts)
    SELL_SIDE = "SELL_SIDE"  # Liquidity below price (stop losses of longs)


@dataclass(frozen=True)
class LiquidityConcept:
    """Base class for all liquidity concepts.

    Liquidity is the fuel of smart money moves. Understanding where liquidity
    rests — and how it gets consumed — is critical for directional analysis.
    """
    name: str
    code: str  # Machine-readable reason code
    bias: Bias
    definition: str
    detection_conditions: List[str]
    confirmation: List[str]
    strength: int  # 0-100
    context: List[str]
    invalidation: List[str]
    conflicts: List[str]
    liquidity_side: LiquiditySide = LiquiditySide.BUY_SIDE


# ═══════════════════════════════════════════════════════════
# LIQUIDITY CONCEPTS
# ═══════════════════════════════════════════════════════════

LIQUIDITY_SWEEP_BUY_SIDE = LiquidityConcept(
    name="Buy-Side Liquidity Sweep",
    code="LIQUIDITY_SWEEP",
    bias=Bias.BEARISH,
    definition=(
        "Price temporarily breaches above a known liquidity level (swing high, "
        "equal highs, session high, previous day high, round number) but fails "
        "to sustain the break. Closes back below the level. Smart money has "
        "consumed the buy-side liquidity (triggered short stops) and is now "
        "free to push price lower."
    ),
    detection_conditions=[
        "Identifiable liquidity pool above current price (equal highs, swing high, session high, PDH, round number)",
        "Price wicks above the liquidity level (penetration)",
        "Candle CLOSES back below the liquidity level",
        "The breach was temporary — not sustained acceptance",
        "Often accompanied by a rejection candle (pin bar, shooting star)",
    ],
    confirmation=[
        "Immediate bearish displacement (strong move lower after sweep)",
        "Bearish engulfing or rejection candle at the sweep level",
        "CHOCH or BOS forms bearish after the sweep",
        "Volume spike at the sweep level followed by rejection",
        "Higher timeframe resistance or bearish structure",
    ],
    strength=80,
    context=[
        "One of the highest-probability setups in SMC/ICT",
        "Most effective at session highs (London, NY)",
        "Powerful after accumulation/ranging period",
        "When combined with BOS bearish = high conviction SELL",
        "At PDH (Previous Day High) or PWH (Previous Week High)",
    ],
    invalidation=[
        "Price sustains above the swept level (acceptance)",
        "Candle closes above the liquidity level and holds",
        "No bearish displacement follows the sweep",
        "Higher timeframe flips bullish after the sweep",
    ],
    conflicts=[
        "BOS bullish after sweep — may be genuine breakout, not sweep",
        "MTF bullish alignment while expecting bearish from sweep",
        "Sweep followed by continued bullish momentum",
    ],
    liquidity_side=LiquiditySide.BUY_SIDE,
)

LIQUIDITY_SWEEP_SELL_SIDE = LiquidityConcept(
    name="Sell-Side Liquidity Sweep",
    code="LIQUIDITY_SWEEP_SELL",
    bias=Bias.BULLISH,
    definition=(
        "Price temporarily breaches below a known liquidity level (swing low, "
        "equal lows, session low, previous day low, round number) but fails "
        "to sustain the break. Closes back above the level. Smart money has "
        "consumed the sell-side liquidity (triggered long stops) and is now "
        "free to push price higher."
    ),
    detection_conditions=[
        "Identifiable liquidity pool below current price (equal lows, swing low, session low, PDL, round number)",
        "Price wicks below the liquidity level (penetration)",
        "Candle CLOSES back above the liquidity level",
        "The breach was temporary — not sustained acceptance",
        "Often accompanied by a rejection candle (hammer, pin bar)",
    ],
    confirmation=[
        "Immediate bullish displacement (strong move higher after sweep)",
        "Bullish engulfing or rejection candle at the sweep level",
        "CHOCH or BOS forms bullish after the sweep",
        "Volume spike at the sweep level followed by rejection",
        "Higher timeframe support or bullish structure",
    ],
    strength=80,
    context=[
        "One of the highest-probability setups in SMC/ICT",
        "Most effective at session lows (London, NY)",
        "Powerful after accumulation/ranging period",
        "When combined with BOS bullish = high conviction BUY",
        "At PDL (Previous Day Low) or PWL (Previous Week Low)",
    ],
    invalidation=[
        "Price sustains below the swept level (acceptance)",
        "Candle closes below the liquidity level and holds",
        "No bullish displacement follows the sweep",
        "Higher timeframe flips bearish after the sweep",
    ],
    conflicts=[
        "BOS bearish after sweep — may be genuine breakdown",
        "MTF bearish alignment while expecting bullish from sweep",
        "Sweep followed by continued bearish momentum",
    ],
    liquidity_side=LiquiditySide.SELL_SIDE,
)

FALSE_BREAKOUT = LiquidityConcept(
    name="False Breakout",
    code="FALSE_BREAKOUT",
    bias=Bias.NEUTRAL,  # Direction depends on context
    definition=(
        "Price breaks out of a range or past a key level but immediately "
        "reverses, trapping breakout traders. Similar to liquidity sweep but "
        "specifically about range breakouts. The breakout candle closes beyond "
        "the level, but the next candle reverses completely."
    ),
    detection_conditions=[
        "Clear range or consolidation identified",
        "Price breaks beyond the range boundary",
        "Breakout candle closes beyond the level (not just wick)",
        "Next candle reverses and closes back within the range",
        "Volume on reversal is higher than on breakout",
    ],
    confirmation=[
        "Strong reversal candle (engulfing the breakout candle)",
        "Volume on reversal exceeds breakout volume",
        "Pattern at a known resistance/support confluence",
        "Higher timeframe shows the opposite bias",
    ],
    strength=70,
    context=[
        "Most common during ranging/choppy markets",
        "At key round numbers and psychological levels",
        "During low-liquidity periods (between sessions)",
        "When spread is wider than usual",
    ],
    invalidation=[
        "Price re-establishes beyond the breakout level",
        "Breakout was a genuine shift (no reversal)",
        "Next candle continues in breakout direction",
    ],
    conflicts=[
        "Genuine breakout (BOS) with follow-through",
        "MTF aligned with breakout direction",
    ],
    liquidity_side=LiquiditySide.BUY_SIDE,  # Default; actual depends on direction
)

DISPLACEMENT = LiquidityConcept(
    name="Displacement",
    code="DISPLACEMENT",
    bias=Bias.NEUTRAL,  # Direction determined by candle
    definition=(
        "A strong, impulsive price move that creates a clear imbalance between "
        "buyers and sellers. Characterized by large candles, minimal wicks, and "
        "a clear direction. Displacement creates fair value gaps (FVG) and signals "
        "smart money directional intent."
    ),
    detection_conditions=[
        "Candle range is significantly larger than recent average (2x+ ATR)",
        "Body is a large percentage of the candle range (>70%)",
        "Minimal opposing wicks (clean directional move)",
        "Follow-through in the same direction on next candle(s)",
        "Creates a gap between consecutive candle wicks (FVG)",
    ],
    confirmation=[
        "Volume spike 2x+ average during displacement",
        "Subsequent candles respect the displacement zone",
        "Fair value gap (FVG) visible in the displacement area",
        "Higher timeframe aligns with displacement direction",
        "Displacement occurs at session open or after news",
    ],
    strength=75,
    context=[
        "Strongest when it breaks structure (BOS)",
        "At London/NY session open — institutional flows",
        "After accumulation/ranging period — breakout move",
        "Near news events — directional conviction",
        "Creates order blocks and FVGs for future reactions",
    ],
    invalidation=[
        "Price returns to fully fill the displacement gap",
        "Equal or larger opposite displacement occurs",
        "No follow-through — displacement was a one-off spike",
        "Displacement during thin liquidity (not institutional)",
    ],
    conflicts=[
        "Opposite displacement immediately following",
        "Price fills the FVG created by displacement (disproves strength)",
        "MTF conflicting direction",
    ],
    liquidity_side=LiquiditySide.BUY_SIDE,  # Default; direction from candle
)

EQUAL_HIGHS = LiquidityConcept(
    name="Equal Highs Liquidity Pool",
    code="EQUAL_HIGHS",
    bias=Bias.BEARISH,  # Attract bearish sweep
    definition=(
        "Two or more swing highs at approximately the same level. This creates "
        "a pool of buy-side liquidity (stop losses for short positions above "
        "the highs). Smart money often sweeps this level before reversing."
    ),
    detection_conditions=[
        "Two or more swing highs within 5-10 points of each other",
        "The highs are clearly visible on the chart",
        "Not a true resistance — no sustained selling at the level",
        "Time between the highs allows stops to accumulate",
    ],
    confirmation=[
        "Liquidity sweep above the equal highs followed by reversal",
        "Volume spike during the sweep that fails to hold",
        "Bearish displacement after sweep of the equal highs",
        "CHOCH forms bearish after the sweep",
    ],
    strength=65,
    context=[
        "The more equal highs, the larger the liquidity pool",
        "More significant on H1 and H4 timeframes",
        "Equal highs at session/PDH level = prime sweep target",
        "Often targeted during London or NY session",
    ],
    invalidation=[
        "Price breaks above and sustains (true breakout)",
        "Equal highs become genuine resistance with multiple rejections",
        "Time passes without sweep — level may lose significance",
    ],
    conflicts=[
        "Genuine resistance with increasing selling pressure",
        "MTF bullish structure pushing higher",
    ],
    liquidity_side=LiquiditySide.BUY_SIDE,
)

EQUAL_LOWS = LiquidityConcept(
    name="Equal Lows Liquidity Pool",
    code="EQUAL_LOWS",
    bias=Bias.BULLISH,  # Attract bullish sweep
    definition=(
        "Two or more swing lows at approximately the same level. This creates "
        "a pool of sell-side liquidity (stop losses for long positions below "
        "the lows). Smart money often sweeps this level before reversing."
    ),
    detection_conditions=[
        "Two or more swing lows within 5-10 points of each other",
        "The lows are clearly visible on the chart",
        "Not a true support — no sustained buying at the level",
        "Time between the lows allows stops to accumulate",
    ],
    confirmation=[
        "Liquidity sweep below the equal lows followed by reversal",
        "Volume spike during the sweep that fails to hold",
        "Bullish displacement after sweep of the equal lows",
        "CHOCH forms bullish after the sweep",
    ],
    strength=65,
    context=[
        "The more equal lows, the larger the liquidity pool",
        "More significant on H1 and H4 timeframes",
        "Equal lows at session/PDL level = prime sweep target",
        "Often targeted during London or NY session",
    ],
    invalidation=[
        "Price breaks below and sustains (true breakdown)",
        "Equal lows become genuine support with multiple bounces",
        "Time passes without sweep — level may lose significance",
    ],
    conflicts=[
        "Genuine support with increasing buying pressure",
        "MTF bearish structure pushing lower",
    ],
    liquidity_side=LiquiditySide.SELL_SIDE,
)

STOP_RUN = LiquidityConcept(
    name="Stop Run",
    code="STOP_RUN",
    bias=Bias.NEUTRAL,
    definition=(
        "A rapid price move that triggers a cluster of stop-loss orders at a "
        "known level, often creating a spike/wick. Similar to liquidity sweep "
        "but specifically describes the mechanism of stop order triggering. "
        "The move is fast and often reverses immediately."
    ),
    detection_conditions=[
        "Sharp price spike through a known level",
        "Long wick above/below the spike level",
        "Very short duration of the spike (quick in-and-out)",
        "Volume spike during the stop run",
        "Level was a known cluster of stops (equal highs/lows, swing)",
    ],
    confirmation=[
        "Immediate reversal after the stop run",
        "Price closes back within the prior range",
        "Follow-through in the direction of the sweep reversal",
        "Displacement in the opposite direction of the spike",
    ],
    strength=70,
    context=[
        "More common during high-volume sessions",
        "At session extremes (Asian high/low targeted by London)",
        "Before major news releases — liquidity grab",
        "At round numbers where stops cluster",
    ],
    invalidation=[
        "Price sustains beyond the stop run level",
        "No reversal follows the spike",
        "The spike was just the beginning of a larger move",
    ],
    conflicts=[
        "Genuine breakout (BOS) with continuation",
        "MTF aligned with the spike direction",
    ],
    liquidity_side=LiquiditySide.BUY_SIDE,  # Default; depends on direction
)


# Master list of all liquidity concepts
ALL_LIQUIDITY_CONCEPTS: List[LiquidityConcept] = [
    LIQUIDITY_SWEEP_BUY_SIDE,
    LIQUIDITY_SWEEP_SELL_SIDE,
    FALSE_BREAKOUT,
    DISPLACEMENT,
    EQUAL_HIGHS,
    EQUAL_LOWS,
    STOP_RUN,
]
