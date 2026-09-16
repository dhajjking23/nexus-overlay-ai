"""
NEXUS OVERLAY AI - Core Data Models
Protocol v1.0 - Structured message definitions for MT5 <-> Backend <-> Android
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
import json


class MessageType(Enum):
    """Protocol message types"""
    # MT5 -> Backend
    MARKET_TICK = "MARKET_TICK"
    CANDLE_CLOSED = "CANDLE_CLOSED"
    SYMBOL_INFO = "SYMBOL_INFO"
    CONNECTION_STATUS = "CONNECTION_STATUS"
    HEARTBEAT = "HEARTBEAT"
    
    # Backend -> Android
    MARKET_SNAPSHOT = "MARKET_SNAPSHOT"
    SIGNAL_CREATED = "SIGNAL_CREATED"
    SIGNAL_UPDATED = "SIGNAL_UPDATED"
    SIGNAL_INVALIDATED = "SIGNAL_INVALIDATED"
    SIGNAL_EXPIRED = "SIGNAL_EXPIRED"
    DECISION_LOG = "DECISION_LOG"
    SYSTEM_STATUS = "SYSTEM_STATUS"
    ERROR = "ERROR"
    
    # Android -> Backend
    CONFIG_UPDATE = "CONFIG_UPDATE"
    CALIBRATE_OVERLAY = "CALIBRATE_OVERLAY"
    ACKNOWLEDGE = "ACKNOWLEDGE"


class DecisionState(Enum):
    """Final decision states"""
    BUY = "BUY"
    SELL = "SELL"
    WAIT = "WAIT"


class InternalDecisionState(Enum):
    """Internal decision states for tracking"""
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    DATA_STALE = "DATA_STALE"
    RISK_REJECTED = "RISK_REJECTED"
    CONFLICT = "CONFLICT"
    NO_SETUP = "NO_SETUP"
    AI_UNAVAILABLE = "AI_UNAVAILABLE"
    MARKET_CLOSED = "MARKET_CLOSED"


class SignalLifecycleState(Enum):
    """Signal lifecycle states"""
    NEW = "NEW"
    CONFIRMED = "CONFIRMED"
    ACTIVE = "ACTIVE"
    WEAKENING = "WEAKENING"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"
    COMPLETED = "COMPLETED"


class MarketRegime(Enum):
    """Market regime classification"""
    TRENDING_BULLISH = "TRENDING_BULLISH"
    TRENDING_BEARISH = "TRENDING_BEARISH"
    RANGE = "RANGE"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    BREAKOUT = "BREAKOUT"
    CONSOLIDATION = "CONSOLIDATION"
    REVERSAL = "REVERSAL"
    UNCERTAIN = "UNCERTAIN"


class TrendDirection(Enum):
    """Trend direction"""
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    PULLBACK = "PULLBACK"


class SessionType(Enum):
    """Trading sessions"""
    ASIAN = "ASIAN"
    LONDON = "LONDON"
    NEW_YORK = "NEW_YORK"
    OVERLAP = "OVERLAP"


class PatternType(Enum):
    """Price action patterns"""
    BULLISH_ENGULFING = "BULLISH_ENGULFING"
    BEARISH_ENGULFING = "BEARISH_ENGULFING"
    PIN_BAR = "PIN_BAR"
    HAMMER = "HAMMER"
    SHOOTING_STAR = "SHOOTING_STAR"
    INSIDE_BAR = "INSIDE_BAR"
    OUTSIDE_BAR = "OUTSIDE_BAR"
    DOJI = "DOJI"
    REJECTION_CANDLE = "REJECTION_CANDLE"
    MOMENTUM_CANDLE = "MOMENTUM_CANDLE"
    EXHAUSTION_CANDLE = "EXHAUSTION_CANDLE"
    COMPRESSION = "COMPRESSION"
    EXPANSION = "EXPANSION"
    BREAKOUT = "BREAKOUT"
    FALSE_BREAKOUT = "FALSE_BREAKOUT"
    RETEST = "RETEST"


class StructureType(Enum):
    """Market structure types"""
    HH = "HH"
    HL = "HL"
    LH = "LH"
    LL = "LL"
    BOS = "BOS"
    CHOCH = "CHOCH"
    SWING_HIGH = "SWING_HIGH"
    SWING_LOW = "SWING_LOW"
    TREND = "TREND"
    RANGE = "RANGE"
    CONSOLIDATION = "CONSOLIDATION"
    EXPANSION = "EXPANSION"


class LiquidityEventType(Enum):
    """Liquidity event types"""
    EQUAL_HIGHS = "EQUAL_HIGHS"
    EQUAL_LOWS = "EQUAL_LOWS"
    PREV_DAY_HIGH = "PREV_DAY_HIGH"
    PREV_DAY_LOW = "PREV_DAY_LOW"
    PREV_SESSION_HIGH = "PREV_SESSION_HIGH"
    PREV_SESSION_LOW = "PREV_SESSION_LOW"
    SWING_LIQUIDITY = "SWING_LIQUIDITY"
    LIQUIDITY_SWEEP = "LIQUIDITY_SWEEP"
    STOP_RUN = "STOP_RUN"
    FALSE_BREAKOUT = "FALSE_BREAKOUT"


class ZoneType(Enum):
    """Support/Resistance/Zone types"""
    SUPPORT = "SUPPORT"
    RESISTANCE = "RESISTANCE"
    SUPPLY = "SUPPLY"
    DEMAND = "DEMAND"
    ORDER_BLOCK = "ORDER_BLOCK"
    FAIR_VALUE_GAP = "FAIR_VALUE_GAP"
    PREVIOUS_HIGH = "PREVIOUS_HIGH"
    PREVIOUS_LOW = "PREVIOUS_LOW"
    SESSION_LEVEL = "SESSION_LEVEL"


class EntryType(Enum):
    """Entry types"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    CONFIRMATION = "CONFIRMATION"
    ZONE = "ZONE"


