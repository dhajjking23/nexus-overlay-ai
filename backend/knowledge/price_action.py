"""
NEXUS OVERLAY AI - Price Action Knowledge Base

Codifies candlestick patterns and price action signals as deterministic data.
Each pattern has explicit detection conditions, confirmation requirements,
and known conflicts.

These are the bot's eyes — pattern recognition without AI.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List


class Bias(Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


@dataclass(frozen=True)
class PriceActionConcept:
    """Base class for all price action patterns.

    Every pattern has: definition, detection_conditions, confirmation,
    strength, context, invalidation, conflicts.
    """
    name: str
    code: str  # Machine-readable reason code
    bias: Bias
    definition: str
    detection_conditions: List[str]
    confirmation: List[str]
    strength: int  # 0-100 base strength
    context: List[str]  # Where/when most reliable
    invalidation: List[str]  # What invalidates this pattern
    conflicts: List[str]  # Contradictory patterns
    min_body_ratio: float = 0.0  # Min body/range ratio for the candle
    min_wick_ratio: float = 0.0  # Min wick/range ratio for rejection patterns


# ═══════════════════════════════════════════════════════════
# BULLISH PATTERNS
# ═══════════════════════════════════════════════════════════

BULLISH_ENGULFING = PriceActionConcept(
    name="Bullish Engulfing",
    code="BULLISH_ENGULFING",
    bias=Bias.BULLISH,
    definition=(
        "A two-candle pattern where a bearish candle is completely engulfed by "
        "the following bullish candle. The bullish candle opens at or below the "
        "bearish candle's close and closes at or above the bearish candle's open. "
        "Indicates strong buying pressure overcoming selling pressure."
    ),
    detection_conditions=[
        "Previous candle is bearish (close < open)",
        "Current candle is bullish (close > open)",
        "Current candle's body completely engulfs previous candle's body",
        "Current open <= previous close",
        "Current close >= previous open",
        "Preceded by a downtrend or at a support level",
    ],
    confirmation=[
        "High volume on the engulfing candle",
        "Price continues above the engulfing candle's high on next candle",
        "Fibonacci/support confluence at the engulfing level",
        "Bullish divergence on RSI at the pattern location",
        "Higher timeframe bias is bullish",
    ],
    strength=70,
    context=[
        "Most reliable at support zones, demand zones, order blocks",
        "Stronger after a sustained downtrend (exhaustion reversal)",
        "More significant on H1 and H4 timeframes",
        "Validated by volume confirmation",
        "Weakened if it occurs mid-range without context",
    ],
    invalidation=[
        "Price falls below the low of the engulfing pattern",
        "Next candle immediately engulfs the bullish engulfing",
        "Volume is very low on the engulfing candle",
        "Higher timeframe shows strong bearish structure",
    ],
    conflicts=[
        "Bearish Engulfing forming nearby",
        "Strong bearish BOS continues after the pattern",
        "RSI already overbought (>70) — limited upside",
        "MTF bearish alignment",
    ],
    min_body_ratio=0.5,
)

BEARISH_ENGULFING = PriceActionConcept(
    name="Bearish Engulfing",
    code="BEARISH_ENGULFING",
    bias=Bias.BEARISH,
    definition=(
        "A two-candle pattern where a bullish candle is completely engulfed by "
        "the following bearish candle. The bearish candle opens at or above the "
        "bullish candle's close and closes at or below the bullish candle's open. "
        "Indicates strong selling pressure overcoming buying pressure."
    ),
    detection_conditions=[
        "Previous candle is bullish (close > open)",
        "Current candle is bearish (close < open)",
        "Current candle's body completely engulfs previous candle's body",
        "Current open >= previous close",
        "Current close <= previous open",
        "Preceded by an uptrend or at a resistance level",
    ],
    confirmation=[
        "High volume on the engulfing candle",
        "Price continues below the engulfing candle's low on next candle",
        "Fibonacci/resistance confluence at the engulfing level",
        "Bearish divergence on RSI at the pattern location",
        "Higher timeframe bias is bearish",
    ],
    strength=70,
    context=[
        "Most reliable at resistance zones, supply zones, order blocks",
        "Stronger after a sustained uptrend (exhaustion reversal)",
        "More significant on H1 and H4 timeframes",
        "Validated by volume confirmation",
        "Weakened if it occurs mid-range without context",
    ],
    invalidation=[
        "Price rises above the high of the engulfing pattern",
        "Next candle immediately engulfs the bearish engulfing",
        "Volume is very low on the engulfing candle",
        "Higher timeframe shows strong bullish structure",
    ],
    conflicts=[
        "Bullish Engulfing forming nearby",
        "Strong bullish BOS continues after the pattern",
        "RSI already oversold (<30) — limited downside",
        "MTF bullish alignment",
    ],
    min_body_ratio=0.5,
)

PIN_BAR_BULLISH = PriceActionConcept(
    name="Bullish Pin Bar",
    code="PIN_BAR_BULLISH",
    bias=Bias.BULLISH,
    definition=(
        "A candle with a very long lower wick (tail) and small body near the "
        "top of the candle. The lower wick is at least 2x the body size. "
        "Indicates price was rejected strongly from lower levels, showing "
        "buying pressure at the wick level."
    ),
    detection_conditions=[
        "Lower wick is at least 2x the body size",
        "Body is in the upper third of the candle range",
        "Upper wick is small (less than body size ideally)",
        "Occurs at a support level or after a decline",
        "The wick represents a clear rejection of lower prices",
    ],
    confirmation=[
        "Price holds above the pin bar's low on subsequent candles",
        "Volume spike during the wick formation",
        "Pin bar wick touches a known support level",
        "Higher timeframe structure supports bullish reversal",
        "Follow-through bullish candle after pin bar",
    ],
    strength=65,
    context=[
        "Most powerful at key support levels, demand zones",
        "More reliable on H1 and H4 timeframes",
        "Strongest when it closes bullish (close > open)",
        "At session lows — London/NY open ranges",
        "Less reliable in choppy/ranging markets",
    ],
    invalidation=[
        "Price breaks below the pin bar's low (wick becomes noise)",
        "Next candle closes below pin bar's body",
        "Pattern occurs mid-range without structural context",
        "Pin bar has extremely small body (near doji — ambiguous)",
    ],
    conflicts=[
        "Bearish engulfing immediately following",
        "Continued bearish BOS after the pin bar",
        "Pin bar at an area with no structural support",
    ],
    min_wick_ratio=0.6,
)

SHOOTING_STAR = PriceActionConcept(
    name="Shooting Star",
    code="SHOOTING_STAR",
    bias=Bias.BEARISH,
    definition=(
        "A candle with a very long upper wick (shadow) and small body near the "
        "bottom of the candle. The upper wick is at least 2x the body size. "
        "Indicates price was rejected strongly from higher levels, showing "
        "selling pressure at the wick level."
    ),
    detection_conditions=[
        "Upper wick is at least 2x the body size",
        "Body is in the lower third of the candle range",
        "Lower wick is small (less than body size ideally)",
        "Occurs at a resistance level or after an advance",
        "The wick represents a clear rejection of higher prices",
    ],
    confirmation=[
        "Price stays below the shooting star's high on subsequent candles",
        "Volume spike during the wick formation",
        "Shooting star wick touches a known resistance level",
        "Higher timeframe structure supports bearish reversal",
        "Follow-through bearish candle after shooting star",
    ],
    strength=65,
    context=[
        "Most powerful at key resistance levels, supply zones",
        "More reliable on H1 and H4 timeframes",
        "Strongest when it closes bearish (close < open)",
        "At session highs — London/NY open ranges",
        "Less reliable in choppy/ranging markets",
    ],
    invalidation=[
        "Price breaks above the shooting star's high (wick becomes noise)",
        "Next candle closes above shooting star's body",
        "Pattern occurs mid-range without structural context",
        "Shooting star has extremely small body (near doji — ambiguous)",
    ],
    conflicts=[
        "Bullish engulfing immediately following",
        "Continued bullish BOS after the shooting star",
        "Shooting star at an area with no structural resistance",
    ],
    min_wick_ratio=0.6,
)

REJECTION_CANDLE_BULLISH = PriceActionConcept(
    name="Bullish Rejection",
    code="REJECTION_BULLISH",
    bias=Bias.BULLISH,
    definition=(
        "Any candle that shows strong rejection of lower prices. The candle "
        "has a significant lower wick indicating sellers were present but "
        "buyers pushed price back up. Includes hammers, dragons, and other "
        "long-lower-wick patterns."
    ),
    detection_conditions=[
        "Lower wick is at least 1.5x the body size",
        "Price tested a known support/structural level",
        "Close is above the midpoint of the candle range",
        "Occurs during active trading session",
    ],
    confirmation=[
        "Bullish follow-through on next candle",
        "Volume spike at rejection level",
        "Bullish divergence on momentum indicators",
        "Higher timeframe supports bullish bias",
    ],
    strength=60,
    context=[
        "More meaningful at key structural levels",
        "Validated by session context (London/NY)",
        "Particularly important after a sustained move down",
        "Confluence with round numbers increases significance",
    ],
    invalidation=[
        "Price revisits and breaks below the rejection level",
        "Next candle completely engulfs the rejection candle bearishly",
        "No follow-through buying",
    ],
    conflicts=[
        "Bearish continuation patterns",
        "MTF strong bearish alignment",
    ],
    min_wick_ratio=0.5,
)

REJECTION_CANDLE_BEARISH = PriceActionConcept(
    name="Bearish Rejection",
    code="REJECTION_BEARISH",
    bias=Bias.BEARISH,
    definition=(
        "Any candle that shows strong rejection of higher prices. The candle "
        "has a significant upper wick indicating buyers were present but "
        "sellers pushed price back down."
    ),
    detection_conditions=[
        "Upper wick is at least 1.5x the body size",
        "Price tested a known resistance/structural level",
        "Close is below the midpoint of the candle range",
        "Occurs during active trading session",
    ],
    confirmation=[
        "Bearish follow-through on next candle",
        "Volume spike at rejection level",
        "Bearish divergence on momentum indicators",
        "Higher timeframe supports bearish bias",
    ],
    strength=60,
    context=[
        "More meaningful at key structural levels",
        "Validated by session context (London/NY)",
        "Particularly important after a sustained move up",
        "Confluence with round numbers increases significance",
    ],
    invalidation=[
        "Price revisits and breaks above the rejection level",
        "Next candle completely engulfs the rejection candle bullishly",
        "No follow-through selling",
    ],
    conflicts=[
        "Bullish continuation patterns",
        "MTF strong bullish alignment",
    ],
    min_wick_ratio=0.5,
)


# ═══════════════════════════════════════════════════════════
# NEUTRAL / COMPRESSION PATTERNS
# ═══════════════════════════════════════════════════════════

INSIDE_BAR = PriceActionConcept(
    name="Inside Bar",
    code="INSIDE_BAR",
    bias=Bias.NEUTRAL,
    definition=(
        "A candle whose entire range (high to low) is contained within the "
        "range of the previous candle. Indicates compression and indecision. "
        "Often precedes a breakout move."
    ),
    detection_conditions=[
        "Current candle's high <= previous candle's high",
        "Current candle's low >= previous candle's low",
        "Current candle's range is smaller than previous candle's range",
        "Preceded by a directional move (not in mid-range chop)",
    ],
    confirmation=[
        "Breakout direction of the mother bar confirms bias",
        "Volume expansion on breakout candle",
        "MTF structure supports the breakout direction",
        "Inside bar at a key structural level",
    ],
    strength=40,  # Neutral — direction determined by breakout
    context=[
        "Most meaningful after a clear trending move",
        "Multiple inside bars (coiling) = stronger breakout potential",
        "At key structural levels (support/resistance)",
        "During session transitions (end of Asian → London)",
    ],
    invalidation=[
        "False breakout both directions (whipsaw)",
        "Breakout occurs on low volume",
        "Mother bar itself was choppy (no clear direction)",
    ],
    conflicts=[
        "Engulfing patterns at the same level",
        "Conflicting MTF structure",
    ],
)

MOMENTUM_CANDLE = PriceActionConcept(
    name="Momentum Candle",
    code="MOMENTUM_CANDLE",
    bias=Bias.NEUTRAL,  # Direction depends on candle color
    definition=(
        "A large-body candle with minimal wicks that indicates strong directional "
        "momentum. The body should be at least 70% of the total candle range. "
        "Confirms the direction of the impulse."
    ),
    detection_conditions=[
        "Body is at least 70% of total candle range",
        "Upper and lower wicks are each less than 15% of range",
        "Substantially larger range than recent average candles",
        "Preceded by a directional move or at breakout point",
    ],
    confirmation=[
        "Volume at or above 2x the recent average",
        "Follow-through in the same direction",
        "Higher timeframe aligns with the momentum direction",
        "Momentum indicators confirming (RSI moving toward extreme)",
    ],
    strength=60,
    context=[
        "Strongest at breakout points and trend resumption",
        "Particularly meaningful at session open (London/NY)",
        "Less reliable as an isolated signal",
        "Most significant on H1 timeframes and above",
    ],
    invalidation=[
        "Immediate reversal candle of equal or greater size",
        "No follow-through on subsequent candles",
        "Low volume — lack of participation",
    ],
    conflicts=[
        "Opposite-direction momentum candle immediately following",
        "Doji/indecision at the same level",
    ],
    min_body_ratio=0.7,
)

EXHAUSTION_CANDLE = PriceActionConcept(
    name="Exhaustion Candle",
    code="EXHAUSTION_CANDLE",
    bias=Bias.NEUTRAL,  # Signals potential reversal
    definition=(
        "A candle at the end of a sustained trend that shows signs of exhaustion. "
        "Characterized by extreme range but closing near the opposite end, or "
        "a climactic volume spike followed by reversal. Often the last push."
    ),
    detection_conditions=[
        "Occurs after a sustained move (multiple candles in one direction)",
        "Extreme range or volume relative to recent candles",
        "Close is near the opposite end of the range from the trend direction",
        "May have a very long wick in the trend direction",
        "Volume spike that is the highest in the recent session",
    ],
    confirmation=[
        "Reversal candle immediately follows",
        "Volume decreases on exhaustion candle (climactic volume)",
        "RSI at extreme level (>70 or <30)",
        "Higher timeframe shows exhaustion signals",
    ],
    strength=55,
    context=[
        "Most reliable at the end of extended trends",
        "At session extremes (high/low of session)",
        "Near key structural levels (support/resistance)",
        "Combined with divergence signals = high probability",
    ],
    invalidation=[
        "Exhaustion is followed by continuation (trend resumes)",
        "Price makes new extreme in the trend direction",
        "It was just a pullback within a larger move",
    ],
    conflicts=[
        "Momentum candle in the same direction (not exhaustion)",
        "Strong trend structure still intact",
    ],
    min_body_ratio=0.3,
)

HAMMER_PATTERN = PriceActionConcept(
    name="Hammer",
    code="HAMMER",
    bias=Bias.BULLISH,
    definition=(
        "A single-candle pattern with a small body at the top, long lower wick "
        "(at least 2x body), and minimal upper wick. Forms at the bottom of a "
        "downtrend. The long lower wick shows buyers rejected lower prices."
    ),
    detection_conditions=[
        "Small body at the top third of the candle",
        "Lower wick is at least 2x the body size",
        "Upper wick is negligible (less than 10% of range ideally)",
        "Forms during or after a downtrend",
        "Not a doji (body must be visible)",
    ],
    confirmation=[
        "Next candle closes above the hammer's high",
        "Volume is elevated during hammer formation",
        "Hammer touches a support level or demand zone",
        "Bullish divergence on RSI at the hammer location",
    ],
    strength=65,
    context=[
        "Strongest at key support/demand levels",
        "More reliable on H1 and H4 timeframes",
        "At the low of a session or after a sell-off",
        "Multiple hammers at same level = strong support",
    ],
    invalidation=[
        "Price breaks below the hammer's low",
        "Next candle is a strong bearish candle",
        "Hammer forms mid-range without structural context",
    ],
    conflicts=[
        "Bearish continuation patterns forming immediately after",
        "Strong bearish MTF structure",
    ],
    min_wick_ratio=0.6,
)

DOJI_PATTERN = PriceActionConcept(
    name="Doji",
    code="DOJI",
    bias=Bias.NEUTRAL,
    definition=(
        "A candle where open and close are virtually equal, creating a cross or "
        "plus shape. Indicates indecision between buyers and sellers. "
        "Context determines whether it signals reversal or continuation."
    ),
    detection_conditions=[
        "Body size is less than 10% of total candle range",
        "Upper and lower wicks are roughly equal",
        "Clear indecision — neither buyers nor sellers dominated",
    ],
    confirmation=[
        "Context: at a key level = potential reversal signal",
        "Context: mid-trend with low volume = consolidation",
        "Followed by a strong directional candle = breakout",
        "Volume profile helps determine significance",
    ],
    strength=35,  # Low standalone strength — needs context
    context=[
        "At the end of a trend = potential reversal",
        "During a trend = pause/consolidation",
        "During high-volume session = significant indecision",
        "At key support/resistance = watch for breakout direction",
    ],
    invalidation=[
        "It was just noise — price continues in trend direction",
        "Follow-through confirms the prior trend",
    ],
    conflicts=[
        "Momentum candle (decisive vs indecisive)",
        "Any strong directional signal",
    ],
    min_body_ratio=0.1,
)

OUTSIDE_BAR = PriceActionConcept(
    name="Outside Bar",
    code="OUTSIDE_BAR",
    bias=Bias.NEUTRAL,  # Direction depends on context
    definition=(
        "A candle whose range completely engulfs the previous candle's range. "
        "The current high > previous high AND current low < previous low. "
        "Can signal volatility expansion or trend continuation."
    ),
    detection_conditions=[
        "Current candle's high > previous candle's high",
        "Current candle's low < previous candle's low",
        "Current candle's range > previous candle's range",
        "Previous candle was a smaller, contained candle",
    ],
    confirmation=[
        "Direction of the outside bar (bullish close = bullish signal)",
        "Volume expansion confirms breakout intent",
        "MTF context supports the direction",
        "Follow-through in the outside bar's direction",
    ],
    strength=55,
    context=[
        "At the end of a consolidation = breakout signal",
        "After an inside bar = volatility expansion",
        "Most meaningful on H1 timeframes and above",
        "During London/NY session open",
    ],
    invalidation=[
        "Immediate reversal (outside bar was a trap)",
        "Price re-enters the prior range on next candle",
        "Low volume — no conviction",
    ],
    conflicts=[
        "Conflicting MTF signals",
        "Inside bar immediately following (re-consolidation)",
    ],
)


# Master list of all price action concepts
ALL_PRICE_ACTION_CONCEPTS: List[PriceActionConcept] = [
    BULLISH_ENGULFING, BEARISH_ENGULFING,
    PIN_BAR_BULLISH, SHOOTING_STAR,
    REJECTION_CANDLE_BULLISH, REJECTION_CANDLE_BEARISH,
    INSIDE_BAR, OUTSIDE_BAR, DOJI_PATTERN,
    MOMENTUM_CANDLE, EXHAUSTION_CANDLE,
    HAMMER_PATTERN,
]
