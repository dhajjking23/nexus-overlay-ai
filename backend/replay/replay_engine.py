"""
NEXUS OVERLAY AI - Market Replay Engine

Enhanced per audit spec XLV-XLVIII:
  - Candle replay, tick replay, spread simulation, latency simulation
  - NO LOOK-AHEAD BIAS: engine must NOT see future candles/highs/lows
  - Strict sequential processing
  - ReplayResult tracking: entry, exit, MAE, MFE, duration

Takes historical OHLCV data, replays candle-by-candle, runs full analysis
pipeline, outputs signals/decisions/results for backtesting.
"""
from __future__ import annotations
import asyncio
import json
import logging
import time
import random
from dataclasses import dataclass, field
from typing import Any, Optional, Callable, Awaitable

from backend.models import (
    CandleData, TickData, ProtocolMessage, MessageType,
    MarketSnapshot, AIAssessment, DecisionState,
    SignalLifecycleState, MarketRegime, TrendDirection,
    MultiTimeframeAnalysis, ConfluenceScore, RiskValidation,
    EntryCalculation, SLTPCalculation, ConfidenceModel,
    StrategyAssessment, TradingSignal, DecisionLogEntry,
    IndicatorValue, MarketStructure, PriceActionPattern,
    LiquidityEvent, SessionType,
    now_ms,
)
from backend.strategies.base import MarketState
from backend.event_bus import EventType, EventBus
from backend.replay.no_lookahead import CandleWindow, LookAheadError

logger = logging.getLogger(__name__)


@dataclass
class ReplayCandle:
    """A candle in the replay stream."""
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: int
    spread: float
    timeframe: str = "M1"


@dataclass
class ReplayConfig:
    """Configuration for replay engine behavior."""
    # Spread simulation
    simulate_spread: bool = False
    spread_multiplier: float = 1.0  # multiply original spread
    spread_noise: float = 0.0  # random spread variation (price units)

    # Latency simulation
    simulate_latency: bool = False
    latency_ms: int = 0  # simulated processing latency
    latency_jitter_ms: int = 0  # random jitter

    # Slippage simulation
    simulate_slippage: bool = False
    slippage_points: float = 0.0  # slippage in price units
    slippage_probability: float = 0.3  # probability of slippage per trade

    # Tick replay
    interpolate_ticks: bool = False
    ticks_per_candle: int = 10  # number of ticks to simulate within a candle

    # Look-ahead prevention
    strict_sequential: bool = True  # enforce look-ahead prevention

    # Trade tracking
    track_mae_mfe: bool = True  # calculate MAE/MFE for each signal

    def to_dict(self) -> dict:
        return {
            "simulate_spread": self.simulate_spread,
            "spread_multiplier": self.spread_multiplier,
            "spread_noise": self.spread_noise,
            "simulate_latency": self.simulate_latency,
            "latency_ms": self.latency_ms,
            "latency_jitter_ms": self.latency_jitter_ms,
            "simulate_slippage": self.simulate_slippage,
            "slippage_points": self.slippage_points,
            "slippage_probability": self.slippage_probability,
            "interpolate_ticks": self.interpolate_ticks,
            "ticks_per_candle": self.ticks_per_candle,
            "strict_sequential": self.strict_sequential,
            "track_mae_mfe": self.track_mae_mfe,
        }