class SLMethod(Enum):
    """Stop loss calculation methods"""
    ATR = "ATR"
    STRUCTURE = "STRUCTURE"
    SWING = "SWING"
    ZONE = "ZONE"
    NONE = "NONE"


class TPMethod(Enum):
    """Take profit calculation methods"""
    RISK_REWARD = "RISK_REWARD"
    LIQUIDITY = "LIQUIDITY"
    SUPPORT_RESISTANCE = "SUPPORT_RESISTANCE"
    PREVIOUS_HIGH_LOW = "PREVIOUS_HIGH_LOW"
    ATR_PROJECTION = "ATR_PROJECTION"
    NONE = "NONE"


class AIProviderType(Enum):
    """AI Provider types"""
    OPENAI = "OPENAI"
    CLAUDE = "CLAUDE"
    GEMINI = "GEMINI"
    OPENROUTER = "OPENROUTER"
    LOCAL = "LOCAL"


@dataclass
class ProtocolMessage:
    """Base protocol message with security fields."""
    protocol_version: str = "1.0"
    message_type: MessageType = MessageType.HEARTBEAT
    message_id: str = ""
    sequence: int = 0
    symbol: str = "XAUUSD"
    timeframe: str = "M1"
    timestamp: int = field(default_factory=lambda: int(datetime.now().timestamp() * 1000))
    source: str = "backend"
    payload: dict = field(default_factory=dict)
    checksum: str = ""
    hmac_signature: str = ""
    nonce: str = ""
    
    def to_json(self) -> str:
        return json.dumps({
            "protocol_version": self.protocol_version,
            "message_type": self.message_type.value,
            "message_id": self.message_id,
            "sequence": self.sequence,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp,
            "source": self.source,
            "payload": self.payload,
            "checksum": self.checksum,
            "hmac_signature": self.hmac_signature,
            "nonce": self.nonce,
        })
    
    @classmethod
    def from_json(cls, json_str: str) -> ProtocolMessage:
        data = json.loads(json_str)
        return cls(
            protocol_version=data.get("protocol_version", "1.0"),
            message_type=MessageType(data["message_type"]),
            message_id=data.get("message_id", ""),
            sequence=data.get("sequence", 0),
            symbol=data.get("symbol", "XAUUSD"),
            timeframe=data.get("timeframe", "M1"),
            timestamp=data.get("timestamp", int(datetime.now().timestamp() * 1000)),
            source=data.get("source", "backend"),
            payload=data.get("payload", {}),
            checksum=data.get("checksum", ""),
            hmac_signature=data.get("hmac_signature", ""),
            nonce=data.get("nonce", ""),
        )


@dataclass
class TickData:
    """Single tick data"""
    bid: float
    ask: float
    spread: float
    volume: int
    timestamp: int
    flags: int = 0


@dataclass
class CandleData:
    """OHLC candle data"""
    open: float
    high: float
    low: float
    close: float
    volume: int
    spread: float
    timestamp: int
    timeframe: str
    complete: bool = True


@dataclass
class SymbolInfo:
    """Symbol contract specification"""
    name: str
    digits: int
    point: float
    tick_size: float
    contract_size: float
    min_lot: float
    max_lot: float
    step_lot: float
    swap_long: float
    swap_short: float
    margin_currency: str
    profit_calculation_mode: int
    exchange: str
    description: str
    timeframe_flags: int
    session_deals: int
    session_buy_orders: int
    session_sell_orders: int
    volume: int
    volume_high: int
    volume_low: int
    time: int
    bid: float
    ask: float
    last: float
    volume_real: float
    volumehigh_real: float
    volumelow_real: float


