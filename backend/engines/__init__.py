"""
NEXUS OVERLAY AI - Engines Package

Engine Pipeline:
Market Data -> Indicators -> Structure -> Liquidity -> Zones -> MTF ->
Session -> Regime -> Strategies -> Risk -> Entry/SL/TP -> Confidence -> Decision

PHASE C additions:
  EvidenceGraph (directional evidence aggregation)
  TradeThesis (canonical trading thesis)
  MarketSnapshot (atomic decision-time snapshot)
"""
from backend.engines.market_data_engine import MarketDataEngine
from backend.engines.indicator_engine import IndicatorEngine
from backend.engines.price_action_engine import PriceActionEngine
from backend.engines.structure_engine import StructureEngine
from backend.engines.liquidity_engine import LiquidityEngine
from backend.engines.zone_engine import ZoneEngine
from backend.engines.mtf_engine import MTFEngine
from backend.engines.session_engine import SessionEngine
from backend.engines.regime_engine import RegimeEngine
from backend.engines.strategy_engine import StrategyEngine
from backend.engines.confluence_engine import ConfluenceEngine
from backend.engines.risk_engine import RiskEngine
from backend.engines.entry_engine import EntryEngine
from backend.engines.sl_engine import SLEngine
from backend.engines.tp_engine import TPEngine
from backend.engines.confidence_model import ConfidenceModelEngine
from backend.engines.decision_engine import (
    DecisionEngine, DecisionEngineOutput, DecisionResult, ReasonCode,
)
from backend.engines.safety_governor import SafetyGovernor, SafetyVerdict
from backend.engines.evidence_graph import (
    EvidenceGraph, EvidenceAssessment, EvidenceItem,
    ConflictSeverity, MissingConfirmation, InvalidationCondition,
)
from backend.engines.trade_thesis import (
    TradeThesis, Direction, SetupType, MarketRegime, HTFBias,
    EvidenceRef, RiskFlag, create_wait_thesis, create_no_trade_thesis,
)
from backend.engines.market_snapshot import (
    MarketSnapshot, ClockDiscipline, DataSource,
    SymbolSpecification, generate_snapshot_id,
)
from backend.engines.engine_health import (
    EngineHealthState, EngineHealth, EngineHealthTracker,
    get_health_tracker, reset_health_tracker,
)

__all__ = [
    # Existing engines
    "MarketDataEngine", "IndicatorEngine", "PriceActionEngine",
    "StructureEngine", "LiquidityEngine", "ZoneEngine", "MTFEngine",
    "SessionEngine", "RegimeEngine", "StrategyEngine", "ConfluenceEngine",
    "RiskEngine", "EntryEngine", "SLEngine", "TPEngine", "ConfidenceModelEngine",
    "DecisionEngine", "DecisionEngineOutput", "SafetyGovernor", "SafetyVerdict",
    # PHASE C — Decision Result
    "DecisionResult", "ReasonCode",
    # PHASE C — Evidence Graph
    "EvidenceGraph", "EvidenceAssessment", "EvidenceItem",
    "ConflictSeverity", "MissingConfirmation", "InvalidationCondition",
    # PHASE C — Trade Thesis
    "TradeThesis", "Direction", "SetupType", "MarketRegime", "HTFBias",
    "EvidenceRef", "RiskFlag", "create_wait_thesis", "create_no_trade_thesis",
    # PHASE C — Market Snapshot
    "MarketSnapshot", "ClockDiscipline", "DataSource",
    "SymbolSpecification", "generate_snapshot_id",
    # Engine Health Tracking
    "EngineHealthState", "EngineHealth", "EngineHealthTracker",
    "get_health_tracker", "reset_health_tracker",
]