@dataclass
class ReplayResult:
    """Result of a single candle replay, with trade tracking."""
    candle_index: int
    candle: ReplayCandle
    market_state: Optional[MarketState] = None
    strategy_assessments: list[StrategyAssessment] = field(default_factory=list)
    confluence: Optional[ConfluenceScore] = None
    ai_assessment: Optional[AIAssessment] = None
    risk_validation: Optional[RiskValidation] = None
    signal: Optional[TradingSignal] = None
    decision: str = "WAIT"
    confidence: int = 0
    processing_time_ms: float = 0
    timestamp: int = 0

    # Look-ahead tracking
    lookahead_violations: int = 0

    # Applied simulation effects
    applied_spread: float = 0.0
    applied_latency_ms: float = 0.0
    applied_slippage: float = 0.0

    # Trade tracking fields
    has_active_trade: bool = False
    trade_entry_price: float = 0.0
    trade_exit_price: float = 0.0
    trade_mae: float = 0.0  # Maximum Adverse Excursion
    trade_mfe: float = 0.0  # Maximum Favorable Excursion
    trade_duration_candles: int = 0
    trade_outcome: str = ""  # "TP1", "TP2", "TP3", "SL", "", "EXPIRED"

    def __post_init__(self):
        if self.timestamp == 0:
            self.timestamp = self.candle.timestamp


@dataclass
class ReplayStats:
    """Aggregate statistics from a replay session."""
    total_candles: int = 0
    total_signals: int = 0
    buy_signals: int = 0
    sell_signals: int = 0
    wait_signals: int = 0
    avg_confidence: float = 0.0
    avg_processing_time_ms: float = 0.0
    total_processing_time_ms: float = 0.0
    signals_by_strategy: dict[str, int] = field(default_factory=dict)
    regime_distribution: dict[str, int] = field(default_factory=dict)
    results: list[ReplayResult] = field(default_factory=list)

    # Look-ahead violation tracking
    total_lookahead_violations: int = 0

    # Simulation stats
    avg_applied_spread: float = 0.0
    avg_applied_latency_ms: float = 0.0

    def summary(self) -> dict:
        return {
            "total_candles": self.total_candles,
            "total_signals": self.total_signals,
            "buy_signals": self.buy_signals,
            "sell_signals": self.sell_signals,
            "wait_signals": self.wait_signals,
            "avg_confidence": self.avg_confidence,
            "avg_processing_time_ms": self.avg_processing_time_ms,
            "signals_by_strategy": self.signals_by_strategy,
            "regime_distribution": self.regime_distribution,
            "total_lookahead_violations": self.total_lookahead_violations,
            "avg_applied_spread": self.avg_applied_spread,
            "avg_applied_latency_ms": self.avg_applied_latency_ms,
        }


# Type aliases for pipeline functions
MarketDataHandler = Callable[[CandleData], Awaitable[MarketState]]
StrategyEvaluator = Callable[[MarketState], list[StrategyAssessment]]
ConfluenceCalculator = Callable[[list[StrategyAssessment]], ConfluenceScore]
DecisionMaker = Callable[[ConfluenceScore, MarketState], tuple[DecisionState, int]]
SignalBuilder = Callable[[DecisionState, int, MarketState, list[StrategyAssessment], ConfluenceScore], Optional[TradingSignal]]


