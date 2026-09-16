# Replay and backtesting engine

from backend.replay.replay_engine import (
    MarketReplayEngine,
    ReplayCandle,
    ReplayResult,
    ReplayStats,
    ReplayConfig,
    MarketDataHandler,
    StrategyEvaluator,
    ConfluenceCalculator,
    DecisionMaker,
    SignalBuilder,
)
from backend.replay.backtester import (
    Backtester,
    BacktestResult,
    WalkForwardResult,
    TradeSetup,
    TradeOutcome_,
)
from backend.replay.monte_carlo import (
    MonteCarloSimulator,
    SimulationConfig,
    SimulationResult,
    MonteCarloReport,
)
from backend.replay.no_lookahead import (
    LookAheadDetector,
    CandleWindow,
    LookAheadError,
    LookAheadViolation,
    LookAheadReport,
    no_lookahead,
    requires_candle_window,
    create_safe_candle_accessor,
)

__all__ = [
    # replay_engine
    "MarketReplayEngine",
    "ReplayCandle",
    "ReplayResult",
    "ReplayStats",
    "ReplayConfig",
    "MarketDataHandler",
    "StrategyEvaluator",
    "ConfluenceCalculator",
    "DecisionMaker",
    "SignalBuilder",
    # backtester
    "Backtester",
    "BacktestResult",
    "WalkForwardResult",
    "TradeSetup",
    "TradeOutcome_",
    # monte_carlo
    "MonteCarloSimulator",
    "SimulationConfig",
    "SimulationResult",
    "MonteCarloReport",
    # no_lookahead
    "LookAheadDetector",
    "CandleWindow",
    "LookAheadError",
    "LookAheadViolation",
    "LookAheadReport",
    "no_lookahead",
    "requires_candle_window",
    "create_safe_candle_accessor",
]