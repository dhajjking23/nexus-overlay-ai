"""
NEXUS OVERLAY AI - Performance Analytics

Comprehensive trading performance metrics calculation.
Per audit spec LII: Each completed signal must be tracked for
entry, MAE, MFE, TP1/TP2/TP3, SL, Duration.

Tracks:
  - win_rate, loss_rate
  - avg_R, median_R
  - expectancy (expected R per trade)
  - profit_factor (gross profit / gross loss)
  - max_drawdown, avg_drawdown
  - MFE (Maximum Favorable Excursion), MAE (Maximum Adverse Excursion)
  - avg_trade_duration
  - TP1/TP2/TP3 hit rates, SL rate
  - signal_frequency, WAIT_frequency

Pure Python, no external dependencies required.
"""
from __future__ import annotations
import logging
import statistics
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class TradeOutcome(Enum):
    """Possible trade outcomes."""
    TP1_HIT = "TP1_HIT"
    TP2_HIT = "TP2_HIT"
    TP3_HIT = "TP3_HIT"
    SL_HIT = "SL_HIT"
    EXPIRED = "EXPIRED"
    MANUAL_CLOSE = "MANUAL_CLOSE"
    BREAKEVEN = "BREAKEVEN"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


@dataclass
class TradeRecord:
    """Complete record of a single completed trade."""
    signal_id: str
    symbol: str
    direction: str  # "BUY" or "SELL"
    entry_price: float
    sl_price: float
    tp1_price: float
    tp2_price: float
    tp3_price: float
    entry_timestamp: int
    exit_timestamp: int = 0
    exit_price: float = 0.0
    outcome: TradeOutcome = TradeOutcome.UNKNOWN
    r_multiple: float = 0.0  # profit in R units
    mae: float = 0.0  # Maximum Adverse Excursion in price
    mfe: float = 0.0  # Maximum Favorable Excursion in price
    mae_r: float = 0.0  # MAE in R units
    mfe_r: float = 0.0  # MFE in R units
    duration_seconds: float = 0.0
    primary_strategy: str = ""
    supporting_strategies: list[str] = field(default_factory=list)
    opposing_strategies: list[str] = field(default_factory=list)
    regime: str = ""
    confidence: int = 0
    rr_planned: float = 0.0  # planned risk:reward at entry

    @property
    def risk_distance(self) -> float:
        """Distance from entry to SL (always positive)."""
        return abs(self.entry_price - self.sl_price)

    @property
    def is_win(self) -> bool:
        return self.outcome in (
            TradeOutcome.TP1_HIT,
            TradeOutcome.TP2_HIT,
            TradeOutcome.TP3_HIT,
        )

    @property
    def is_loss(self) -> bool:
        return self.outcome == TradeOutcome.SL_HIT

    def to_dict(self) -> dict:
        return {
            "signal_id": self.signal_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "sl_price": self.sl_price,
            "tp1_price": self.tp1_price,
            "tp2_price": self.tp2_price,
            "tp3_price": self.tp3_price,
            "exit_price": self.exit_price,
            "outcome": self.outcome.value,
            "r_multiple": self.r_multiple,
            "mae": self.mae,
            "mfe": self.mfe,
            "mae_r": self.mae_r,
            "mfe_r": self.mfe_r,
            "duration_seconds": self.duration_seconds,
            "primary_strategy": self.primary_strategy,
            "regime": self.regime,
            "confidence": self.confidence,
            "rr_planned": self.rr_planned,
        }


