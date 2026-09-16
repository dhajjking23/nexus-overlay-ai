"""
NEXUS OVERLAY AI - Backtester

Per audit spec XLVI (Walk-forward testing):
  TRAIN → VALIDATION → OUT-OF-SAMPLE

Feeds historical candles sequentially through the full analysis pipeline,
records all signals with entry/SL/TP outcomes.

Tracks:
  - win_rate, avg_R, expectancy, max_drawdown, profit_factor
  - Walk-forward: train_period, validation_period, out_of_sample_period

Pure Python, no external ML libraries required.
"""
from __future__ import annotations
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from backend.replay.replay_engine import (
    MarketReplayEngine,
    ReplayCandle,
    ReplayResult,
    ReplayStats,
)
from backend.analytics.performance import (
    PerformanceAnalytics,
    PerformanceMetrics,
    TradeRecord,
    TradeOutcome,
)
from backend.models import DecisionState

logger = logging.getLogger(__name__)


@dataclass
class TradeSetup:
    """Captured signal for potential trade entry."""
    signal_id: str
    direction: str  # "BUY" or "SELL"
    entry_price: float
    sl_price: float
    tp1_price: float
    tp2_price: float
    tp3_price: float
    rr: float
    confidence: int
    candle_index: int
    timestamp: int
    regime: str = ""
    trend: str = ""
    primary_strategy: str = ""
    supporting_strategies: list[str] = field(default_factory=list)
    opposing_strategies: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


@dataclass
class TradeOutcome_:
    """Outcome of a trade that was tracked through subsequent candles."""
    setup: TradeSetup
    exit_candle_index: int
    exit_price: float
    outcome: TradeOutcome
    r_multiple: float
    mae: float  # Maximum adverse excursion in price
    mfe: float  # Maximum favorable excursion in price
    mae_r: float
    mfe_r: float
    duration_candles: int
    duration_seconds: float

    def to_trade_record(self) -> TradeRecord:
        """Convert to TradeRecord for analytics."""
        risk = abs(self.setup.entry_price - self.setup.sl_price)
        duration_sec = self.duration_seconds
        return TradeRecord(
            signal_id=self.setup.signal_id,
            symbol="XAUUSD",
            direction=self.setup.direction,
            entry_price=self.setup.entry_price,
            sl_price=self.setup.sl_price,
            tp1_price=self.setup.tp1_price,
            tp2_price=self.setup.tp2_price,
            tp3_price=self.setup.tp3_price,
            entry_timestamp=self.setup.timestamp,
            exit_timestamp=self.setup.timestamp + int(duration_sec * 1000),
            exit_price=self.exit_price,
            outcome=self.outcome,
            r_multiple=self.r_multiple,
            mae=self.mae,
            mfe=self.mfe,
            mae_r=self.mae_r,
            mfe_r=self.mfe_r,
            duration_seconds=duration_sec,
            primary_strategy=self.setup.primary_strategy,
            supporting_strategies=list(self.setup.supporting_strategies),
            opposing_strategies=list(self.setup.opposing_strategies),
            regime=self.setup.regime,
            confidence=self.setup.confidence,
            rr_planned=self.setup.rr,
        )


@dataclass
class BacktestResult:
    """Complete result of a backtest run."""
    period_label: str  # "train", "validation", "out_of_sample", or custom
    metrics: PerformanceMetrics
    trade_outcomes: list[TradeOutcome_]
    total_candles: int
    total_signals_generated: int
    total_trades_taken: int
    processing_time_seconds: float

    def to_dict(self) -> dict:
        return {
            "period_label": self.period_label,
            "total_candles": self.total_candles,
            "total_signals_generated": self.total_signals_generated,
            "total_trades_taken": self.total_trades_taken,
            "processing_time_seconds": self.processing_time_seconds,
            "metrics": self.metrics.to_dict(),
        }


