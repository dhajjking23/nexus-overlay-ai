"""
NEXUS OVERLAY AI - Trading Strategies Package
All available strategies for the strategy engine.
"""
from __future__ import annotations
from typing import Type

from backend.strategies.base import BaseStrategy, MarketState
from backend.strategies.trend_following import TrendFollowingStrategy
from backend.strategies.pullback import PullbackStrategy
from backend.strategies.breakout import BreakoutStrategy
from backend.strategies.liquidity_sweep import LiquiditySweepStrategy
from backend.strategies.mean_reversion import MeanReversionStrategy
from backend.strategies.scalping import ScalpingStrategy


# Registry of all strategies for dynamic instantiation
STRATEGY_REGISTRY: dict[str, Type[BaseStrategy]] = {
    "trend_following": TrendFollowingStrategy,
    "pullback": PullbackStrategy,
    "breakout": BreakoutStrategy,
    "liquidity_sweep": LiquiditySweepStrategy,
    "mean_reversion": MeanReversionStrategy,
    "scalping": ScalpingStrategy,
}


def get_all_strategy_classes() -> dict[str, Type[BaseStrategy]]:
    """Get all registered strategy classes."""
    return STRATEGY_REGISTRY.copy()


def create_strategy(name: str, config: dict | None = None) -> BaseStrategy:
    """Factory: instantiate a strategy by name."""
    cls = STRATEGY_REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown strategy: {name}. Available: {list(STRATEGY_REGISTRY.keys())}")
    return cls(config=config)


__all__ = [
    "BaseStrategy",
    "MarketState",
    "TrendFollowingStrategy",
    "PullbackStrategy",
    "BreakoutStrategy",
    "LiquiditySweepStrategy",
    "MeanReversionStrategy",
    "ScalpingStrategy",
    "STRATEGY_REGISTRY",
    "get_all_strategy_classes",
    "create_strategy",
]
