"""
NEXUS OVERLAY AI - Strategy Attribution

Per audit spec LIII: Each signal must track which strategy generated it,
which strategies agreed, and which strategies disagreed.

Tracks per-strategy:
  - primary_strategy (the strategy that generated the signal)
  - supporting_strategies (agreed with direction)
  - opposing_strategies (disagreed with direction)

Calculates per-strategy expectancy, drawdown, win rate, R-multiple stats.

Pure Python, no external dependencies required.
"""
from __future__ import annotations
import logging
import statistics
from dataclasses import dataclass, field
from typing import Any, Optional

from backend.analytics.performance import TradeRecord, TradeOutcome

logger = logging.getLogger(__name__)


@dataclass
class StrategyContribution:
    """Record of a single strategy's contribution to a signal."""
    strategy_name: str
    role: str  # "primary", "supporting", "opposing", "neutral"
    score: int  # 0-100
    confidence: float  # 0.0-1.0
    direction: str  # "BUY", "SELL", "WAIT"
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "role": self.role,
            "score": self.score,
            "confidence": self.confidence,
            "direction": self.direction,
            "evidence": self.evidence,
        }


@dataclass
class SignalAttribution:
    """Strategy attribution for a single signal/trade."""
    signal_id: str
    primary_strategy: str
    supporting_strategies: list[str] = field(default_factory=list)
    opposing_strategies: list[str] = field(default_factory=list)
    neutral_strategies: list[str] = field(default_factory=list)
    contributions: list[StrategyContribution] = field(default_factory=list)
    trade: Optional[TradeRecord] = None

    def to_dict(self) -> dict:
        return {
            "signal_id": self.signal_id,
            "primary_strategy": self.primary_strategy,
            "supporting_strategies": self.supporting_strategies,
            "opposing_strategies": self.opposing_strategies,
            "neutral_strategies": self.neutral_strategies,
            "contributions": [c.to_dict() for c in self.contributions],
            "trade_outcome": self.trade.outcome.value if self.trade else None,
            "r_multiple": self.trade.r_multiple if self.trade else None,
        }


@dataclass
class StrategyMetrics:
    """Aggregated metrics for a single strategy."""
    strategy_name: str
    total_signals: int = 0
    primary_count: int = 0  # times it was the primary strategy
    supporting_count: int = 0
    opposing_count: int = 0
    neutral_count: int = 0

    # Performance (when primary)
    primary_wins: int = 0
    primary_losses: int = 0
    primary_win_rate: float = 0.0
    primary_avg_r: float = 0.0
    primary_expectancy: float = 0.0
    primary_profit_factor: float = 0.0

    # Performance (all roles)
    total_wins: int = 0
    total_losses: int = 0
    total_win_rate: float = 0.0
    total_avg_r: float = 0.0
    total_expectancy: float = 0.0
    total_profit_factor: float = 0.0

    # Drawdown
    max_drawdown: float = 0.0
    max_drawdown_r: float = 0.0

    # Average score when it participated
    avg_score: float = 0.0
    avg_confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "total_signals": self.total_signals,
            "primary_count": self.primary_count,
            "supporting_count": self.supporting_count,
            "opposing_count": self.opposing_count,
            "neutral_count": self.neutral_count,
            "primary_wins": self.primary_wins,
            "primary_losses": self.primary_losses,
            "primary_win_rate": self.primary_win_rate,
            "primary_avg_r": self.primary_avg_r,
            "primary_expectancy": self.primary_expectancy,
            "primary_profit_factor": self.primary_profit_factor,
            "total_wins": self.total_wins,
            "total_losses": self.total_losses,
            "total_win_rate": self.total_win_rate,
            "total_avg_r": self.total_avg_r,
            "total_expectancy": self.total_expectancy,
            "total_profit_factor": self.total_profit_factor,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_r": self.max_drawdown_r,
            "avg_score": self.avg_score,
            "avg_confidence": self.avg_confidence,
        }


