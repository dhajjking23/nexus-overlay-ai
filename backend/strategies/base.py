"""
NEXUS OVERLAY AI - Strategy Base
Abstract base class for all trading strategies.
Every strategy receives market state and returns a StrategyAssessment.
"""
from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from backend.models import (
    DecisionState,
    StrategyAssessment,
    IndicatorValue,
    MarketStructure,
    LiquidityEvent,
    PriceActionPattern,
    MultiTimeframeAnalysis,
    CandleData,
    SessionType,
    MarketRegime,
    TrendDirection,
    now_ms,
)

logger = logging.getLogger(__name__)


@dataclass
class MarketState:
    """
    Aggregated market state passed to every strategy.
    Built by the strategy engine from all upstream engine outputs.
    Strategies MUST NOT fabricate missing values — check for None.
    """
    symbol: str
    timeframe: str
    price: float  # current mid price (bid+ask)/2
    bid: float
    ask: float
    spread: float
    candles: list[CandleData] = field(default_factory=list)
    indicators: dict[str, IndicatorValue] = field(default_factory=dict)
    structure: Optional[MarketStructure] = None
    liquidity_events: list[LiquidityEvent] = field(default_factory=list)
    patterns: list[PriceActionPattern] = field(default_factory=list)
    mtf: Optional[MultiTimeframeAnalysis] = None
    regime: MarketRegime = MarketRegime.UNCERTAIN
    session: SessionType = SessionType.ASIAN
    data_quality: float = 100.0  # 0-100 scale (was 1.0, wrong scale)
    data_age_ms: int = 0  # ms since last data point
    timestamp: int = field(default_factory=now_ms)

    def get_indicator(self, name: str) -> Optional[IndicatorValue]:
        """Safe indicator lookup — returns None if missing."""
        return self.indicators.get(name)

    def get_indicator_value(self, name: str) -> Optional[float]:
        """Get raw float value of an indicator, or None."""
        iv = self.indicators.get(name)
        return iv.value if iv is not None else None

    def get_candles(self, count: int) -> list[CandleData]:
        """Get the last N candles (most recent last)."""
        return self.candles[-count:] if self.candles else []

    @property
    def candle_count(self) -> int:
        return len(self.candles)

    @property
    def has_valid_data(self) -> bool:
        return (
            self.candle_count > 0
            and self.data_quality > 0.0
            and self.price > 0
        )


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.
    
    Subclasses MUST implement:
      - name: class-level strategy name
      - weight: importance weight (0.0–1.0) for confluence scoring
      - evaluate(market_state) -> StrategyAssessment
    
    Lifecycle:
      1. __init__ receives optional config overrides
      2. evaluate() is called by the strategy engine on each cycle
      3. Returns StrategyAssessment with direction, score, confidence, evidence
    """

    name: str = "base"
    weight: float = 0.5
    # Minimum data quality required for this strategy to produce a signal
    min_data_quality: float = 30.0  # 0-100 scale (was 0.3, wrong scale)
    # Minimum number of candles needed
    min_candles: int = 2
    # Required timeframes this strategy needs indicators for
    required_indicators: list[str] = []

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self._enabled = self.config.get("enabled", True)
        self._weight_override = self.config.get("weight")
        if self._weight_override is not None:
            self.weight = float(self._weight_override)
        self._logger = logging.getLogger(f"nexus.strategy.{self.name}")

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _check_preconditions(self, state: MarketState) -> tuple[bool, str | None]:
        """
        Validate preconditions before evaluation.
        Returns (pass, reason_if_fail).
        """
        if not state.has_valid_data:
            return False, "No valid market data available"
        if state.candle_count < self.min_candles:
            return False, f"Insufficient candles: {state.candle_count} < {self.min_candles}"
        if state.data_quality < self.min_data_quality:
            return False, f"Data quality too low: {state.data_quality:.1f} < {self.min_data_quality}"
        if state.spread <= 0:
            return False, "Invalid spread"
        if state.price <= 0:
            return False, "Invalid price"
        # Check required indicators
        for ind_name in self.required_indicators:
            if ind_name not in state.indicators:
                return False, f"Missing required indicator: {ind_name}"
        return True, None

    def _make_assessment(
        self,
        direction: DecisionState,
        score: int,
        confidence: float,
        evidence: list[str],
        timeframe: str | None = None,
    ) -> StrategyAssessment:
        """Helper to build a StrategyAssessment with proper defaults."""
        clamped_score = max(0, min(100, score))
        clamped_conf = max(0.0, min(1.0, confidence))
        return StrategyAssessment(
            strategy=self.name,
            direction=direction,
            score=clamped_score,
            confidence=clamped_conf,
            evidence=evidence,
            timeframe=timeframe or "",
            timestamp=now_ms(),
        )

    def _no_signal(self, reason: str) -> StrategyAssessment:
        """Return a no-signal assessment (WAIT, score 0)."""
        return self._make_assessment(
            direction=DecisionState.WAIT,
            score=0,
            confidence=0.0,
            evidence=[f"[{self.name}] {reason}"],
        )

    @abstractmethod
    def evaluate(self, state: MarketState) -> StrategyAssessment:
        """
        Evaluate current market state and return an assessment.
        
        Args:
            state: Current aggregated market state from all engines.
        
        Returns:
            StrategyAssessment with direction (BUY/SELL/WAIT),
            score (0-100), confidence (0.0-1.0), and evidence list.
        """
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name} weight={self.weight} enabled={self._enabled}>"
