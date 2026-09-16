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
"""
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
    BullishEngulfing,
    BearishEngulfing,
    PinBar,
    Hammer,
    ShootingStar,
    RejectionCandle,
    InsideBar,
    OutsideBar,
    Doji,
    MomentumCandle,
    ExhaustionCandle,
    ALL_PRICE_ACTION_CONCEPTS,
)
from backend.knowledge.liquidity import (
    LiquidityConcept,
    LiquiditySweep,
    FalseBreakout,
    Displacement,
    EqualHighs,
    EqualLows,
    StopRun,
    ALL_LIQUIDITY_CONCEPTS,
)
from backend.knowledge.session import (
    SessionConcept,
    LondonSession,
    NewYorkSession,
    TokyoSession,
    LondonNewYorkOverlap,
    ALL_SESSION_CONCEPTS,
)
from backend.knowledge.risk import (
    RiskConcept,
    SpreadRisk,
    VolatilityRisk,
    RiskRewardRisk,
    SessionRisk,
    NewsRisk,
    DataQualityRisk,
    SignalAgeRisk,
    ALL_RISK_CONCEPTS,
)

__all__ = [
    # Market Structure
    "MarketStructureConcept", "BreakOfStructure", "ChangeOfCharacter",
    "HigherHigh", "HigherLow", "LowerHigh", "LowerLow",
    "ALL_STRUCTURE_CONCEPTS",
    # Price Action
    "PriceActionConcept", "BullishEngulfing", "BearishEngulfing",
    "PinBar", "Hammer", "ShootingStar", "RejectionCandle",
    "InsideBar", "OutsideBar", "Doji", "MomentumCandle", "ExhaustionCandle",
    "ALL_PRICE_ACTION_CONCEPTS",
    # Liquidity
    "LiquidityConcept", "LiquiditySweep", "FalseBreakout", "Displacement",
    "EqualHighs", "EqualLows", "StopRun",
    "ALL_LIQUIDITY_CONCEPTS",
    # Session
    "SessionConcept", "LondonSession", "NewYorkSession", "TokyoSession",
    "LondonNewYorkOverlap", "ALL_SESSION_CONCEPTS",
    # Risk
    "RiskConcept", "SpreadRisk", "VolatilityRisk", "RiskRewardRisk",
    "SessionRisk", "NewsRisk", "DataQualityRisk", "SignalAgeRisk",
    "ALL_RISK_CONCEPTS",
]
