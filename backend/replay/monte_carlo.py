"""
NEXUS OVERLAY AI - Monte Carlo Simulator

Per audit spec LV (RESEARCH MODE):
  Replay, Backtest, Optimization, Monte Carlo, Parameter comparison.

Takes trade results and simulates thousands of randomized orderings
to produce robustness statistics. Varies slippage, spread, and
execution delay to stress-test strategy performance.

Outputs:
  - drawdown_distribution
  - loss_streak_distribution
  - return_distribution
  - robustness_score (composite 0-100)

Pure Python, no external ML libraries required.
"""
from __future__ import annotations
import logging
import random
import statistics
from dataclasses import dataclass, field
from typing import Any, Optional

from backend.analytics.performance import TradeRecord, TradeOutcome

logger = logging.getLogger(__name__)


@dataclass
class SimulationConfig:
    """Configuration for Monte Carlo simulation."""
    num_simulations: int = 1000
    initial_capital: float = 10000.0
    slippage_points: float = 0.0  # additional slippage in price units
    spread_multiplier: float = 1.0  # multiply original spread
    execution_delay_ms: int = 0  # simulated execution delay
    risk_per_trade_pct: float = 1.0  # risk as % of capital per trade
    max_drawdown_limit_pct: float = 20.0  # max acceptable drawdown %
    random_seed: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "num_simulations": self.num_simulations,
            "initial_capital": self.initial_capital,
            "slippage_points": self.slippage_points,
            "spread_multiplier": self.spread_multiplier,
            "execution_delay_ms": self.execution_delay_ms,
            "risk_per_trade_pct": self.risk_per_trade_pct,
            "max_drawdown_limit_pct": self.max_drawdown_limit_pct,
            "random_seed": self.random_seed,
        }


@dataclass
class SimulationResult:
    """Result of a single Monte Carlo simulation run."""
    run_id: int
    final_equity: float
    total_return_pct: float
    max_drawdown: float
    max_drawdown_pct: float
    max_drawdown_duration: int  # number of trades in drawdown
    max_loss_streak: int
    equity_curve: list[float]
    trade_returns: list[float]
    num_trades: int

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "final_equity": self.final_equity,
            "total_return_pct": self.total_return_pct,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_pct": self.max_drawdown_pct,
            "max_drawdown_duration": self.max_drawdown_duration,
            "max_loss_streak": self.max_loss_streak,
            "num_trades": self.num_trades,
        }


@dataclass
class MonteCarloReport:
    """Aggregated results from Monte Carlo simulation."""
    # Configuration
    num_simulations: int = 0
    config: Optional[SimulationConfig] = None

    # Return distribution
    avg_return_pct: float = 0.0
    median_return_pct: float = 0.0
    return_std: float = 0.0
    min_return_pct: float = 0.0
    max_return_pct: float = 0.0
    return_percentiles: dict[str, float] = field(default_factory=dict)

    # Drawdown distribution
    avg_max_drawdown: float = 0.0
    median_max_drawdown: float = 0.0
    drawdown_std: float = 0.0
    max_drawdown_across_sims: float = 0.0
    drawdown_percentiles: dict[str, float] = field(default_factory=dict)

    # Loss streak distribution
    avg_max_loss_streak: float = 0.0
    median_max_loss_streak: float = 0.0
    loss_streak_percentiles: dict[str, float] = field(default_factory=dict)

    # Drawdown duration
    avg_max_dd_duration: float = 0.0
    median_max_dd_duration: float = 0.0

    # Robustness
    robustness_score: float = 0.0  # 0-100
    probability_of_profit: float = 0.0
    probability_of_ruin: float = 0.0  # probability of exceeding drawdown limit
    avg_final_equity: float = 0.0
    median_final_equity: float = 0.0

    # Raw simulation results
    simulations: list[SimulationResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "num_simulations": self.num_simulations,
            "avg_return_pct": self.avg_return_pct,
            "median_return_pct": self.median_return_pct,
            "return_std": self.return_std,
            "min_return_pct": self.min_return_pct,
            "max_return_pct": self.max_return_pct,
            "return_percentiles": self.return_percentiles,
            "avg_max_drawdown": self.avg_max_drawdown,
            "median_max_drawdown": self.median_max_drawdown,
            "drawdown_std": self.drawdown_std,
            "max_drawdown_across_sims": self.max_drawdown_across_sims,
            "drawdown_percentiles": self.drawdown_percentiles,
            "avg_max_loss_streak": self.avg_max_loss_streak,
            "median_max_loss_streak": self.median_max_loss_streak,
            "loss_streak_percentiles": self.loss_streak_percentiles,
            "avg_max_dd_duration": self.avg_max_dd_duration,
            "median_max_dd_duration": self.median_max_dd_duration,
            "robustness_score": self.robustness_score,
            "probability_of_profit": self.probability_of_profit,
            "probability_of_ruin": self.probability_of_ruin,
            "avg_final_equity": self.avg_final_equity,
            "median_final_equity": self.median_final_equity,
        }


