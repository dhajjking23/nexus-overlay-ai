"""
NEXUS OVERLAY AI - Market Structure Knowledge Base

Codifies ITC/SMT market structure concepts as deterministic data structures.
These are the building blocks of trend analysis and direction.

Concepts: BOS, CHOCH, HH, HL, LH, LL
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class Direction(Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


@dataclass(frozen=True)
class MarketStructureConcept:
    """Base class for all market structure concepts.

    Every concept has explicit definition, detection rules, confirmation
    requirements, strength rating, context requirements, invalidation
    rules, and known conflicts.
    """
    name: str
    code: str  # Machine-readable reason code, e.g. "BOS", "CHOCH"
    direction: Direction
    definition: str
    detection_conditions: List[str]
    confirmation: List[str]
    strength: int  # 0-100 base strength rating
    context: List[str]  # When this concept matters most
    invalidation: List[str]  # What makes this concept void
    conflicts: List[str]  # Concepts that contradict this one
    timeframe_weight: dict = field(default_factory=dict)
    # e.g. {"H4": 1.0, "H1": 0.9, "M15": 0.7, "M5": 0.5, "M1": 0.3}


@dataclass(frozen=True)
class BreakOfStructure(MarketStructureConcept):
    """BOS — Break of Structure.

    Price breaks a recent swing high (bullish) or swing low (bearish)
    confirming continuation of the current trend.
    """
    pass


@dataclass(frozen=True)
class ChangeOfCharacter(MarketStructureConcept):
    """CHOCH — Change of Character.

    Price breaks structure against the prevailing trend direction,
    signaling a potential trend reversal. First sign of trend shift.
    """
    pass


@dataclass(frozen=True)
class HigherHigh(MarketStructureConcept):
    """HH — Higher High.

    Current swing high exceeds the previous swing high.
    Bullish continuation confirmation.
    """
    pass


@dataclass(frozen=True)
class HigherLow(MarketStructureConcept):
    """HL — Higher Low.

    Current swing low is above the previous swing low.
    Bullish trend support level.
    """
    pass


@dataclass(frozen=True)
class LowerHigh(MarketStructureConcept):
    """LH — Lower High.

    Current swing high is below the previous swing high.
    Bearish trend resistance level.
    """
    pass


@dataclass(frozen=True)
class LowerLow(MarketStructureConcept):
    """LL — Lower Low.

    Current swing low falls below the previous swing low.
    Bearish continuation confirmation.
    """
    pass


# ═══════════════════════════════════════════════════════════
# PREDEFINED CONCEPT INSTANCES — The bot's market structure brain
# ═══════════════════════════════════════════════════════════

BOS_BULLISH = BreakOfStructure(
    name="Break of Structure (Bullish)",
    code="BOS_BULLISH",
    direction=Direction.BULLISH,
    definition=(
        "Price breaks above the most recent swing high in a bullish trend, "
        "confirming continuation. The break must be a candle close above the "
        "swing high level, not just a wick."
    ),
    detection_conditions=[
        "Identified swing high on the timeframe",
        "Bullish trend context (series of HH/HL before the break)",
        "Candle CLOSE above the swing high price (not just wick)",
        "The break candle body is substantial (not a doji)",
        "Volume or momentum supports the break",
    ],
    confirmation=[
        "Follow-through candle closes above the break level",
        "Increased volume on break candle",
        "Momentum indicators aligned (RSI > 50, MACD bullish)",
        "Higher timeframe structure supports bullish direction",
        "No immediate rejection wick above break level",
    ],
    strength=75,
    context=[
        "Most reliable during active trading sessions (London, NY)",
        "Stronger on higher timeframes (H4 > H1 > M15)",
        "Valid only within an established bullish structure",
        "More significant after a pullback to support",
    ],
    invalidation=[
        "Price closes back below the broken swing high",
        "CHOCH (Change of Character) forms against the BOS direction",
        "Sustained rejection above the break level",
        "Immediate reversal candle after break (engulfing opposite)",
    ],
    conflicts=[
        "CHOCH (opposite direction)",
        "Bearish divergence on momentum indicators",
        "MTF conflict (higher TF bearish while entry TF bullish BOS)",
        "Liquidity sweep at the break level (may be fake breakout)",
    ],
    timeframe_weight={"H4": 1.0, "H1": 0.9, "M15": 0.7, "M5": 0.5, "M1": 0.3},
)

BOS_BEARISH = BreakOfStructure(
    name="Break of Structure (Bearish)",
    code="BOS_BEARISH",
    direction=Direction.BEARISH,
    definition=(
        "Price breaks below the most recent swing low in a bearish trend, "
        "confirming continuation. The break must be a candle close below the "
        "swing low level."
    ),
    detection_conditions=[
        "Identified swing low on the timeframe",
        "Bearish trend context (series of LH/LL before the break)",
        "Candle CLOSE below the swing low price (not just wick)",
        "The break candle body is substantial (not a doji)",
        "Volume or momentum supports the break",
    ],
    confirmation=[
        "Follow-through candle closes below the break level",
        "Increased volume on break candle",
        "Momentum indicators aligned (RSI < 50, MACD bearish)",
        "Higher timeframe structure supports bearish direction",
        "No immediate rejection wick below break level",
    ],
    strength=75,
    context=[
        "Most reliable during active trading sessions (London, NY)",
        "Stronger on higher timeframes (H4 > H1 > M15)",
        "Valid only within an established bearish structure",
        "More significant after a pullback to resistance",
    ],
    invalidation=[
        "Price closes back above the broken swing low",
        "CHOCH (Change of Character) forms against the BOS direction",
        "Sustained rejection below the break level",
        "Immediate reversal candle after break (engulfing opposite)",
    ],
    conflicts=[
        "CHOCH (opposite direction)",
        "Bullish divergence on momentum indicators",
        "MTF conflict (higher TF bullish while entry TF bearish BOS)",
        "Liquidity sweep at the break level (may be fake breakout)",
    ],
    timeframe_weight={"H4": 1.0, "H1": 0.9, "M15": 0.7, "M5": 0.5, "M1": 0.3},
)

CHOCH_BULLISH = ChangeOfCharacter(
    name="Change of Character (Bullish)",
    code="CHOCH_BULLISH",
    direction=Direction.BULLISH,
    definition=(
        "Price breaks above a significant LOWER HIGH in a bearish trend, "
        "signaling the first sign of trend reversal from bearish to bullish. "
        "This is the initial structural shift before a new bullish trend forms."
    ),
    detection_conditions=[
        "Prior bearish trend context (series of LH/LL)",
        "Identified the most recent lower high in the downtrend",
        "Candle CLOSE above that lower high level",
        "The break must occur against the prevailing trend direction",
        "Preceded by some form of exhaustion or support response",
    ],
    confirmation=[
        "Follow-through buying after the break",
        "Volume spike on the CHOCH candle",
        "Higher timeframe showing potential reversal signals",
        "Price subsequently holds above the CHOCH level",
        "New higher low forms after CHOCH confirmation",
    ],
    strength=70,
    context=[
        "Critical for identifying trend reversals",
        "More significant on H1 and H4 timeframes",
        "First signal of trend change — expect pullback",
        "Combined with liquidity sweep at lows = high-probability reversal",
    ],
    invalidation=[
        "Price falls back below the CHOCH level",
        "New lower low forms immediately after CHOCH",
        "CHOCH was a liquidity sweep (wick-only break)",
        "Higher timeframe trend remains strongly bearish",
    ],
    conflicts=[
        "BOS bearish (continuation vs reversal signals)",
        "Higher TF bearish structure still intact",
        "Bearish engulfing immediately after CHOCH",
    ],
    timeframe_weight={"H4": 1.0, "H1": 0.95, "M15": 0.7, "M5": 0.4, "M1": 0.2},
)

CHOCH_BEARISH = ChangeOfCharacter(
    name="Change of Character (Bearish)",
    code="CHOCH_BEARISH",
    direction=Direction.BEARISH,
    definition=(
        "Price breaks below a significant HIGHER LOW in a bullish trend, "
        "signaling the first sign of trend reversal from bullish to bearish. "
        "This is the initial structural shift before a new bearish trend forms."
    ),
    detection_conditions=[
        "Prior bullish trend context (series of HH/HL)",
        "Identified the most recent higher low in the uptrend",
        "Candle CLOSE below that higher low level",
        "The break must occur against the prevailing trend direction",
        "Preceded by some form of exhaustion or resistance response",
    ],
    confirmation=[
        "Follow-through selling after the break",
        "Volume spike on the CHOCH candle",
        "Higher timeframe showing potential reversal signals",
        "Price subsequently stays below the CHOCH level",
        "New lower high forms after CHOCH confirmation",
    ],
    strength=70,
    context=[
        "Critical for identifying trend reversals",
        "More significant on H1 and H4 timeframes",
        "First signal of trend change — expect pullback",
        "Combined with liquidity sweep at highs = high-probability reversal",
    ],
    invalidation=[
        "Price recovers back above the CHOCH level",
        "New higher low forms immediately after CHOCH",
        "CHOCH was a liquidity sweep (wick-only break)",
        "Higher timeframe trend remains strongly bullish",
    ],
    conflicts=[
        "BOS bullish (continuation vs reversal signals)",
        "Higher TF bullish structure still intact",
        "Bullish engulfing immediately after CHOCH",
    ],
    timeframe_weight={"H4": 1.0, "H1": 0.95, "M15": 0.7, "M5": 0.4, "M1": 0.2},
)

HH_CONCEPT = HigherHigh(
    name="Higher High",
    code="HH",
    direction=Direction.BULLISH,
    definition=(
        "A swing high that is higher than the previous swing high. "
        "Indicates bullish continuation and upward trend health. "
        "Must be a confirmed swing (at least 3 candles to form)."
    ),
    detection_conditions=[
        "Previous swing high identified and measured",
        "Current swing high exceeds previous swing high",
        "Swing is confirmed (minimum candle structure to qualify)",
        "Price is making new highs in a bullish sequence",
    ],
    confirmation=[
        "Followed by a Higher Low (HL) — confirms trend health",
        "Increasing volume on the push to new highs",
        "Momentum indicators not showing bearish divergence",
        "Higher timeframe also showing HH sequence",
    ],
    strength=60,
    context=[
        "Most meaningful after at least 2 prior HH in sequence",
        "Weakened if accompanied by bearish RSI divergence",
        "Stronger on higher timeframes",
        "Should be accompanied by healthy HL between HHs",
    ],
    invalidation=[
        "Price immediately reverses after making the HH",
        "Bearish divergence on RSI/MACD at the HH",
        "ChoCh occurs soon after (lower high forms)",
        "HH forms on very low volume (weak participation)",
    ],
    conflicts=[
        "LH (Lower High) forming nearby — trend may be shifting",
        "Bearish divergence at the HH level",
        "MTF bearish trend while entry TF shows HH",
    ],
    timeframe_weight={"H4": 1.0, "H1": 0.85, "M15": 0.65, "M5": 0.45, "M1": 0.25},
)

HL_CONCEPT = HigherLow(
    name="Higher Low",
    code="HL",
    direction=Direction.BULLISH,
    definition=(
        "A swing low that is higher than the previous swing low. "
        "Represents the support level of an uptrend. The level from which "
        "the next bullish impulse is expected to launch."
    ),
    detection_conditions=[
        "Previous swing low identified and measured",
        "Current swing low is above the previous swing low",
        "Swing low is confirmed (at least 3 candle formation)",
        "This HL is part of a sequence of higher lows",
    ],
    confirmation=[
        "Price bounces strongly from the HL level",
        "Volume increases on the bounce",
        "Bullish price action at the HL (hammer, engulfing)",
        "The HL aligns with a known support/zone level",
    ],
    strength=65,
    context=[
        "Key level for stop-loss placement (below HL)",
        "Stronger when aligned with demand zone or order block",
        "HL at a round number or psychological level adds significance",
        "Valid only within bullish trend context",
    ],
    invalidation=[
        "Price breaks below the HL — trend structure damaged",
        "Bearish CHOCH forms from this level",
        "Extended consolidation at HL without bounce (absorption)",
        "HL becomes LL — trend reversal confirmed",
    ],
    conflicts=[
        "LL (Lower Low) — would invalidate the bullish structure",
        "Bearish liquidity sweep below HL before recovery",
        "MTF bearish while entry TF shows bullish HL",
    ],
    timeframe_weight={"H4": 1.0, "H1": 0.85, "M15": 0.65, "M5": 0.45, "M1": 0.25},
)

LH_CONCEPT = LowerHigh(
    name="Lower High",
    code="LH",
    direction=Direction.BEARISH,
    definition=(
        "A swing high that is lower than the previous swing high. "
        "Represents the resistance level of a downtrend. The level from which "
        "the next bearish impulse is expected to launch."
    ),
    detection_conditions=[
        "Previous swing high identified and measured",
        "Current swing high is below the previous swing high",
        "Swing high is confirmed (at least 3 candle formation)",
        "This LH is part of a sequence of lower highs",
    ],
    confirmation=[
        "Price rejects strongly from the LH level",
        "Volume increases on the rejection",
        "Bearish price action at the LH (engulfing, shooting star)",
        "The LH aligns with a known resistance/supply level",
    ],
    strength=65,
    context=[
        "Key level for stop-loss placement (above LH)",
        "Stronger when aligned with supply zone or order block",
        "LH at a round number or psychological level adds significance",
        "Valid only within bearish trend context",
    ],
    invalidation=[
        "Price breaks above the LH — trend structure damaged",
        "Bullish CHOCH forms from this level",
        "Extended consolidation at LH without rejection (absorption)",
        "LH becomes HH — trend reversal confirmed",
    ],
    conflicts=[
        "HH (Higher High) — would invalidate the bearish structure",
        "Bullish liquidity sweep above LH before recovery",
        "MTF bullish while entry TF shows bearish LH",
    ],
    timeframe_weight={"H4": 1.0, "H1": 0.85, "M15": 0.65, "M5": 0.45, "M1": 0.25},
)

LL_CONCEPT = LowerLow(
    name="Lower Low",
    code="LL",
    direction=Direction.BEARISH,
    definition=(
        "A swing low that is lower than the previous swing low. "
        "Indicates bearish continuation and downward trend health. "
        "Must be a confirmed swing."
    ),
    detection_conditions=[
        "Previous swing low identified and measured",
        "Current swing low falls below previous swing low",
        "Swing low is confirmed (minimum candle structure to qualify)",
        "Price is making new lows in a bearish sequence",
    ],
    confirmation=[
        "Followed by a Lower High (LH) — confirms trend health",
        "Increasing volume on the push to new lows",
        "Momentum indicators not showing bullish divergence",
        "Higher timeframe also showing LL sequence",
    ],
    strength=60,
    context=[
        "Most meaningful after at least 2 prior LL in sequence",
        "Weakened if accompanied by bullish RSI divergence",
        "Stronger on higher timeframes",
        "Should be accompanied by healthy LH between LLs",
    ],
    invalidation=[
        "Price immediately reverses after making the LL",
        "Bullish divergence on RSI/MACD at the LL",
        "ChoCh occurs soon after (higher low forms)",
        "LL forms on very low volume (weak participation)",
    ],
    conflicts=[
        "HL (Higher Low) forming nearby — trend may be shifting",
        "Bullish divergence at the LL level",
        "MTF bullish trend while entry TF shows LL",
    ],
    timeframe_weight={"H4": 1.0, "H1": 0.85, "M15": 0.65, "M5": 0.45, "M1": 0.25},
)

# Master list of all market structure concepts
ALL_STRUCTURE_CONCEPTS: List[MarketStructureConcept] = [
    BOS_BULLISH, BOS_BEARISH,
    CHOCH_BULLISH, CHOCH_BEARISH,
    HH_CONCEPT, HL_CONCEPT, LH_CONCEPT, LL_CONCEPT,
]