@dataclass
class WalkForwardResult:
    """Result of walk-forward analysis across multiple periods."""
    periods: list[BacktestResult]
    train_result: Optional[BacktestResult] = None
    validation_result: Optional[BacktestResult] = None
    out_of_sample_result: Optional[BacktestResult] = None
    combined_metrics: Optional[PerformanceMetrics] = None
    is_robust: bool = False  # validation agrees with train

    def to_dict(self) -> dict:
        return {
            "periods": [p.to_dict() for p in self.periods],
            "train": self.train_result.to_dict() if self.train_result else None,
            "validation": (
                self.validation_result.to_dict() if self.validation_result else None
            ),
            "out_of_sample": (
                self.out_of_sample_result.to_dict()
                if self.out_of_sample_result
                else None
            ),
            "is_robust": self.is_robust,
            "combined_metrics": (
                self.combined_metrics.to_dict() if self.combined_metrics else None
            ),
        }


class Backtester:
    """
    Full backtester that feeds historical candles through the analysis
    pipeline, tracks trades, and computes performance metrics.

    Supports walk-forward analysis: split data into train/validation/OOS.

    Usage:
        backtester = Backtester()
        backtester.set_pipeline(handlers...)

        # Simple backtest
        result = backtester.run(candles, label="full")

        # Walk-forward
        wf_result = backtester.walk_forward(
            candles,
            train_ratio=0.6,
            validation_ratio=0.2,
            out_of_sample_ratio=0.2,
        )
    """

    def __init__(self):
        self._engine = MarketReplayEngine()
        self._active_trades: list[TradeSetup] = []
        self._completed_trades: list[TradeOutcome_] = []
        self._signal_counter = 0

        # Configuration
        self._max_active_trades = 1
        self._trade_duration_limit_candles = 1000  # force-close after N candles
        self._tp1_partial_exit_pct = 0.5  # partial exit at TP1

    def set_pipeline(
        self,
        market_data_handler: Any = None,
        strategy_evaluator: Any = None,
        confluence_calculator: Any = None,
        decision_maker: Any = None,
        signal_builder: Any = None,
    ) -> None:
        """Set the analysis pipeline functions on the underlying engine."""
        self._engine.set_pipeline(
            market_data_handler=market_data_handler,
            strategy_evaluator=strategy_evaluator,
            confluence_calculator=confluence_calculator,
            decision_maker=decision_maker,
            signal_builder=signal_builder,
        )

    def set_max_active_trades(self, n: int) -> None:
        """Max simultaneous open trades."""
        self._max_active_trades = n

    def set_trade_duration_limit(self, candles: int) -> None:
        """Force-close trades after this many candles."""
        self._trade_duration_limit_candles = candles

    def run(
        self,
        candles: list[ReplayCandle],
        label: str = "backtest",
        speed: float = 0.0,
    ) -> BacktestResult:
        """
        Run a full backtest on the given candles.

        Args:
            candles: Historical OHLCV data.
            label: Period label (e.g., "train", "validation", "out_of_sample").
            speed: Replay speed (0 = max speed).

        Returns:
            BacktestResult with metrics and trade outcomes.
        """
        start_time = time.time()

        # Reset state
        self._active_trades.clear()
        self._completed_trades.clear()
        self._signal_counter = 0
        self._engine.reset()

        # Run replay
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're already in an async context, use a helper
                stats = loop.run_until_complete(
                    self._async_run(candles, speed)
                )
            else:
                stats = loop.run_until_complete(
                    self._async_run(candles, speed)
                )
        except RuntimeError:
            stats = asyncio.run(self._async_run(candles, speed))

        # Force-close remaining active trades
        self._force_close_all(candles)

        # Build analytics
        analytics = PerformanceAnalytics()
        trade_records = [to.to_trade_record() for to in self._completed_trades]
        analytics.add_trades(trade_records)
        analytics.set_total_candles(len(candles))
        metrics = analytics.calculate()

        elapsed = time.time() - start_time

        result = BacktestResult(
            period_label=label,
            metrics=metrics,
            trade_outcomes=list(self._completed_trades),
            total_candles=len(candles),
            total_signals_generated=stats.total_signals,
            total_trades_taken=len(self._completed_trades),
            processing_time_seconds=elapsed,
        )

        logger.info(
            f"Backtest [{label}]: {len(candles)} candles, "
            f"{stats.total_signals} signals, "
            f"{len(self._completed_trades)} trades, "
            f"win_rate={metrics.win_rate:.1%}, "
            f"expectancy={metrics.expectancy:.2f}R"
        )

        return result

    async def _async_run(
        self,
        candles: list[ReplayCandle],
        speed: float,
    ) -> ReplayStats:
        """Internal async replay run."""
        stats = ReplayStats()
        self._engine._results = []
        self._engine._current_index = 0

        for i, candle in enumerate(candles):
            self._engine._current_index = i
            result = await self._engine._process_candle(candle, i)
            self._engine._results.append(result)
            stats.results.append(result)
            stats.total_candles = i + 1

            # Track signals and manage trades
            self._track_signal(result, i, candle, candles)

            # Update active trades
            self._update_active_trades(i, candle, candles)

            # Update stats
            stats.total_processing_time_ms += result.processing_time_ms
            if result.signal:
                stats.total_signals += 1
                if result.decision == "BUY":
                    stats.buy_signals += 1
                elif result.decision == "SELL":
                    stats.sell_signals += 1
                else:
                    stats.wait_signals += 1

            if stats.total_signals > 0:
                stats.avg_confidence = sum(
                    r.confidence for r in self._engine._results if r.signal
                ) / stats.total_signals

            if speed > 0:
                import asyncio as _asyncio
                await _asyncio.sleep(speed)

        return stats

    def _track_signal(
        self,
        result: ReplayResult,
        index: int,
        candle: ReplayCandle,
        all_candles: list[ReplayCandle],
    ) -> None:
        """Track a new signal and potentially open a trade."""
        if not result.signal:
            return

        signal = result.signal

        # Only track BUY/SELL signals
        if signal.decision not in (DecisionState.BUY, DecisionState.SELL):
            return

        # Check if we can take another trade
        if len(self._active_trades) >= self._max_active_trades:
            return

        # Avoid duplicate entries at same price level
        for active in self._active_trades:
            if (
                active.direction == signal.decision.value
                and abs(active.entry_price - signal.entry) < 0.001
            ):
                return

        self._signal_counter += 1
        primary = ""
        supporting = []
        opposing = []
        if result.strategy_assessments:
            best_score = -1
            for sa in result.strategy_assessments:
                d = ""
                if hasattr(sa, 'direction'):
                    d = sa.direction.value if hasattr(sa.direction, 'value') else str(sa.direction)
                if d == signal.decision.value and sa.score > best_score:
                    best_score = sa.score
                    primary = sa.strategy
            for sa in result.strategy_assessments:
                d = ""
                if hasattr(sa, 'direction'):
                    d = sa.direction.value if hasattr(sa.direction, 'value') else str(sa.direction)
                name = sa.strategy
                if name == primary:
                    continue
                elif d == signal.decision.value and sa.score > 0:
                    supporting.append(name)
                elif d != signal.decision.value and d != "WAIT" and sa.score > 0:
                    opposing.append(name)

        setup = TradeSetup(
            signal_id=f"SIG-{self._signal_counter:06d}",
            direction=signal.decision.value,
            entry_price=signal.entry,
            sl_price=signal.sl,
            tp1_price=signal.tp1,
            tp2_price=signal.tp2,
            tp3_price=signal.tp3,
            rr=signal.rr,
            confidence=signal.confidence,
            candle_index=index,
            timestamp=candle.timestamp,
            regime=signal.regime,
            trend=signal.trend,
            primary_strategy=primary,
            supporting_strategies=supporting,
            opposing_strategies=opposing,
            evidence=list(signal.evidence),
        )
        self._active_trades.append(setup)

    def _update_active_trades(
        self,
        index: int,
        candle: ReplayCandle,
        all_candles: list[ReplayCandle],
    ) -> None:
        """Check active trades against current candle for TP/SL hits."""
        closed_indices = []

        for i, trade in enumerate(self._active_trades):
            # Check candle high/low for TP/SL
            high = candle.high
            low = candle.low

            if trade.direction == "BUY":
                # For BUY: SL is below entry, TP is above
                hit_sl = low <= trade.sl_price
                hit_tp3 = high >= trade.tp3_price
                hit_tp2 = high >= trade.tp2_price
                hit_tp1 = high >= trade.tp1_price
            else:
                # For SELL: SL is above entry, TP is below
                hit_sl = high >= trade.sl_price
                hit_tp3 = low <= trade.tp3_price
                hit_tp2 = low <= trade.tp2_price
                hit_tp1 = low <= trade.tp1_price

            # Determine outcome
            outcome = None
            exit_price = 0.0

            if hit_sl:
                outcome = TradeOutcome.SL_HIT
                exit_price = trade.sl_price
            elif hit_tp3:
                outcome = TradeOutcome.TP3_HIT
                exit_price = trade.tp3_price
            elif hit_tp2:
                outcome = TradeOutcome.TP2_HIT
                exit_price = trade.tp2_price
            elif hit_tp1:
                outcome = TradeOutcome.TP1_HIT
                exit_price = trade.tp1_price

            # Check duration limit
            if outcome is None:
                candles_held = index - trade.candle_index
                if candles_held >= self._trade_duration_limit_candles:
                    outcome = TradeOutcome.EXPIRED
                    exit_price = candle.close

            if outcome is not None:
                # Calculate MAE/MFE
                risk = abs(trade.entry_price - trade.sl_price)
                mae, mfe = self._calculate_mae_mfe(trade, all_candles, index)

                # Calculate R-multiple
                if trade.direction == "BUY":
                    pnl = exit_price - trade.entry_price
                else:
                    pnl = trade.entry_price - exit_price

                r_multiple = pnl / risk if risk > 0 else 0.0

                duration_candles = index - trade.candle_index
                duration_seconds = (
                    candle.timestamp - all_candles[trade.candle_index].timestamp
                ) / 1000.0

                trade_outcome = TradeOutcome_(
                    setup=trade,
                    exit_candle_index=index,
                    exit_price=exit_price,
                    outcome=outcome,
                    r_multiple=r_multiple,
                    mae=mae,
                    mfe=mfe,
                    mae_r=mae / risk if risk > 0 else 0.0,
                    mfe_r=mfe / risk if risk > 0 else 0.0,
                    duration_candles=duration_candles,
                    duration_seconds=duration_seconds,
                )
                self._completed_trades.append(trade_outcome)
                closed_indices.append(i)

        # Remove closed trades (in reverse order)
        for i in sorted(closed_indices, reverse=True):
            self._active_trades.pop(i)

    def _calculate_mae_mfe(
        self,
        trade: TradeSetup,
        all_candles: list[ReplayCandle],
        current_index: int,
    ) -> tuple[float, float]:
        """Calculate Maximum Adverse Excursion and Maximum Favorable Excursion."""
        start = trade.candle_index
        end = current_index + 1

        mae = 0.0  # worst adverse move from entry
        mfe = 0.0  # best favorable move from entry

        for idx in range(start, end):
            if idx >= len(all_candles):
                break
            c = all_candles[idx]

            if trade.direction == "BUY":
                # Adverse: price goes below entry
                adverse = trade.entry_price - c.low
                # Favorable: price goes above entry
                favorable = c.high - trade.entry_price
            else:
                # Adverse: price goes above entry
                adverse = c.high - trade.entry_price
                # Favorable: price goes below entry
                favorable = trade.entry_price - c.low

            mae = max(mae, adverse)
            mfe = max(mfe, favorable)

        return mae, mfe

    def _force_close_all(self, all_candles: list[ReplayCandle]) -> None:
        """Force-close any remaining active trades at last candle close."""
        if not self._active_trades or not all_candles:
            return

        last_index = len(all_candles) - 1
        last_candle = all_candles[-1]

        for trade in self._active_trades:
            risk = abs(trade.entry_price - trade.sl_price)
            mae, mfe = self._calculate_mae_mfe(
                trade, all_candles, last_index
            )

            if trade.direction == "BUY":
                pnl = last_candle.close - trade.entry_price
            else:
                pnl = trade.entry_price - last_candle.close

            r_multiple = pnl / risk if risk > 0 else 0.0

            duration_candles = last_index - trade.candle_index
            duration_seconds = (
                last_candle.timestamp - all_candles[trade.candle_index].timestamp
            ) / 1000.0

            trade_outcome = TradeOutcome_(
                setup=trade,
                exit_candle_index=last_index,
                exit_price=last_candle.close,
                outcome=TradeOutcome.EXPIRED,
                r_multiple=r_multiple,
                mae=mae,
                mfe=mfe,
                mae_r=mae / risk if risk > 0 else 0.0,
                mfe_r=mfe / risk if risk > 0 else 0.0,
                duration_candles=duration_candles,
                duration_seconds=duration_seconds,
            )
            self._completed_trades.append(trade_outcome)

        self._active_trades.clear()

    def walk_forward(
        self,
        candles: list[ReplayCandle],
        train_ratio: float = 0.6,
        validation_ratio: float = 0.2,
        out_of_sample_ratio: float = 0.2,
        label_prefix: str = "WF",
    ) -> WalkForwardResult:
        """
        Run walk-forward analysis.

        Splits candles into train/validation/out_of_sample periods
        and runs backtest on each.

        Args:
            candles: Full historical data.
            train_ratio: Fraction of data for training.
            validation_ratio: Fraction for validation.
            out_of_sample_ratio: Fraction for out-of-sample.
            label_prefix: Label prefix for periods.

        Returns:
            WalkForwardResult with per-period results and robustness check.
        """
        total = len(candles)
        train_end = int(total * train_ratio)
        val_end = int(total * (train_ratio + validation_ratio))

        train_candles = candles[:train_end]
        val_candles = candles[train_end:val_end]
        oos_candles = candles[val_end:]

        logger.info(
            f"Walk-forward: train={len(train_candles)}, "
            f"validation={len(val_candles)}, "
            f"out_of_sample={len(oos_candles)}"
        )

        # Run each period with a fresh engine
        train_result = self._run_period(train_candles, f"{label_prefix}_train")
        val_result = self._run_period(val_candles, f"{label_prefix}_validation")
        oos_result = self._run_period(oos_candles, f"{label_prefix}_out_of_sample")

        # Combine all trades for overall metrics
        all_outcomes = (
            train_result.trade_outcomes
            + val_result.trade_outcomes
            + oos_result.trade_outcomes
        )
        analytics = PerformanceAnalytics()
        analytics.add_trades([to.to_trade_record() for to in all_outcomes])
        analytics.set_total_candles(total)
        combined = analytics.calculate()

        # Check robustness: validation should agree with train directionally
        is_robust = self._check_robustness(train_result, val_result)

        wf = WalkForwardResult(
            periods=[train_result, val_result, oos_result],
            train_result=train_result,
            validation_result=val_result,
            out_of_sample_result=oos_result,
            combined_metrics=combined,
            is_robust=is_robust,
        )

        logger.info(
            f"Walk-forward complete: train_win={train_result.metrics.win_rate:.1%}, "
            f"val_win={val_result.metrics.win_rate:.1%}, "
            f"oos_win={oos_result.metrics.win_rate:.1%}, "
            f"robust={is_robust}"
        )

        return wf

    def _run_period(
        self,
        candles: list[ReplayCandle],
        label: str,
    ) -> BacktestResult:
        """Run a single backtest period with fresh engine state."""
        saved_active = list(self._active_trades)
        saved_completed = list(self._completed_trades)
        saved_counter = self._signal_counter

        self._active_trades.clear()
        self._completed_trades.clear()
        self._signal_counter = 0
        self._engine.reset()

        result = self.run(candles, label=label, speed=0.0)

        # Restore state
        self._active_trades = saved_active
        self._completed_trades = saved_completed
        self._signal_counter = saved_counter

        return result

    def _check_robustness(
        self,
        train: BacktestResult,
        validation: BacktestResult,
    ) -> bool:
        """
        Check if validation results agree with train results.

        Robust if:
          - Both have positive expectancy, or
          - Win rates are within 15 percentage points
          - Expectancy signs agree (both positive or both negative)
        """
        # Check expectancy sign agreement
        train_exp_positive = train.metrics.expectancy > 0
        val_exp_positive = validation.metrics.expectancy > 0

        if train_exp_positive != val_exp_positive:
            return False

        # Check win rate proximity
        wr_diff = abs(train.metrics.win_rate - validation.metrics.win_rate)
        if wr_diff > 0.15:
            return False

        # Both have same direction and reasonable proximity
        return True
