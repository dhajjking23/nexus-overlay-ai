"""
NEXUS OVERLAY AI - Strategy Engine
Manages all strategies, collects assessments, applies per-strategy weights.
Returns list of StrategyAssessment.
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

from backend.strategies.base import BaseStrategy, MarketState
from backend.strategies import STRATEGY_REGISTRY, create_strategy
from backend.models import (
    DecisionState,
    StrategyAssessment,
    ConfluenceScore,
    now_ms,
)
from backend.event_bus import EventType, get_event_bus

logger = logging.getLogger(__name__)


class StrategyEngine:
    """
    Manages all trading strategies and produces weighted assessments.
    
    Lifecycle:
      1. Initialize with config, load all strategies
      2. On each cycle, receive MarketState, run all enabled strategies
      3. Collect StrategyAssessment list
      4. Optionally publish STRATEGY_ASSESSMENT events
      5. Provide aggregated confluence scoring
    
    Thread safety: all methods are async-safe (single event loop).
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self._strategies: dict[str, BaseStrategy] = {}
        self._last_assessments: list[StrategyAssessment] = []
        self._running = False
        self._cycle_count = 0
        self._logger = logging.getLogger("nexus.engine.strategy")
        self._initialize_strategies()

    def _initialize_strategies(self) -> None:
        """Load strategies from registry, applying enabled list and weights from YAML.

        YAML config structure:
            strategies:
              enabled: [trend_following, pullback, ...]
              weights:
                trend_following: 15
                pullback: 15
        """
        strategy_configs = self.config.get("strategies", {})
        enabled_list = strategy_configs.get("enabled", [])
        weights_map = strategy_configs.get("weights", {})
        use_enabled_filter = bool(enabled_list)

        for name, cls in STRATEGY_REGISTRY.items():
            # Determine if this strategy is enabled
            strategy_enabled = name in enabled_list if use_enabled_filter else True

            # Build per-strategy config: apply weight from YAML
            weight_val = weights_map.get(name, None)
            cfg = {"enabled": strategy_enabled}
            if weight_val is not None:
                cfg["weight"] = weight_val

            # Also merge any strategy-specific config dict if present
            strategy_specific = strategy_configs.get(name, {})
            if isinstance(strategy_specific, dict):
                cfg.update(strategy_specific)

            try:
                strategy = cls(config=cfg)
                self._strategies[name] = strategy
                self._logger.info(
                    f"Loaded strategy: {name} "
                    f"(weight={strategy.weight}, enabled={strategy.enabled})"
                )
            except Exception as e:
                self._logger.error(f"Failed to load strategy {name}: {e}")

    @property
    def strategy_names(self) -> list[str]:
        return list(self._strategies.keys())

    @property
    def enabled_strategies(self) -> list[BaseStrategy]:
        return [s for s in self._strategies.values() if s.enabled]

    @property
    def last_assessments(self) -> list[StrategyAssessment]:
        return self._last_assessments

    async def start(self) -> None:
        """Start the strategy engine."""
        if self._running:
            return
        self._running = True
        enabled = self.enabled_strategies
        self._logger.info(
            f"Strategy engine started: {len(enabled)}/{len(self._strategies)} strategies active "
            f"({[s.name for s in enabled]})"
        )

    async def stop(self) -> None:
        """Stop the strategy engine."""
        self._running = False
        self._logger.info("Strategy engine stopped")

    async def evaluate(self, market_state: MarketState) -> list[StrategyAssessment]:
        """
        Run all enabled strategies against the market state.
        
        Args:
            market_state: Current aggregated market state.
        
        Returns:
            List of StrategyAssessment from all strategies.
        """
        self._cycle_count += 1
        assessments: list[StrategyAssessment] = []

        enabled = self.enabled_strategies
        if not enabled:
            self._logger.warning("No enabled strategies")
            return assessments

        # Run each strategy (they're sync, but we wrap for future-proofing)
        for strategy in enabled:
            try:
                assessment = strategy.evaluate(market_state)
                # Override timeframe if not set
                if not assessment.timeframe:
                    assessment.timeframe = market_state.timeframe
                assessments.append(assessment)
            except Exception as e:
                self._logger.error(
                    f"Strategy {strategy.name} evaluation error: {e}",
                    exc_info=True,
                )
                # Produce a zero-score WAIT assessment on error
                assessments.append(StrategyAssessment(
                    strategy=strategy.name,
                    direction=DecisionState.WAIT,
                    score=0,
                    confidence=0.0,
                    evidence=[f"[{strategy.name}] Evaluation error: {str(e)}"],
                    timeframe=market_state.timeframe,
                    timestamp=now_ms(),
                ))

        self._last_assessments = assessments

        # Publish strategy assessments to event bus
        try:
            bus = get_event_bus()
            for assessment in assessments:
                if assessment.direction != DecisionState.WAIT:
                    await bus.publish(
                        event_type=EventType.STRATEGY_ASSESSMENT,
                        source=f"strategy_engine.{assessment.strategy}",
                        payload={
                            "strategy": assessment.strategy,
                            "direction": assessment.direction.value,
                            "score": assessment.score,
                            "confidence": assessment.confidence,
                            "evidence_count": len(assessment.evidence),
                        },
                    )
        except Exception as e:
            self._logger.error(f"Failed to publish strategy assessments: {e}")

        return assessments

    def compute_weighted_score(
        self, assessments: list[StrategyAssessment]
    ) -> dict[str, Any]:
        """
        Compute weighted confluence scores from strategy assessments.
        
        Returns dict with:
          - total_score: float (weighted average)
          - direction: DecisionState (majority weighted vote)
          - strategy_scores: dict[str, float] (individual weighted scores)
          - agreement_ratio: float (0.0-1.0, how much strategies agree)
          - weighted_evidence: list[str] (top evidence items)
        """
        if not assessments:
            return {
                "total_score": 0.0,
                "direction": DecisionState.WAIT,
                "strategy_scores": {},
                "agreement_ratio": 0.0,
                "weighted_evidence": [],
            }

        strategy_scores: dict[str, float] = {}
        buy_weighted = 0.0
        sell_weighted = 0.0
        total_weight = 0.0
        all_evidence: list[tuple[float, str]] = []  # (priority, text)
        directions_seen: dict[DecisionState, float] = {}

        for assessment in assessments:
            strategy = self._strategies.get(assessment.strategy)
            if strategy is None:
                continue

            weight = strategy.weight
            weighted_score = (assessment.score / 100.0) * weight
            strategy_scores[assessment.strategy] = weighted_score
            total_weight += weight

            # Track direction votes weighted by confidence and strategy weight
            vote_weight = weight * assessment.confidence
            if assessment.direction == DecisionState.BUY:
                buy_weighted += vote_weight
                directions_seen[DecisionState.BUY] = directions_seen.get(DecisionState.BUY, 0) + vote_weight
            elif assessment.direction == DecisionState.SELL:
                sell_weighted += vote_weight
                directions_seen[DecisionState.SELL] = directions_seen.get(DecisionState.SELL, 0) + vote_weight

            # Collect evidence
            for ev in assessment.evidence:
                priority = assessment.score * assessment.confidence
                all_evidence.append((priority, ev))

        # Total weighted score
        total_score = sum(strategy_scores.values()) / max(total_weight, 0.001) * 100

        # Direction from weighted vote
        if buy_weighted > sell_weighted:
            direction = DecisionState.BUY
        elif sell_weighted > buy_weighted:
            direction = DecisionState.SELL
        else:
            direction = DecisionState.WAIT

        # Agreement ratio: what fraction of non-WAIT strategies agree with majority
        non_wait = [a for a in assessments if a.direction != DecisionState.WAIT]
        if non_wait:
            majority_count = sum(
                1 for a in non_wait if a.direction == direction
            )
            agreement = majority_count / len(non_wait)
        else:
            agreement = 0.0

        # Top evidence (by priority)
        all_evidence.sort(key=lambda x: x[0], reverse=True)
        weighted_evidence = [text for _, text in all_evidence[:10]]

        return {
            "total_score": round(total_score, 2),
            "direction": direction,
            "strategy_scores": strategy_scores,
            "agreement_ratio": round(agreement, 3),
            "weighted_evidence": weighted_evidence,
        }

    def get_strategy_info(self) -> list[dict[str, Any]]:
        """Get info about all strategies for diagnostics."""
        return [
            {
                "name": s.name,
                "weight": s.weight,
                "enabled": s.enabled,
                "min_data_quality": s.min_data_quality,
                "min_candles": s.min_candles,
                "required_indicators": s.required_indicators,
                "class": s.__class__.__name__,
            }
            for s in self._strategies.values()
        ]

    def get_stats(self) -> dict[str, Any]:
        """Get engine statistics."""
        return {
            "cycle_count": self._cycle_count,
            "running": self._running,
            "total_strategies": len(self._strategies),
            "enabled_strategies": len(self.enabled_strategies),
            "last_assessment_count": len(self._last_assessments),
            "strategies": {
                s.name: {"weight": s.weight, "enabled": s.enabled}
                for s in self._strategies.values()
            },
        }