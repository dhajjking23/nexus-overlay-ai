"""
NEXUS OVERLAY AI - Trading Knowledge Base

Codifies trading concepts as deterministic, testable Python data structures.
No AI dependency — the bot has explicit, verifiable trading knowledge.

Each concept includes:
  - definition: What the concept IS
  - detection_conditions: How to IDENTIFY it
  - confirmation: What SUPPORTS it
  - strength: How STRONG the signal is (0-100)
  - context: When it MATTERS most
  - invalidation: What INVALIDATES it
  - conflicts: What CONFLICTS with it

PHASE C — AI Independence: The Trading Intelligence Core has its own brain.

Knowledge Base Version: 1.0.0
Every signal/decision should reference knowledge_version in its metadata.
"""
# Knowledge Base Version — increment when concepts change
KB_VERSION = "1.0.0"

from backend.knowledge.market_structure import (
    MarketStructureConcept,
    BreakOfStructure,
    ChangeOfCharacter,
    HigherHigh,
    HigherLow,
    LowerHigh,
    LowerLow,
    ALL_STRUCTURE_CONCEPTS,
)
from backend.knowledge.price_action import (
    PriceActionConcept,
    BULLISH_ENGULFING,
    BEARISH_ENGULFING,
    PIN_BAR_BULLISH,
    SHOOTING_STAR,
    REJECTION_CANDLE_BULLISH,
    REJECTION_CANDLE_BEARISH,
    INSIDE_BAR,
    OUTSIDE_BAR,
    DOJI_PATTERN,
    MOMENTUM_CANDLE,
    EXHAUSTION_CANDLE,
    HAMMER_PATTERN,
    ALL_PRICE_ACTION_CONCEPTS,
)
from backend.knowledge.liquidity import (
    LiquidityConcept,
    LIQUIDITY_SWEEP_BUY_SIDE,
    LIQUIDITY_SWEEP_SELL_SIDE,
    FALSE_BREAKOUT,
    DISPLACEMENT,
    EQUAL_HIGHS,
    EQUAL_LOWS,
    STOP_RUN,
    ALL_LIQUIDITY_CONCEPTS,
)
from backend.knowledge.session import (
    SessionConcept,
    LONDON_SESSION,
    NEW_YORK_SESSION,
    TOKYO_SESSION,
    LONDON_NEW_YORK_OVERLAP,
    ALL_SESSION_CONCEPTS,
)
from backend.knowledge.risk import (
    RiskConcept,
    SPREAD_RISK,
    VOLATILITY_RISK,
    SESSION_RISK,
    NEWS_RISK,
    DATA_QUALITY_RISK,
    SIGNAL_AGE_RISK,
    ALL_RISK_CONCEPTS,
)

__all__ = [
    # Knowledge Base Version
    "KB_VERSION",
    # Market Structure
    "MarketStructureConcept", "BreakOfStructure", "ChangeOfCharacter",
    "HigherHigh", "HigherLow", "LowerHigh", "LowerLow",
    "ALL_STRUCTURE_CONCEPTS",
    # Price Action
    "PriceActionConcept", "BULLISH_ENGULFING", "BEARISH_ENGULFING",
    "PIN_BAR_BULLISH", "SHOOTING_STAR", "REJECTION_CANDLE_BULLISH",
    "REJECTION_CANDLE_BEARISH", "INSIDE_BAR", "OUTSIDE_BAR",
    "DOJI_PATTERN", "MOMENTUM_CANDLE", "EXHAUSTION_CANDLE",
    "HAMMER_PATTERN", "ALL_PRICE_ACTION_CONCEPTS",
    # Liquidity
    "LiquidityConcept", "LIQUIDITY_SWEEP_BUY_SIDE", "LIQUIDITY_SWEEP_SELL_SIDE",
    "FALSE_BREAKOUT", "DISPLACEMENT", "EQUAL_HIGHS", "EQUAL_LOWS",
    "STOP_RUN", "ALL_LIQUIDITY_CONCEPTS",
    # Session
    "SessionConcept", "LONDON_SESSION", "NEW_YORK_SESSION",
    "TOKYO_SESSION", "LONDON_NEW_YORK_OVERLAP", "ALL_SESSION_CONCEPTS",
    # Risk
    "RiskConcept", "SPREAD_RISK", "VOLATILITY_RISK", "SESSION_RISK",
    "NEWS_RISK", "DATA_QUALITY_RISK", "SIGNAL_AGE_RISK",
    "ALL_RISK_CONCEPTS",
]