class StrategyAttribution:
    """
    Track and calculate strategy attribution for every signal.

    For each signal, classifies strategies as:
      - primary: the strategy that generated the signal
      - supporting: agreed with the signal direction
      - opposing: disagreed with the signal direction
      - neutral: did not participate

    Calculates per-strategy:
      - expectancy, win rate, drawdown
      - frequency as primary, supporting, opposing

    Usage:
        attribution = StrategyAttribution()
        # For each signal:
        attr = attribution.classify_signal(
            signal_id="SIG-001",
            strategy_assessments=[...],
            signal_direction="BUY",
        )
        attribution.record_trade(attr, trade_record)
        # After all signals:
        metrics = attribution.calculate_all()
    """

    def __init__(self):
        self._attributions: list[SignalAttribution] = []
        self._strategy_metrics: dict[str, StrategyMetrics] = {}

    def classify_signal(
        self,
        signal_id: str,
        strategy_assessments: list[Any],
        signal_direction: str,
    ) -> SignalAttribution:
        """
        Classify strategies for a signal based on their assessments.

        Args:
            signal_id: Unique signal identifier.
            strategy_assessments: List of StrategyAssessment objects.
            signal_direction: "BUY" or "SELL" (the final signal direction).

        Returns:
            SignalAttribution with classified roles.
        """
        primary = ""
        supporting: list[str] = []
        opposing: list[str] = []
        neutral: list[str] = []
        contributions: list[StrategyContribution] = []

        if not strategy_assessments:
            attr = SignalAttribution(
                signal_id=signal_id,
                primary_strategy="NONE",
                supporting_strategies=[],
                opposing_strategies=[],
                neutral_strategies=[],
                contributions=[],
            )
            self._attributions.append(attr)
            return attr

        # Find the strategy with highest score in the signal direction
        best_score = -1
        best_strategy = ""

        for sa in strategy_assessments:
            direction = ""
            if hasattr(sa, 'direction'):
                d = sa.direction
                if hasattr(d, 'value'):
                    direction = d.value
                else:
                    direction = str(d)

            score = sa.score if hasattr(sa, 'score') else 0
            conf = sa.confidence if hasattr(sa, 'confidence') else 0.0
            evidence = sa.evidence if hasattr(sa, 'evidence') else []
            name = sa.strategy if hasattr(sa, 'strategy') else "unknown"

            if direction == signal_direction and score > best_score:
                best_score = score
                best_strategy = name

        for sa in strategy_assessments:
            direction = ""
            if hasattr(sa, 'direction'):
                d = sa.direction
                if hasattr(d, 'value'):
                    direction = d.value
                else:
                    direction = str(d)

            score = sa.score if hasattr(sa, 'score') else 0
            conf = sa.confidence if hasattr(sa, 'confidence') else 0.0
            evidence = sa.evidence if hasattr(sa, 'evidence') else []
            name = sa.strategy if hasattr(sa, 'strategy') else "unknown"

            # Classify role
            if name == best_strategy:
                role = "primary"
                primary = name
            elif direction == signal_direction and score > 0:
                role = "supporting"
                supporting.append(name)
            elif direction != signal_direction and direction != "WAIT" and score > 0:
                role = "opposing"
                opposing.append(name)
            else:
                role = "neutral"
                neutral.append(name)

            contributions.append(StrategyContribution(
                strategy_name=name,
                role=role,
                score=score,
                confidence=conf,
                direction=direction,
                evidence=list(evidence) if isinstance(evidence, list) else [],
            ))

        attr = SignalAttribution(
            signal_id=signal_id,
            primary_strategy=primary or "NONE",
            supporting_strategies=supporting,
            opposing_strategies=opposing,
            neutral_strategies=neutral,
            contributions=contributions,
        )
        self._attributions.append(attr)
        return attr

    def record_trade(
        self,
        attribution: SignalAttribution,
        trade: TradeRecord,
    ) -> None:
        """Link a trade record to an attribution."""
        attribution.trade = trade
        trade.primary_strategy = attribution.primary_strategy
        trade.supporting_strategies = list(attribution.supporting_strategies)
        trade.opposing_strategies = list(attribution.opposing_strategies)

    def calculate_all(self) -> dict[str, StrategyMetrics]:
        """
        Calculate per-strategy metrics across all attributed signals.

        Returns:
            Dict mapping strategy name to StrategyMetrics.
        """
        # Aggregate contributions per strategy
        strategy_data: dict[str, dict[str, Any]] = {}

        for attr in self._attributions:
            for contrib in attr.contributions:
                name = contrib.strategy_name
                if name not in strategy_data:
                    strategy_data[name] = {
                        "scores": [],
                        "confidences": [],
                        "r_multiples": [],
                        "primary_r_multiples": [],
                        "is_primary_wins": 0,
                        "is_primary_losses": 0,
                        "total_wins": 0,
                        "total_losses": 0,
                    }

                d = strategy_data[name]
                d["scores"].append(contrib.score)
                d["confidences"].append(contrib.confidence)

                if attr.trade is not None:
                    r = attr.trade.r_multiple
                    d["r_multiples"].append(r)

                    is_win = attr.trade.is_win
                    is_loss = attr.trade.is_loss

                    if is_win:
                        d["total_wins"] += 1
                    if is_loss:
                        d["total_losses"] += 1

                    if contrib.role == "primary":
                        d["primary_r_multiples"].append(r)
                        if is_win:
                            d["is_primary_wins"] += 1
                        if is_loss:
                            d["is_primary_losses"] += 1

        # Build StrategyMetrics
        results: dict[str, StrategyMetrics] = {}
        for name, d in strategy_data.items():
            sm = StrategyMetrics(strategy_name=name)

            # Count roles
            sm.total_signals = sum(
                1 for attr in self._attributions
                for c in attr.contributions
                if c.strategy_name == name
            )
            sm.primary_count = sum(
                1 for attr in self._attributions
                for c in attr.contributions
                if c.strategy_name == name and c.role == "primary"
            )
            sm.supporting_count = sum(
                1 for attr in self._attributions
                for c in attr.contributions
                if c.strategy_name == name and c.role == "supporting"
            )
            sm.opposing_count = sum(
                1 for attr in self._attributions
                for c in attr.contributions
                if c.strategy_name == name and c.role == "opposing"
            )
            sm.neutral_count = sum(
                1 for attr in self._attributions
                for c in attr.contributions
                if c.strategy_name == name and c.role == "neutral"
            )

            # Primary performance
            sm.primary_wins = d["is_primary_wins"]
            sm.primary_losses = d["is_primary_losses"]
            primary_total = sm.primary_wins + sm.primary_losses
            if primary_total > 0:
                sm.primary_win_rate = sm.primary_wins / primary_total

            primary_r = d["primary_r_multiples"]
            if primary_r:
                sm.primary_avg_r = statistics.mean(primary_r)
                # Expectancy: win_rate * avg_win + loss_rate * avg_loss
                win_r = [r for r in primary_r if r > 0]
                loss_r = [r for r in primary_r if r < 0]
                wr = len(win_r) / len(primary_r) if primary_r else 0.0
                lr = len(loss_r) / len(primary_r) if primary_r else 0.0
                avg_w = statistics.mean(win_r) if win_r else 0.0
                avg_l = statistics.mean(loss_r) if loss_r else 0.0
                sm.primary_expectancy = wr * avg_w + lr * avg_l

                gross_profit = sum(r for r in primary_r if r > 0)
                gross_loss = abs(sum(r for r in primary_r if r < 0))
                if gross_loss > 0:
                    sm.primary_profit_factor = gross_profit / gross_loss
                elif gross_profit > 0:
                    sm.primary_profit_factor = float('inf')

            # Total performance (all roles)
            sm.total_wins = d["total_wins"]
            sm.total_losses = d["total_losses"]
            total_wl = sm.total_wins + sm.total_losses
            if total_wl > 0:
                sm.total_win_rate = sm.total_wins / total_wl

            all_r = d["r_multiples"]
            if all_r:
                sm.total_avg_r = statistics.mean(all_r)
                win_r = [r for r in all_r if r > 0]
                loss_r = [r for r in all_r if r < 0]
                wr = len(win_r) / len(all_r) if all_r else 0.0
                lr = len(loss_r) / len(all_r) if all_r else 0.0
                avg_w = statistics.mean(win_r) if win_r else 0.0
                avg_l = statistics.mean(loss_r) if loss_r else 0.0
                sm.total_expectancy = wr * avg_w + lr * avg_l

                gross_profit = sum(r for r in all_r if r > 0)
                gross_loss = abs(sum(r for r in all_r if r < 0))
                if gross_loss > 0:
                    sm.total_profit_factor = gross_profit / gross_loss
                elif gross_profit > 0:
                    sm.total_profit_factor = float('inf')

                # Drawdown for this strategy
                peak = 0.0
                max_dd = 0.0
                peak_r = 0.0
                max_dd_r = 0.0
                cumulative = 0.0
                for r in all_r:
                    cumulative += r
                    if cumulative > peak:
                        peak = cumulative
                    dd = peak - cumulative
                    if dd > max_dd:
                        max_dd = dd
                    if cumulative > peak_r:
                        peak_r = cumulative
                    dd_r = peak_r - cumulative
                    if dd_r > max_dd_r:
                        max_dd_r = dd_r
                sm.max_drawdown = max_dd
                sm.max_drawdown_r = max_dd_r

            # Average scores
            if d["scores"]:
                sm.avg_score = statistics.mean(d["scores"])
            if d["confidences"]:
                sm.avg_confidence = statistics.mean(d["confidences"])

            results[name] = sm

        self._strategy_metrics = results
        return results

    def get_strategy_ranking(self, metric: str = "primary_expectancy") -> list[tuple[str, float]]:
        """
        Rank strategies by a given metric.

        Args:
            metric: StrategyMetrics field name to rank by.

        Returns:
            List of (strategy_name, metric_value) sorted descending.
        """
        if not self._strategy_metrics:
            self.calculate_all()

        pairs = []
        for name, sm in self._strategy_metrics.items():
            value = getattr(sm, metric, 0.0)
            if value == float('inf'):
                value = 999999.0
            pairs.append((name, value))

        pairs.sort(key=lambda x: x[1], reverse=True)
        return pairs

    def get_attributions(self) -> list[SignalAttribution]:
        """Get all signal attributions."""
        return list(self._attributions)

    def get_summary(self) -> dict:
        """Get a summary of all strategy attributions."""
        if not self._strategy_metrics:
            self.calculate_all()

        return {
            "total_signals": len(self._attributions),
            "strategies": {
                name: sm.to_dict()
                for name, sm in self._strategy_metrics.items()
            },
            "ranking_by_expectancy": [
                {"strategy": name, "expectancy": val}
                for name, val in self.get_strategy_ranking("primary_expectancy")
            ],
        }

    def reset(self) -> None:
        """Clear all attributions."""
        self._attributions.clear()
        self._strategy_metrics.clear()
