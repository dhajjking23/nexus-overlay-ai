# NEXUS OVERLAY AI - Configuration Helpers
"""
Common configuration used across multiple components.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class MarketState:
    """Consolidated market state passed between engines"""
    symbol: str = "XAUUSD"
    price: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    spread: float = 0.0
    
    # Candles per timeframe
    candles: dict[str, list] = field(default_factory=dict)
    
    # Tick data
    last_tick_time: int = 0
    
    # Indicator values (from indicator engine)
    indicators: dict[str, Any] = field(default_factory=dict)
    
    # Structure analysis
    structure: Any = None  # MarketStructure
    
    # Liquidity events
    liquidity_events: list = field(default_factory=list)
    
    # Price action patterns
    price_action_patterns: list = field(default_factory=list)
    
    # MTF analysis
    mtf_analysis: Any = None  # MultiTimeframeAnalysis
    
    # Zone data
    zones: list = field(default_factory=list)
    
    # Session info
    current_session: str = ""
    
    # Regime
    regime: Any = None  # MarketRegime
    
    # Data quality
    data_quality: float = 100.0
    
    # Connection state
    connected: bool = False
    data_live: bool = False
    
    # Timestamp
    timestamp: int = field(default_factory=lambda: int(datetime.now().timestamp() * 1000))
    
    def to_dict(self) -> dict:
        """Convert to dict for serialization"""
        return {
            "symbol": self.symbol,
            "price": self.price,
            "bid": self.bid,
            "ask": self.ask,
            "spread": self.spread,
            "last_tick_time": self.last_tick_time,
            "data_quality": self.data_quality,
            "connected": self.connected,
            "data_live": self.data_live,
            "current_session": self.current_session,
            "regime": self.regime.value if self.regime else None,
            "indicators_count": len(self.indicators),
            "timeframes_loaded": list(self.candles.keys()),
            "liquidity_events_count": len(self.liquidity_events),
            "price_action_count": len(self.price_action_patterns),
            "zones_count": len(self.zones),
        }


@dataclass  
class EngineResult:
    """Generic result from an engine"""
    success: bool = True
    data: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    execution_time_ms: float = 0.0
    
    def add_error(self, error: str) -> None:
        self.errors.append(error)
        self.success = False
    
    def add_warning(self, warning: str) -> None:
        self.warnings.append(warning)


@dataclass
class PipelineResult:
    """Full pipeline execution result"""
    decision: str = "WAIT"
    signal: Any = None  # TradingSignal or None
    market_state: MarketState = field(default_factory=MarketState)
    safety_check: EngineResult = field(default_factory=EngineResult)
    risk_check: EngineResult = field(default_factory=EngineResult)
    confidence: float = 0.0
    evidence: list = field(default_factory=list)
    engine_results: dict[str, EngineResult] = field(default_factory=dict)
    execution_time_ms: float = 0.0
    timestamp: int = field(default_factory=lambda: int(datetime.now().timestamp() * 1000))