@dataclass
class IndicatorValue:
    """Structured indicator output"""
    indicator: str
    timeframe: str
    value: float
    state: str
    timestamp: int
    auxiliary: dict = field(default_factory=dict)


@dataclass
class PriceActionPattern:
    """Detected price action pattern"""
    pattern: PatternType
    timeframe: str
    location: str
    strength: float
    confirmation: bool
    invalidation: float
    timestamp: int
    candle_index: int = -1


@dataclass
class MarketStructure:
    """Market structure analysis"""
    trend: TrendDirection
    structure: StructureType
    bos: bool
    choch: bool
    swing_highs: list[float] = field(default_factory=list)
    swing_lows: list[float] = field(default_factory=list)
    timeframe: str = "M5"
    timestamp: int = field(default_factory=lambda: int(datetime.now().timestamp() * 1000))


@dataclass
class LiquidityEvent:
    """Liquidity event"""
    event: LiquidityEventType
    direction: str  # BUY_SIDE / SELL_SIDE
    price: float
    timeframe: str
    strength: float
    timestamp: int


@dataclass
class Zone:
    """Support/Resistance/Supply/Demand zone"""
    zone_type: ZoneType
    upper_price: float
    lower_price: float
    midpoint: float
    timeframe: str
    strength: float
    freshness: int
    touches: int
    invalidation: float
    timestamp: int


@dataclass
class MultiTimeframeAnalysis:
    """Multi-timeframe hierarchical analysis"""
    timeframe_analysis: dict[str, TrendDirection]  # "H4": TrendDirection.BULLISH
    alignment: str  # aligned, partially_aligned, conflicting, neutral
    dominant_trend: TrendDirection
    entry_timeframe: str
    entry_direction: TrendDirection
    conflicts: list[str] = field(default_factory=list)
    timestamp: int = field(default_factory=lambda: int(datetime.now().timestamp() * 1000))


@dataclass
class StrategyAssessment:
    """Individual strategy assessment"""
    strategy: str
    direction: DecisionState
    score: int  # 0-100
    confidence: float  # 0.0-1.0
    evidence: list[str] = field(default_factory=list)
    timeframe: str = "M5"
    timestamp: int = field(default_factory=lambda: int(datetime.now().timestamp() * 1000))


@dataclass
class ConfluenceScore:
    """Confluence weighted evidence matrix — direction-aware."""
    weights: dict[str, int]
    scores: dict[str, float]
    total_score: float
    # Directional decomposition (audit section 21, P0)
    bullish_score: float = 0.0        # Sum of bullish-biased components
    bearish_score: float = 0.0        # Sum of bearish-biased components
    neutral_score: float = 0.0        # Neutral components
    net_directional_score: float = 0.0  # bullish - bearish
    directional_agreement: float = 0.0  # How aligned indicators are (0-100)
    conflict_score: float = 0.0       # Severity of directional conflict (0-100)
    contributing_factors: list[str] = field(default_factory=list)
    timestamp: int = field(default_factory=lambda: int(datetime.now().timestamp() * 1000))


@dataclass
class MarketSnapshot:
    """Structured market snapshot for AI analysis"""
    symbol: str
    price: float
    spread: float
    trend: dict[str, str]
    structure: dict[str, str]
    liquidity: dict
    price_action: dict
    momentum: dict
    volatility: dict
    session: str
    regime: str
    data_quality: float
    timestamp: int


@dataclass
class AIAssessment:
    """AI analysis output"""
    provider: AIProviderType
    assessment: str  # bullish, bearish, neutral, contradictions, missing_confirmation
    confidence: float
    explanation: str
    timestamp: int


@dataclass
class RiskValidation:
    """Risk engine validation result"""
    passed: bool
    checks: dict[str, bool]
    failed_reasons: list[str]
    rr: float
    min_rr: float
    spread: float
    max_spread: float
    data_quality: float
    timestamp: int


@dataclass
class EntryCalculation:
    """Entry price calculation"""
    entry_type: EntryType
    price: float
    reason: str
    confirmation_candles: int
    timestamp: int


@dataclass
class SLTPCalculation:
    """SL/TP calculation"""
    sl_method: SLMethod
    sl_price: float
    sl_reason: str
    tp1_method: TPMethod
    tp1_price: float
    tp2_method: TPMethod
    tp2_price: float
    tp3_method: TPMethod
    tp3_price: float
    invalidation_reason: str
    timestamp: int


@dataclass
class ConfidenceModel:
    """Structured confidence breakdown — AI-INDEPENDENT.

    ``deterministic_score`` is computed solely from technical, structure,
    risk, and data-quality components.  AI has NO influence on it.

    ``ai_advisory_score`` is a *separate*, optional layer produced by
    an AI provider.  It is informational only and never blended into
    ``deterministic_score``.
    """
    technical_score: float
    risk_score: float
    data_quality_score: float
    ai_confidence: float  # kept for backward compat (same as ai_advisory_score)
    mtf_agreement: float
    deterministic_score: float  # was final_confidence — AI-free
    ai_advisory_score: float = 0.0  # separate AI layer (0-100)
    timestamp: int = 0

    @property
    def final_confidence(self) -> float:
        """Backward-compatible alias → deterministic_score."""
        return self.deterministic_score