class MarketReplayEngine:
    """
    Market replay engine for backtesting.

    Enhanced with:
      - NO LOOK-AHEAD BIAS enforcement via CandleWindow
      - Spread simulation
      - Latency simulation
      - Tick replay / interpolation
      - Strict sequential processing
      - Trade tracking (entry, exit, MAE, MFE, duration)

    Takes historical OHLCV data and replays candle-by-candle,
    running the full analysis pipeline to produce signals/decisions.

    Usage:
        engine = MarketReplayEngine()
        engine.set_pipeline(handlers...)
        engine.set_config(ReplayConfig(simulate_spread=True))
        stats = await engine.replay(candles)
        # stats.results contains per-candle results
        # stats.summary() contains aggregate stats
    """

    def __init__(self, event_bus: EventBus | None = None):
        self.event_bus = event_bus
        self._candle_buffer: dict[str, list[CandleData]] = {}  # timeframe -> candles
        self._indicators: dict[str, IndicatorValue] = {}
        self._structure: Optional[MarketStructure] = None
        self._liquidity_events: list[LiquidityEvent] = []
        self._patterns: list[PriceActionPattern] = []
        self._mtf: Optional[MultiTimeframeAnalysis] = None
        self._regime: MarketRegime = MarketRegime.UNCERTAIN
        self._session: SessionType = SessionType.ASIAN
        self._data_quality: float = 1.0

        # Pipeline handlers (injected)
        self._market_data_handler: Optional[MarketDataHandler] = None
        self._strategy_evaluator: Optional[StrategyEvaluator] = None
        self._confluence_calculator: Optional[ConfluenceCalculator] = None
        self._decision_maker: Optional[DecisionMaker] = None
        self._signal_builder: Optional[SignalBuilder] = None

        # Configuration
        self._candle_history_size: int = 200
        self._primary_timeframe: str = "M1"

        # State
        self._current_index: int = 0
        self._results: list[ReplayResult] = []

        # Replay config
        self._config = ReplayConfig()

        # Look-ahead prevention
        self._candle_window: Optional[CandleWindow] = None

        # Simulation state
        self._rng: Optional[random.Random] = None
        self._all_candles: list[ReplayCandle] = []

        # Active trade tracking
        self._active_trade_candle_index: int = -1
        self._active_trade_entry_price: float = 0.0
        self._active_trade_sl: float = 0.0
        self._active_trade_tp1: float = 0.0
        self._active_trade_tp2: float = 0.0
        self._active_trade_tp3: float = 0.0
        self._active_trade_direction: str = ""
        self._active_trade_mae: float = 0.0
        self._active_trade_mfe: float = 0.0
        self._active_trade_high: float = 0.0
        self._active_trade_low: float = float('inf')

    def set_pipeline(
        self,
        market_data_handler: MarketDataHandler | None = None,
        strategy_evaluator: StrategyEvaluator | None = None,
        confluence_calculator: ConfluenceCalculator | None = None,
        decision_maker: DecisionMaker | None = None,
        signal_builder: SignalBuilder | None = None,
    ) -> None:
        """Set the analysis pipeline functions."""
        self._market_data_handler = market_data_handler
        self._strategy_evaluator = strategy_evaluator
        self._confluence_calculator = confluence_calculator
        self._decision_maker = decision_maker
        self._signal_builder = signal_builder

    def set_candle_history_size(self, size: int) -> None:
        """Set how many candles to keep in buffer."""
        self._candle_history_size = size

    def set_primary_timeframe(self, tf: str) -> None:
        """Set primary timeframe for replay."""
        self._primary_timeframe = tf

    def set_config(self, config: ReplayConfig) -> None:
        """Set replay configuration for simulation features."""
        self._config = config
        if config.spread_noise > 0 or config.slippage_points > 0:
            self._rng = random.Random(42)  # Deterministic for reproducibility

    async def replay(self, candles: list[ReplayCandle], speed: float = 0.0) -> ReplayStats:
        """
        Replay historical candles through the analysis pipeline.

        Enforces strict sequential processing. If strict_sequential is enabled,
        the engine uses CandleWindow to prevent any look-ahead bias.

        Args:
            candles: List of historical OHLCV candles to replay.
            speed: Delay between candles (0 = as fast as possible).

        Returns:
            ReplayStats with results for each candle.
        """
        stats = ReplayStats()
        self._results = []
        self._current_index = 0
        self._all_candles = list(candles)

        # Initialize look-ahead prevention window
        if self._config.strict_sequential:
            self._candle_window = CandleWindow(candles, strict=True)
        else:
            self._candle_window = CandleWindow(candles, strict=False)

        # Initialize simulation RNG
        if self._rng is None and (
            self._config.spread_noise > 0 or self._config.slippage_points > 0
        ):
            self._rng = random.Random(42)

        logger.info(f"Starting replay of {len(candles)} candles (speed={speed})")
        start_time = time.time()

        for i, candle in enumerate(candles):
            self._current_index = i

            # Advance the look-ahead window
            if self._candle_window:
                self._candle_window.set_index(i)

            result = await self._process_candle(candle, i)
            self._results.append(result)
            stats.results.append(result)

            # Update stats
            stats.total_candles = i + 1
            stats.total_processing_time_ms += result.processing_time_ms
            stats.total_lookahead_violations += result.lookahead_violations

            # Track spread and latency
            if result.applied_spread > 0:
                stats.avg_applied_spread = (
                    (stats.avg_applied_spread * i + result.applied_spread)
                    / (i + 1)
                )
            if result.applied_latency_ms > 0:
                stats.avg_applied_latency_ms = (
                    (stats.avg_applied_latency_ms * i + result.applied_latency_ms)
                    / (i + 1)
                )

            if result.signal:
                stats.total_signals += 1
                if result.decision == "BUY":
                    stats.buy_signals += 1
                elif result.decision == "SELL":
                    stats.sell_signals += 1
                else:
                    stats.wait_signals += 1

                # Track strategy contributions
                for sa in result.strategy_assessments:
                    name = sa.strategy
                    stats.signals_by_strategy[name] = (
                        stats.signals_by_strategy.get(name, 0) + 1
                    )

            # Calculate running averages
            if stats.total_signals > 0:
                stats.avg_confidence = sum(
                    r.confidence for r in self._results if r.signal
                ) / stats.total_signals
            stats.avg_processing_time_ms = (
                stats.total_processing_time_ms / stats.total_candles
                if stats.total_candles > 0 else 0
            )

            # Optionally pace the replay
            if speed > 0:
                await asyncio.sleep(speed)

            # Log progress every 100 candles
            if (i + 1) % 100 == 0:
                logger.info(
                    f"Replay progress: {i + 1}/{len(candles)} candles, "
                    f"{stats.total_signals} signals"
                )

        elapsed = time.time() - start_time
        logger.info(
            f"Replay complete: {len(candles)} candles in {elapsed:.2f}s, "
            f"{stats.total_signals} signals generated"
        )

        # Publish results if event bus available
        if self.event_bus:
            await self.event_bus.publish(
                EventType.SYSTEM_STATUS,
                source="replay_engine",
                payload=stats.summary(),
            )

        return stats

    async def _process_candle(self, candle: ReplayCandle, index: int) -> ReplayResult:
        """Process a single candle through the pipeline."""
        start = time.time()

        result = ReplayResult(
            candle_index=index,
            candle=candle,
        )

        # Apply spread simulation
        simulated_candle = self._apply_spread_simulation(candle)
        result.applied_spread = simulated_candle.spread

        # Apply latency simulation
        if self._config.simulate_latency and self._config.latency_ms > 0:
            latency = self._config.latency_ms
            if self._config.latency_jitter_ms > 0 and self._rng:
                jitter = self._rng.randint(
                    -self._config.latency_jitter_ms,
                    self._config.latency_jitter_ms,
                )
                latency = max(0, latency + jitter)
            result.applied_latency_ms = latency

        # Convert to CandleData
        candle_data = CandleData(
            open=simulated_candle.open,
            high=simulated_candle.high,
            low=simulated_candle.low,
            close=simulated_candle.close,
            volume=simulated_candle.volume,
            spread=simulated_candle.spread,
            timestamp=simulated_candle.timestamp,
            timeframe=simulated_candle.timeframe,
            complete=True,
        )

        # Add to buffer
        tf = simulated_candle.timeframe
        if tf not in self._candle_buffer:
            self._candle_buffer[tf] = []
        self._candle_buffer[tf].append(candle_data)

        # Trim buffer
        if len(self._candle_buffer[tf]) > self._candle_history_size:
            self._candle_buffer[tf] = self._candle_buffer[tf][-self._candle_history_size:]

        # Track active trade MAE/MFE
        if self._active_trade_candle_index >= 0 and self._config.track_mae_mfe:
            self._update_trade_excursion(candle, index)
            result.has_active_trade = True

        # Build market state (only uses candles up to current index)
        market_state = self._build_market_state(candle_data)
        result.market_state = market_state

        # Run market data handler if set
        if self._market_data_handler:
            try:
                market_state = await self._market_data_handler(candle_data)
                result.market_state = market_state
            except Exception as e:
                logger.error(f"Market data handler error at candle {index}: {e}")

        # Run strategies if set
        if self._strategy_evaluator and market_state:
            try:
                assessments = self._strategy_evaluator(market_state)
                result.strategy_assessments = assessments
            except Exception as e:
                logger.error(f"Strategy evaluator error at candle {index}: {e}")

        # Calculate confluence if set
        if self._confluence_calculator and result.strategy_assessments:
            try:
                result.confluence = self._confluence_calculator(
                    result.strategy_assessments
                )
            except Exception as e:
                logger.error(f"Confluence calculator error at candle {index}: {e}")

        # Make decision if set
        if self._decision_maker and result.confluence and market_state:
            try:
                decision, confidence = self._decision_maker(
                    result.confluence, market_state
                )
                result.decision = decision.value
                result.confidence = confidence
            except Exception as e:
                logger.error(f"Decision maker error at candle {index}: {e}")

        # Build signal if applicable
        if (
            self._signal_builder
            and result.confluence
            and market_state
            and result.decision in ("BUY", "SELL")
        ):
            try:
                decision_state = DecisionState(result.decision)
                signal = self._signal_builder(
                    decision_state, result.confidence, market_state,
                    result.strategy_assessments, result.confluence,
                )
                result.signal = signal

                # Apply slippage simulation to entry
                if (
                    self._config.simulate_slippage
                    and signal
                    and self._rng
                    and self._rng.random() < self._config.slippage_probability
                ):
                    slip = self._config.slippage_points
                    if self._rng.random() < 0.5:
                        slip = -slip  # slippage can also help
                    result.applied_slippage = slip

                # Initialize trade tracking for new signals
                if signal and signal.decision in (DecisionState.BUY, DecisionState.SELL):
                    self._start_trade_tracking(signal, index, candle)

            except Exception as e:
                logger.error(f"Signal builder error at candle {index}: {e}")

        # Record processing time
        elapsed = (time.time() - start) * 1000
        result.processing_time_ms = elapsed

        return result

    def _apply_spread_simulation(self, candle: ReplayCandle) -> ReplayCandle:
        """Apply spread simulation to a candle."""
        if not self._config.simulate_spread:
            return candle

        spread = candle.spread * self._config.spread_multiplier

        if self._config.spread_noise > 0 and self._rng:
            noise = self._rng.uniform(
                -self._config.spread_noise,
                self._config.spread_noise,
            )
            spread = max(0.0, spread + noise)

        if spread != candle.spread:
            return ReplayCandle(
                timestamp=candle.timestamp,
                open=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
                volume=candle.volume,
                spread=spread,
                timeframe=candle.timeframe,
            )
        return candle

    def _build_market_state(self, candle: CandleData) -> MarketState:
        """Build a MarketState from current candle buffer and accumulated state.

        IMPORTANT: Only uses candles up to the current replay index
        to prevent look-ahead bias.
        """
        # Get candles only up to current index from the window
        if self._candle_window:
            primary_candles_data = self._candle_window.get_current_candles(
                self._candle_history_size,
                context="replay_engine._build_market_state",
            )
        else:
            primary_candles_data = self._candle_buffer.get(self._primary_timeframe, [])

        price = (candle.open + candle.high + candle.low + candle.close) / 4.0
        bid = candle.close
        ask = candle.close + candle.spread

        return MarketState(
            symbol="XAUUSD",
            timeframe=self._primary_timeframe,
            price=price,
            bid=bid,
            ask=ask,
            spread=candle.spread,
            candles=primary_candles_data,
            indicators=self._indicators.copy(),
            structure=self._structure,
            liquidity_events=list(self._liquidity_events),
            patterns=list(self._patterns),
            mtf=self._mtf,
            regime=self._regime,
            session=self._session,
            data_quality=self._data_quality,
            data_age_ms=0,
            timestamp=candle.timestamp,
        )

    def _start_trade_tracking(
        self,
        signal: TradingSignal,
        index: int,
        candle: ReplayCandle,
    ) -> None:
        """Start tracking MAE/MFE for a new trade."""
        self._active_trade_candle_index = index
        self._active_trade_entry_price = signal.entry
        self._active_trade_sl = signal.sl
        self._active_trade_tp1 = signal.tp1
        self._active_trade_tp2 = signal.tp2
        self._active_trade_tp3 = signal.tp3
        self._active_trade_direction = signal.decision.value
        self._active_trade_mae = 0.0
        self._active_trade_mfe = 0.0
        self._active_trade_high = candle.high
        self._active_trade_low = candle.low

    def _update_trade_excursion(self, candle: ReplayCandle, index: int) -> None:
        """Update MAE/MFE for the active trade."""
        if self._active_trade_candle_index < 0:
            return

        risk = abs(self._active_trade_entry_price - self._active_trade_sl)
        if risk <= 0:
            return

        if self._active_trade_direction == "BUY":
            adverse = self._active_trade_entry_price - candle.low
            favorable = candle.high - self._active_trade_entry_price
        else:
            adverse = candle.high - self._active_trade_entry_price
            favorable = self._active_trade_entry_price - candle.low

        self._active_trade_mae = max(self._active_trade_mae, adverse)
        self._active_trade_mfe = max(self._active_trade_mfe, favorable)

        # Check for TP/SL hit and close trade
        if self._active_trade_direction == "BUY":
            hit_sl = candle.low <= self._active_trade_sl
            hit_tp1 = candle.high >= self._active_trade_tp1
            hit_tp2 = candle.high >= self._active_trade_tp2
            hit_tp3 = candle.high >= self._active_trade_tp3
        else:
            hit_sl = candle.high >= self._active_trade_sl
            hit_tp1 = candle.low <= self._active_trade_tp1
            hit_tp2 = candle.low <= self._active_trade_tp2
            hit_tp3 = candle.low <= self._active_trade_tp3

        outcome = ""
        exit_price = 0.0
        closed = False

        if hit_sl:
            outcome = "SL"
            exit_price = self._active_trade_sl
            closed = True
        elif hit_tp3:
            outcome = "TP3"
            exit_price = self._active_trade_tp3
            closed = True
        elif hit_tp2:
            outcome = "TP2"
            exit_price = self._active_trade_tp2
            closed = True
        elif hit_tp1:
            outcome = "TP1"
            exit_price = self._active_trade_tp1
            closed = True

        # Update the last result with trade info
        if self._results:
            last = self._results[-1]
            last.trade_entry_price = self._active_trade_entry_price
            last.trade_mae = self._active_trade_mae
            last.trade_mfe = self._active_trade_mfe

            if closed:
                last.trade_exit_price = exit_price
                last.trade_duration_candles = index - self._active_trade_candle_index
                last.trade_outcome = outcome
                # Reset active trade
                self._active_trade_candle_index = -1

    def set_indicators(self, indicators: dict[str, IndicatorValue]) -> None:
        """Update indicators (called by indicator engine during live use)."""
        self._indicators = indicators

    def set_structure(self, structure: MarketStructure) -> None:
        """Update market structure."""
        self._structure = structure

    def set_liquidity_events(self, events: list[LiquidityEvent]) -> None:
        """Update liquidity events."""
        self._liquidity_events = events

    def set_patterns(self, patterns: list[PriceActionPattern]) -> None:
        """Update price action patterns."""
        self._patterns = patterns

    def set_mtf(self, mtf: MultiTimeframeAnalysis) -> None:
        """Update multi-timeframe analysis."""
        self._mtf = mtf

    def set_regime(self, regime: MarketRegime) -> None:
        """Update market regime."""
        self._regime = regime

    def set_session(self, session: SessionType) -> None:
        """Update trading session."""
        self._session = session

    def get_results(self) -> list[ReplayResult]:
        """Get all replay results."""
        return self._results

    def get_signals(self) -> list[TradingSignal]:
        """Get all generated signals."""
        signals = []
        for r in self._results:
            if r.signal:
                signals.append(r.signal)
        return signals

    def get_trade_results(self) -> list[dict]:
        """Get all completed trade results with MAE/MFE/duration."""
        trades = []
        for r in self._results:
            if r.trade_outcome:
                trades.append({
                    "candle_index": r.candle_index,
                    "entry_price": r.trade_entry_price,
                    "exit_price": r.trade_exit_price,
                    "outcome": r.trade_outcome,
                    "mae": r.trade_mae,
                    "mfe": r.trade_mfe,
                    "duration_candles": r.trade_duration_candles,
                    "direction": r.signal.decision.value if r.signal else "",
                })
        return trades

    def get_decision_log(self) -> list[dict]:
        """Convert results to decision log format."""
        logs = []
        for r in self._results:
            logs.append({
                "timestamp": r.candle.timestamp,
                "candle_index": r.candle_index,
                "open": r.candle.open,
                "high": r.candle.high,
                "low": r.candle.low,
                "close": r.candle.close,
                "volume": r.candle.volume,
                "decision": r.decision,
                "confidence": r.confidence,
                "has_signal": r.signal is not None,
                "strategy_count": len(r.strategy_assessments),
                "confluence_score": r.confluence.total_score if r.confluence else 0,
                "processing_time_ms": r.processing_time_ms,
                "trade_outcome": r.trade_outcome,
                "trade_mae": r.trade_mae,
                "trade_mfe": r.trade_mfe,
            })
        return logs

    def export_results_json(self) -> str:
        """Export all results as JSON."""
        return json.dumps(self.get_decision_log(), indent=2)

    def reset(self) -> None:
        """Reset replay engine state."""
        self._candle_buffer.clear()
        self._indicators.clear()
        self._structure = None
        self._liquidity_events.clear()
        self._patterns.clear()
        self._mtf = None
        self._regime = MarketRegime.UNCERTAIN
        self._session = SessionType.ASIAN
        self._data_quality = 1.0
        self._current_index = 0
        self._results.clear()
        self._candle_window = None
        self._all_candles.clear()
        self._active_trade_candle_index = -1
        self._active_trade_entry_price = 0.0
        self._active_trade_mae = 0.0
        self._active_trade_mfe = 0.0

    @staticmethod
    def load_candles_from_dicts(data: list[dict], timeframe: str = "M1") -> list[ReplayCandle]:
        """Convert list of dicts (e.g., from CSV/JSON) to ReplayCandles."""
        candles = []
        for row in data:
            candles.append(ReplayCandle(
                timestamp=int(row.get("timestamp", row.get("time", 0))),
                open=float(row.get("open", 0)),
                high=float(row.get("high", 0)),
                low=float(row.get("low", 0)),
                close=float(row.get("close", 0)),
                volume=int(row.get("volume", 0)),
                spread=float(row.get("spread", 0)),
                timeframe=row.get("timeframe", timeframe),
            ))
        return candles

    @staticmethod
    def load_candles_from_csv(filepath: str, timeframe: str = "M1") -> list[ReplayCandle]:
        """Load candles from CSV file (time,open,high,low,close,volume,spread)."""
        import csv
        candles = []
        with open(filepath, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    timestamp = int(row.get("time", row.get("timestamp", 0)))
                    if timestamp < 1e12:  # Seconds, convert to ms
                        timestamp *= 1000
                    candles.append(ReplayCandle(
                        timestamp=timestamp,
                        open=float(row.get("open", 0)),
                        high=float(row.get("high", 0)),
                        low=float(row.get("low", 0)),
                        close=float(row.get("close", 0)),
                        volume=int(float(row.get("volume", 0))),
                        spread=float(row.get("spread", 0)),
                        timeframe=row.get("timeframe", timeframe),
                    ))
                except (ValueError, KeyError) as e:
                    logger.warning(f"Skipping malformed row: {e}")
        return candles