@dataclass
class PerformanceMetrics:
    """Aggregated performance metrics."""
    # Sample size
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0

    # Win/Loss rates
    win_rate: float = 0.0
    loss_rate: float = 0.0

    # R-multiple metrics
    avg_r: float = 0.0
    median_r: float = 0.0
    std_r: float = 0.0
    max_r: float = 0.0
    min_r: float = 0.0

    # Expectancy
    expectancy: float = 0.0  # average R per trade

    # Profit factor
    profit_factor: float = 0.0  # gross_profit / abs(gross_loss)

    # Drawdown
    max_drawdown: float = 0.0  # in price or R
    max_drawdown_r: float = 0.0
    avg_drawdown: float = 0.0
    max_drawdown_duration: float = 0.0  # seconds

    # Excursion
    avg_mae: float = 0.0
    avg_mfe: float = 0.0
    avg_mae_r: float = 0.0
    avg_mfe_r: float = 0.0
    max_mae: float = 0.0
    max_mfe: float = 0.0

    # Duration
    avg_trade_duration: float = 0.0
    median_trade_duration: float = 0.0

    # TP/SL hit rates
    tp1_hit_rate: float = 0.0
    tp2_hit_rate: float = 0.0
    tp3_hit_rate: float = 0.0
    sl_hit_rate: float = 0.0

    # Signal frequency
    signal_frequency: float = 0.0  # signals per hour
    wait_frequency: float = 0.0  # WAIT decisions per hour
    buy_frequency: float = 0.0
    sell_frequency: float = 0.0

    # Total evaluation time
    total_eval_time_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "breakeven_trades": self.breakeven_trades,
            "win_rate": self.win_rate,
            "loss_rate": self.loss_rate,
            "avg_r": self.avg_r,
            "median_r": self.median_r,
            "std_r": self.std_r,
            "max_r": self.max_r,
            "min_r": self.min_r,
            "expectancy": self.expectancy,
            "profit_factor": self.profit_factor,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_r": self.max_drawdown_r,
            "avg_drawdown": self.avg_drawdown,
            "max_drawdown_duration": self.max_drawdown_duration,
            "avg_mae": self.avg_mae,
            "avg_mfe": self.avg_mfe,
            "avg_mae_r": self.avg_mae_r,
            "avg_mfe_r": self.avg_mfe_r,
            "max_mae": self.max_mae,
            "max_mfe": self.max_mfe,
            "avg_trade_duration": self.avg_trade_duration,
            "median_trade_duration": self.median_trade_duration,
            "tp1_hit_rate": self.tp1_hit_rate,
            "tp2_hit_rate": self.tp2_hit_rate,
            "tp3_hit_rate": self.tp3_hit_rate,
            "sl_hit_rate": self.sl_hit_rate,
            "signal_frequency": self.signal_frequency,
            "wait_frequency": self.wait_frequency,
            "buy_frequency": self.buy_frequency,
            "sell_frequency": self.sell_frequency,
            "total_eval_time_seconds": self.total_eval_time_seconds,
        }


@dataclass
class FrequencyStats:
    """Signal frequency statistics."""
    total_candles: int = 0
    total_signals: int = 0
    buy_signals: int = 0
    sell_signals: int = 0
    wait_signals: int = 0
    total_duration_seconds: float = 0.0
    signal_frequency: float = 0.0  # signals per hour
    wait_frequency: float = 0.0
    buy_frequency: float = 0.0
    sell_frequency: float = 0.0