@dataclass
class TradingSignal:
    """Complete trading signal - THE FINAL OUTPUT"""
    decision: DecisionState
    confidence: int  # 0-100, canonical score (formerly named 'confidence')
    symbol: str
    entry: float
    sl: float
    tp1: float
    tp2: float
    tp3: float
    rr: float
    trend: str
    regime: str
    evidence: list[str]
    invalidations: list[str]
    timestamp: int
    lifecycle_state: SignalLifecycleState = SignalLifecycleState.NEW
    signal_id: str = ""
    mtf_analysis: Optional[MultiTimeframeAnalysis] = None
    confluence: Optional[ConfluenceScore] = None
    risk_validation: Optional[RiskValidation] = None
    entry_calc: Optional[EntryCalculation] = None
    sltp_calc: Optional[SLTPCalculation] = None
    confidence_model: Optional[ConfidenceModel] = None
    ai_assessment: Optional[AIAssessment] = None
    data_quality_score: float = 100.0

    @property
    def decision_score(self) -> int:
        """Canonical score name per audit spec. Returns confidence value (0-100)."""
        return self.confidence

    def to_dict(self) -> dict:
        score = self.confidence
        return {
            "decision": self.decision.value,
            "confidence": score,
            "decision_score": score,
            "symbol": self.symbol,
            "entry": self.entry,
            "sl": self.sl,
            "tp1": self.tp1,
            "tp2": self.tp2,
            "tp3": self.tp3,
            "rr": self.rr,
            "trend": self.trend,
            "regime": self.regime,
            "evidence": self.evidence,
            "invalidations": self.invalidations,
            "timestamp": self.timestamp,
            "lifecycle_state": self.lifecycle_state.value,
            "signal_id": self.signal_id,
            "data_quality_score": self.data_quality_score,
            "mtf_analysis": self.mtf_analysis.__dict__ if self.mtf_analysis else None,
            "confluence": self.confluence.__dict__ if self.confluence else None,
            "risk_validation": self.risk_validation.__dict__ if self.risk_validation else None,
            "entry_calc": self.entry_calc.__dict__ if self.entry_calc else None,
            "sltp_calc": self.sltp_calc.__dict__ if self.sltp_calc else None,
            "confidence_model": self.confidence_model.__dict__ if self.confidence_model else None,
            "ai_assessment": self.ai_assessment.__dict__ if self.ai_assessment else None,
        }


@dataclass
class DecisionLogEntry:
    """Permanent decision log entry"""
    id: str
    timestamp: int
    symbol: str
    timeframe: str
    decision: DecisionState
    decision_score: int  # 0-100
    entry: float
    sl: float
    tp1: float
    tp2: float
    tp3: float
    rr: float
    market_regime: str
    trend: str
    structure: str
    liquidity_state: str
    strategy_scores: dict[str, float]
    indicator_snapshot: dict[str, float]
    evidence: list[str]
    invalidations: list[str]
    ai_assessment: str
    data_quality: float
    signal_status: SignalLifecycleState


@dataclass
class SystemStatus:
    """System diagnostics"""
    status: str  # ONLINE, DEGRADED, OFFLINE
    mt5_connected: bool
    data_live: bool
    ai_ready: bool
    decision_ready: bool
    websocket_clients: int
    last_tick: int
    last_candle: int
    data_quality: float
    engine_status: dict[str, str]
    memory_mb: float
    cpu_percent: float
    timestamp: int = field(default_factory=lambda: int(datetime.now().timestamp() * 1000))


@dataclass
class OverlayCalibration:
    """Android overlay coordinate calibration"""
    chart_left: int
    chart_top: int
    chart_width: int
    chart_height: int
    price_top: float
    price_bottom: float
    symbol: str
    timeframe: str
    timestamp: int


# Utility functions
def now_ms() -> int:
    return int(datetime.now().timestamp() * 1000)


def pips_to_price(pips: float, digits: int = 2) -> float:
    """Convert pips to price offset based on symbol digits"""
    if digits == 2:  # XAUUSD
        return pips * 0.01
    elif digits == 3:
        return pips * 0.001
    elif digits == 5:
        return pips * 0.00001
    return pips * 0.0001


def price_to_pips(price_diff: float, digits: int = 2) -> float:
    """Convert price difference to pips"""
    if digits == 2:
        return price_diff / 0.01
    elif digits == 3:
        return price_diff / 0.001
    elif digits == 5:
        return price_diff / 0.00001
    return price_diff / 0.0001