def _percentile(sorted_values: list, pct: float) -> float:
    """Calculate the value at a given percentile from a sorted list."""
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * (pct / 100.0)
    f = int(k)
    c = f + 1
    if c >= len(sorted_values):
        return sorted_values[-1]
    d = k - f
    return sorted_values[f] + d * (sorted_values[c] - sorted_values[f])


class MonteCarloSimulator:
    """
    Monte Carlo simulator for stress-testing trading strategies.

    Takes a list of TradeRecords and simulates many random orderings,
    adding slippage, spread, and execution delay variations to produce
    a distribution of possible outcomes.

    Usage:
        simulator = MonteCarloSimulator()
        config = SimulationConfig(num_simulations=5000)
        report = simulator.simulate(trades, config)
        print(f"Robustness: {report.robustness_score}")
        print(f"Probability of ruin: {report.probability_of_ruin}")
    """

    def __init__(self):
        self._last_report: Optional[MonteCarloReport] = None

    def simulate(
        self,
        trades: list[TradeRecord],
        config: Optional[SimulationConfig] = None,
    ) -> MonteCarloReport:
        """
        Run Monte Carlo simulation on trade results.

        Args:
            trades: List of completed trade records with R-multiples.
            config: Simulation configuration. Uses defaults if None.

        Returns:
            MonteCarloReport with all distribution statistics.
        """
        if config is None:
            config = SimulationConfig()

        if not trades:
            logger.warning("No trades provided for Monte Carlo simulation")
            return MonteCarloReport(
                num_simulations=0, config=config, robustness_score=0.0,
            )

        rng = random.Random(config.random_seed)

        # Extract R-multiples from trades
        base_r_values = [t.r_multiple for t in trades]
        num_trades = len(base_r_values)

        sim_results: list[SimulationResult] = []

        for sim_id in range(config.num_simulations):
            # Shuffle trade order for this simulation
            shuffled_r = list(base_r_values)
            rng.shuffle(shuffled_r)

            # Apply slippage and spread variations
            adjusted_r = []
            for r in shuffled_r:
                adj_r = self._apply_market_conditions(
                    r, trades[0] if trades else None, config, rng
                )
                adjusted_r.append(adj_r)

            # Run equity simulation
            result = self._simulate_equity(
                run_id=sim_id,
                r_values=adjusted_r,
                config=config,
            )
            sim_results.append(result)

        # Aggregate results
        report = self._aggregate_results(sim_results, config)
        self._last_report = report
        return report

    def simulate_with_parameter_variations(
        self,
        trades: list[TradeRecord],
        parameter_sets: list[SimulationConfig],
    ) -> dict[str, MonteCarloReport]:
        """
        Run Monte Carlo with multiple parameter sets for comparison.

        Args:
            trades: Trade records.
            parameter_sets: List of configs to test.

        Returns:
            Dict mapping config description to MonteCarloReport.
        """
        results: dict[str, MonteCarloReport] = {}
        for i, config in enumerate(parameter_sets):
            label = f"config_{i}"
            if config.random_seed is not None:
                label = f"seed_{config.random_seed}"
            if config.slippage_points != 0:
                label += f"_slip{config.slippage_points}"
            if config.spread_multiplier != 1.0:
                label += f"_spread{config.spread_multiplier}"
            results[label] = self.simulate(trades, config)
        return results

    def _apply_market_conditions(
        self,
        r_multiple: float,
        trade: Optional[TradeRecord],
        config: SimulationConfig,
        rng: random.Random,
    ) -> float:
        """Apply slippage, spread, and delay variations to R-multiple."""
        adjusted = r_multiple

        # Apply slippage (randomly positive or negative)
        if config.slippage_points != 0 and trade is not None:
            risk = trade.risk_distance
            if risk > 0:
                # Slippage reduces R proportionally
                slip_r: float = config.slippage_points / risk
                # Random direction: slippage can help or hurt
                if rng.random() < 0.7:  # 70% chance slippage hurts
                    adjusted -= abs(slip_r)
                else:
                    adjusted += abs(slip_r) * 0.3  # 30% chance small help

        # Apply spread variation
        if config.spread_multiplier != 1.0 and trade is not None:
            # Approximate spread impact as fraction of risk
            # Use a default spread estimate if not available
            if trade.risk_distance > 0:
                # Spread adjustment: extra spread cost reduces R
                spread_penalty = (config.spread_multiplier - 1.0) * 0.02
                adjusted -= spread_penalty

        return adjusted

    def _simulate_equity(
        self,
        run_id: int,
        r_values: list[float],
        config: SimulationConfig,
    ) -> SimulationResult:
        """Simulate equity curve for one run."""
        equity = config.initial_capital
        equity_curve = [equity]
        trade_returns: list[float] = []
        max_drawdown = 0.0
        peak_equity = equity
        max_dd_duration = 0
        current_dd_duration = 0
        max_loss_streak = 0
        current_loss_streak = 0

        risk_amount = equity * (config.risk_per_trade_pct / 100.0)

        for r in r_values:
            # Calculate PnL in price terms (approximation using R)
            pnl = r * risk_amount
            equity += pnl
            trade_returns.append(pnl)
            equity_curve.append(equity)

            # Track drawdown
            if equity > peak_equity:
                peak_equity = equity
                if current_dd_duration > max_dd_duration:
                    max_dd_duration = current_dd_duration
                current_dd_duration = 0
            else:
                current_dd_duration += 1

            dd = peak_equity - equity
            if dd > max_drawdown:
                max_drawdown = dd

            # Track loss streak
            if pnl < 0:
                current_loss_streak += 1
                if current_loss_streak > max_loss_streak:
                    max_loss_streak = current_loss_streak
            else:
                current_loss_streak = 0

        # Final check on drawdown duration
        if current_dd_duration > max_dd_duration:
            max_dd_duration = current_dd_duration

        max_dd_pct = (max_drawdown / config.initial_capital) * 100.0
        total_return = equity - config.initial_capital
        total_return_pct = (total_return / config.initial_capital) * 100.0

        return SimulationResult(
            run_id=run_id,
            final_equity=equity,
            total_return_pct=total_return_pct,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_dd_pct,
            max_drawdown_duration=max_dd_duration,
            max_loss_streak=max_loss_streak,
            equity_curve=equity_curve,
            trade_returns=trade_returns,
            num_trades=len(r_values),
        )

    def _aggregate_results(
        self,
        sim_results: list,
        config: SimulationConfig,
    ) -> MonteCarloReport:
        """Aggregate simulation results into a report."""
        results: list[SimulationResult] = list(sim_results)

        report = MonteCarloReport()
        report.num_simulations = len(results)
        report.config = config
        report.simulations = results

        if not results:
            return report

        # Return distribution
        returns = sorted([r.total_return_pct for r in results])
        report.avg_return_pct = statistics.mean(returns)
        report.median_return_pct = statistics.median(returns)
        report.return_std = statistics.stdev(returns) if len(returns) > 1 else 0.0
        report.min_return_pct = returns[0]
        report.max_return_pct = returns[-1]
        report.return_percentiles = {
            "p5": _percentile(returns, 5),
            "p10": _percentile(returns, 10),
            "p25": _percentile(returns, 25),
            "p50": _percentile(returns, 50),
            "p75": _percentile(returns, 75),
            "p90": _percentile(returns, 90),
            "p95": _percentile(returns, 95),
        }

        # Drawdown distribution
        drawdowns = sorted([r.max_drawdown for r in results])
        report.avg_max_drawdown = statistics.mean(drawdowns)
        report.median_max_drawdown = statistics.median(drawdowns)
        report.drawdown_std = (
            statistics.stdev(drawdowns) if len(drawdowns) > 1 else 0.0
        )
        report.max_drawdown_across_sims = drawdowns[-1] if drawdowns else 0.0
        report.drawdown_percentiles = {
            "p5": _percentile(drawdowns, 5),
            "p25": _percentile(drawdowns, 25),
            "p50": _percentile(drawdowns, 50),
            "p75": _percentile(drawdowns, 75),
            "p95": _percentile(drawdowns, 95),
        }

        # Loss streak distribution
        loss_streaks = sorted([r.max_loss_streak for r in results])
        report.avg_max_loss_streak = statistics.mean(loss_streaks)
        report.median_max_loss_streak = statistics.median(loss_streaks)
        report.loss_streak_percentiles = {
            "p25": _percentile(loss_streaks, 25),
            "p50": _percentile(loss_streaks, 50),
            "p75": _percentile(loss_streaks, 75),
            "p95": _percentile(loss_streaks, 95),
        }

        # Drawdown duration
        dd_durations = sorted([r.max_drawdown_duration for r in results])
        report.avg_max_dd_duration = statistics.mean(dd_durations)
        report.median_max_dd_duration = statistics.median(dd_durations)

        # Final equity
        equities = sorted([r.final_equity for r in results])
        report.avg_final_equity = statistics.mean(equities)
        report.median_final_equity = statistics.median(equities)

        # Probability of profit
        profitable = sum(1 for r in results if r.total_return_pct > 0)
        report.probability_of_profit = profitable / len(results)

        # Probability of ruin
        dd_limit = config.initial_capital * (config.max_drawdown_limit_pct / 100.0)
        ruined = sum(1 for r in results if r.max_drawdown > dd_limit)
        report.probability_of_ruin = ruined / len(results)

        # Robustness score (0-100)
        report.robustness_score = self._calculate_robustness(report, config)

        return report

    def _calculate_robustness(
        self,
        report: MonteCarloReport,
        config: SimulationConfig,
    ) -> float:
        """
        Calculate composite robustness score (0-100).

        Components:
          1. Probability of profit (30% weight)
          2. Median return vs drawdown (25% weight)
          3. Low probability of ruin (25% weight)
          4. Return consistency / low std (20% weight)
        """
        score = 0.0

        # 1. Probability of profit (30%)
        score += report.probability_of_profit * 30.0

        # 2. Median return quality (25%)
        # Positive return is good, high return relative to drawdown is better
        if report.median_max_drawdown > 0:
            return_dd_ratio = abs(report.median_return_pct) / report.median_max_drawdown
            # Cap at 3.0 ratio = max points
            ratio_score = min(return_dd_ratio / 3.0, 1.0)
        else:
            ratio_score = 1.0 if report.median_return_pct > 0 else 0.0
        if report.median_return_pct < 0:
            ratio_score = 0.0
        score += ratio_score * 25.0

        # 3. Low probability of ruin (25%)
        # 0% ruin = full points, 50%+ ruin = 0 points
        ruin_score = max(0.0, 1.0 - (report.probability_of_ruin * 2.0))
        score += ruin_score * 25.0

        # 4. Return consistency (20%)
        # Lower std relative to median = more consistent
        if report.median_return_pct > 0 and report.return_std > 0:
            cv = report.return_std / abs(report.median_return_pct)
            # CV of 0 = perfect (1.0), CV of 2+ = bad (0.0)
            consistency = max(0.0, 1.0 - (cv / 2.0))
        elif report.return_std == 0:
            consistency = 1.0 if report.median_return_pct > 0 else 0.5
        else:
            consistency = 0.0
        score += consistency * 20.0

        return min(100.0, max(0.0, score))

    def get_last_report(self) -> Optional[MonteCarloReport]:
        """Get the most recent simulation report."""
        return self._last_report