class PerformanceAnalytics:
    """
    Calculate comprehensive performance metrics from trade records.

    Usage:
        analytics = PerformanceAnalytics()
        for trade in trade_records:
            analytics.add_trade(trade)
        metrics = analytics.calculate()
        print(metrics.win_rate, metrics.expectancy)
    """

    def __init__(self, initial_capital: float = 10000.0):
        self._trades: list[TradeRecord] = []
        self._initial_capital = initial_capital
        self._total_candles: int = 0
        self._total_eval_time: float = 0.0

    def add_trade(self, trade: TradeRecord) -> None:
        """Add a completed trade record."""
        self._trades.append(trade)

    def add_trades(self, trades: list[TradeRecord]) -> None:
        """Add multiple completed trade records."""
        self._trades.extend(trades)

    def set_total_candles(self, count: int) -> None:
        """Set the total number of candles evaluated (for frequency calc)."""
        self._total_candles = count

    def set_total_eval_time(self, seconds: float) -> None:
        """Set total evaluation time in seconds."""
        self._total_eval_time = seconds

    def get_trades(self) -> list[TradeRecord]:
        """Get all stored trade records."""
        return list(self._trades)

    def calculate(self) -> PerformanceMetrics:
        """Calculate all performance metrics from stored trades."""
        metrics = PerformanceMetrics()
        trades = self._trades

        if not trades:
            return metrics

        metrics.total_trades = len(trades)

        # --- Win/Loss counts ---
        wins = [t for t in trades if t.is_win]
        losses = [t for t in trades if t.is_loss]
        breakeven = [t for t in trades if t.outcome == TradeOutcome.BREAKEVEN]

        metrics.winning_trades = len(wins)
        metrics.losing_trades = len(losses)
        metrics.breakeven_trades = len(breakeven)

        # --- Win/Loss rates ---
        if metrics.total_trades > 0:
            metrics.win_rate = metrics.winning_trades / metrics.total_trades
            metrics.loss_rate = metrics.losing_trades / metrics.total_trades

        # --- R-multiple stats ---
        r_values = [t.r_multiple for t in trades]
        if r_values:
            metrics.avg_r = statistics.mean(r_values)
            metrics.median_r = statistics.median(r_values)
            metrics.std_r = statistics.stdev(r_values) if len(r_values) > 1 else 0.0
            metrics.max_r = max(r_values)
            metrics.min_r = min(r_values)

        # --- Expectancy ---
        # Expectancy = (win_rate * avg_win_R) - (loss_rate * avg_loss_R)
        if wins:
            avg_win_r = statistics.mean([t.r_multiple for t in wins])
        else:
            avg_win_r = 0.0
        if losses:
            avg_loss_r = statistics.mean([t.r_multiple for t in losses])
        else:
            avg_loss_r = 0.0
        metrics.expectancy = (
            metrics.win_rate * avg_win_r + metrics.loss_rate * avg_loss_r
        )

        # --- Profit factor ---
        gross_profit = sum(t.r_multiple for t in trades if t.r_multiple > 0)
        gross_loss = abs(sum(t.r_multiple for t in trades if t.r_multiple < 0))
        if gross_loss > 0:
            metrics.profit_factor = gross_profit / gross_loss
        elif gross_profit > 0:
            metrics.profit_factor = float('inf')
        else:
            metrics.profit_factor = 0.0

        # --- Drawdown analysis ---
        dd_result = self._calculate_drawdown(trades)
        metrics.max_drawdown = dd_result["max_drawdown"]
        metrics.max_drawdown_r = dd_result["max_drawdown_r"]
        metrics.avg_drawdown = dd_result["avg_drawdown"]
        metrics.max_drawdown_duration = dd_result["max_drawdown_duration"]

        # --- MAE / MFE ---
        mae_values = [t.mae for t in trades if t.mae > 0]
        mfe_values = [t.mfe for t in trades if t.mfe > 0]
        mae_r_values = [t.mae_r for t in trades if t.mae_r > 0]
        mfe_r_values = [t.mfe_r for t in trades if t.mfe_r > 0]

        metrics.avg_mae = statistics.mean(mae_values) if mae_values else 0.0
        metrics.avg_mfe = statistics.mean(mfe_values) if mfe_values else 0.0
        metrics.avg_mae_r = statistics.mean(mae_r_values) if mae_r_values else 0.0
        metrics.avg_mfe_r = statistics.mean(mfe_r_values) if mfe_r_values else 0.0
        metrics.max_mae = max(mae_values) if mae_values else 0.0
        metrics.max_mfe = max(mfe_values) if mfe_values else 0.0

        # --- Duration ---
        durations = [t.duration_seconds for t in trades if t.duration_seconds > 0]
        metrics.avg_trade_duration = statistics.mean(durations) if durations else 0.0
        metrics.median_trade_duration = (
            statistics.median(durations) if durations else 0.0
        )

        # --- TP/SL hit rates ---
        if metrics.total_trades > 0:
            metrics.tp1_hit_rate = (
                len([t for t in trades if t.outcome == TradeOutcome.TP1_HIT])
                / metrics.total_trades
            )
            metrics.tp2_hit_rate = (
                len([t for t in trades if t.outcome == TradeOutcome.TP2_HIT])
                / metrics.total_trades
            )
            metrics.tp3_hit_rate = (
                len([t for t in trades if t.outcome == TradeOutcome.TP3_HIT])
                / metrics.total_trades
            )
            metrics.sl_hit_rate = metrics.loss_rate

        # --- Frequency ---
        freq = self._calculate_frequency(trades)
        metrics.signal_frequency = freq["signal_frequency"]
        metrics.wait_frequency = freq["wait_frequency"]
        metrics.buy_frequency = freq["buy_frequency"]
        metrics.sell_frequency = freq["sell_frequency"]

        metrics.total_eval_time_seconds = self._total_eval_time

        return metrics

    def _calculate_drawdown(self, trades: list[TradeRecord]) -> dict:
        """Calculate drawdown series from sequential trade results."""
        if not trades:
            return {
                "max_drawdown": 0.0,
                "max_drawdown_r": 0.0,
                "avg_drawdown": 0.0,
                "max_drawdown_duration": 0.0,
            }

        equity_curve = [self._initial_capital]
        r_curve = [0.0]
        cumulative_r = 0.0

        for trade in trades:
            # Convert R to approximate price change for drawdown
            risk = trade.risk_distance
            pnl = trade.r_multiple * risk
            equity_curve.append(equity_curve[-1] + pnl)
            cumulative_r += trade.r_multiple
            r_curve.append(cumulative_r)

        # Calculate drawdowns
        peak = equity_curve[0]
        r_peak = r_curve[0]
        drawdowns: list[float] = []
        drawdowns_r: list[float] = []
        current_dd_duration = 0.0
        max_dd_duration = 0.0

        for i in range(1, len(equity_curve)):
            if equity_curve[i] > peak:
                peak = equity_curve[i]
                # End of drawdown period
                if current_dd_duration > max_dd_duration:
                    max_dd_duration = current_dd_duration
                current_dd_duration = 0.0
            else:
                dd = peak - equity_curve[i]
                drawdowns.append(dd)
                current_dd_duration += trades[i - 1].duration_seconds if i - 1 < len(trades) else 0.0

            if r_curve[i] > r_peak:
                r_peak = r_curve[i]
            else:
                dd_r = r_peak - r_curve[i]
                drawdowns_r.append(dd_r)

        # Check final drawdown period
        if current_dd_duration > max_dd_duration:
            max_dd_duration = current_dd_duration

        return {
            "max_drawdown": max(drawdowns) if drawdowns else 0.0,
            "max_drawdown_r": max(drawdowns_r) if drawdowns_r else 0.0,
            "avg_drawdown": statistics.mean(drawdowns) if drawdowns else 0.0,
            "max_drawdown_duration": max_dd_duration,
        }

    def _calculate_frequency(self, trades: list[TradeRecord]) -> dict:
        """Calculate signal frequency metrics."""
        total = len(trades)
        if total == 0:
            return {
                "signal_frequency": 0.0,
                "wait_frequency": 0.0,
                "buy_frequency": 0.0,
                "sell_frequency": 0.0,
            }

        # Calculate total duration span
        if total >= 2:
            first_ts = trades[0].entry_timestamp
            last_ts = max(
                t.exit_timestamp if t.exit_timestamp > 0 else t.entry_timestamp
                for t in trades
            )
            duration_hours = max((last_ts - first_ts) / 3600000.0, 0.001)
        else:
            duration_hours = 1.0

        buy_count = len([t for t in trades if t.direction == "BUY"])
        sell_count = len([t for t in trades if t.direction == "SELL"])

        return {
            "signal_frequency": total / duration_hours,
            "wait_frequency": max(
                (self._total_candles - total) / duration_hours, 0.0
            ) if self._total_candles > total else 0.0,
            "buy_frequency": buy_count / duration_hours,
            "sell_frequency": sell_count / duration_hours,
        }

    def calculate_by_regime(self) -> dict[str, PerformanceMetrics]:
        """Calculate performance metrics grouped by market regime."""
        regime_trades: dict[str, list[TradeRecord]] = {}
        for trade in self._trades:
            regime = trade.regime or "UNKNOWN"
            if regime not in regime_trades:
                regime_trades[regime] = []
            regime_trades[regime].append(trade)

        results: dict[str, PerformanceMetrics] = {}
        for regime, rt in regime_trades.items():
            sub_analytics = PerformanceAnalytics(self._initial_capital)
            sub_analytics.add_trades(rt)
            sub_analytics.set_total_candles(self._total_candles)
            sub_analytics.set_total_eval_time(self._total_eval_time)
            results[regime] = sub_analytics.calculate()

        return results

    def calculate_by_strategy(self) -> dict[str, PerformanceMetrics]:
        """Calculate performance metrics grouped by primary strategy."""
        strategy_trades: dict[str, list[TradeRecord]] = {}
        for trade in self._trades:
            strat = trade.primary_strategy or "UNKNOWN"
            if strat not in strategy_trades:
                strategy_trades[strat] = []
            strategy_trades[strat].append(trade)

        results: dict[str, PerformanceMetrics] = {}
        for strat, st in strategy_trades.items():
            sub_analytics = PerformanceAnalytics(self._initial_capital)
            sub_analytics.add_trades(st)
            sub_analytics.set_total_candles(self._total_candles)
            sub_analytics.set_total_eval_time(self._total_eval_time)
            results[strat] = sub_analytics.calculate()

        return results

    def calculate_by_direction(self) -> dict[str, PerformanceMetrics]:
        """Calculate performance metrics grouped by BUY/SELL."""
        dir_trades: dict[str, list[TradeRecord]] = {}
        for trade in self._trades:
            d = trade.direction
            if d not in dir_trades:
                dir_trades[d] = []
            dir_trades[d].append(trade)

        results: dict[str, PerformanceMetrics] = {}
        for d, dt in dir_trades.items():
            sub_analytics = PerformanceAnalytics(self._initial_capital)
            sub_analytics.add_trades(dt)
            sub_analytics.set_total_candles(self._total_candles)
            sub_analytics.set_total_eval_time(self._total_eval_time)
            results[d] = sub_analytics.calculate()

        return results

    def reset(self) -> None:
        """Clear all stored trades."""
        self._trades.clear()
        self._total_candles = 0
        self._total_eval_time = 0.0
