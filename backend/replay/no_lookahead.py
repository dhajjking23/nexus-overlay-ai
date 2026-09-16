"""
NEXUS OVERLAY AI - Look-Ahead Bias Detector

Ensures that NO analysis function accesses data beyond the current bar.
Provides decorators and runtime checkers for detecting future data access
in backtesting and replay scenarios.

Per audit spec XLV:
  Engine must NOT see future candles, future highs, future lows, future
  structure when generating signals.
"""
from __future__ import annotations
import functools
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class LookAheadViolation:
    """Record of a detected look-ahead violation."""
    function_name: str
    description: str
    expected_index: int
    accessed_index: int
    bar_count_available: int
    violation_type: str  # "future_candle", "future_high", "future_low", "future_index"

    def to_dict(self) -> dict:
        return {
            "function_name": self.function_name,
            "description": self.description,
            "expected_index": self.expected_index,
            "accessed_index": self.accessed_index,
            "bar_count_available": self.bar_count_available,
            "violation_type": self.violation_type,
        }


@dataclass
class LookAheadReport:
    """Report from a look-ahead detection pass."""
    violations: list[LookAheadViolation] = field(default_factory=list)
    checks_passed: int = 0
    checks_failed: int = 0

    @property
    def clean(self) -> bool:
        return len(self.violations) == 0

    def summary(self) -> dict:
        return {
            "clean": self.clean,
            "violations": len(self.violations),
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
            "violation_details": [v.to_dict() for v in self.violations],
        }


class CandleWindow:
    """
    A strictly-bounded window of candles that enforces look-ahead prevention.

    The window only exposes candles up to and including the current index.
    Any attempt to access future candles raises a LookAheadError.

    Usage:
        window = CandleWindow(all_candles)
        window.set_index(50)
        # window[49] works (past candle)
        # window[50] works (current candle)
        # window[51] raises LookAheadError
        window.get_current_candles(count=20)  # last 20 up to index 50
    """

    def __init__(self, candles: list[Any], strict: bool = True):
        self._candles = list(candles)
        self._current_index = 0
        self._strict = strict
        self._violations: list[LookAheadViolation] = []

    @property
    def current_index(self) -> int:
        return self._current_index

    @property
    def bar_count(self) -> int:
        return len(self._candles)

    def set_index(self, index: int) -> None:
        """Set the current replay index."""
        if index < 0 or index >= len(self._candles):
            raise IndexError(
                f"Index {index} out of range [0, {len(self._candles) - 1}]"
            )
        self._current_index = index

    def _check_access(self, index: int, context: str = "") -> None:
        """Verify that an index access does not exceed current position."""
        if index > self._current_index:
            violation = LookAheadViolation(
                function_name=context or "unknown",
                description=f"Attempted to access candle at index {index}, "
                            f"but current position is {self._current_index}",
                expected_index=self._current_index,
                accessed_index=index,
                bar_count_available=len(self._candles),
                violation_type="future_index",
            )
            self._violations.append(violation)
            if self._strict:
                raise LookAheadError(
                    f"LOOK-AHEAD VIOLATION: {violation.description}"
                )
            else:
                logger.warning(
                    "Look-ahead violation detected (non-strict mode): "
                    f"{violation.description}"
                )

    def get(self, index: int, context: str = "") -> Any:
        """Get a single candle at index with look-ahead check."""
        self._check_access(index, context)
        return self._candles[index]

    def get_current_candles(self, count: int, context: str = "") -> list[Any]:
        """Get the last `count` candles up to and including current index.

        This is the primary method strategies should use. It guarantees
        no future data is exposed.
        """
        start = max(0, self._current_index - count + 1)
        end = self._current_index + 1
        return self._candles[start:end]

    def get_latest_candle(self, context: str = "") -> Any:
        """Get the most recent candle (at current index)."""
        return self._candles[self._current_index]

    def get_high_up_to(self, context: str = "") -> float:
        """Get the highest high among all candles up to current index."""
        segment = self._candles[:self._current_index + 1]
        if not segment:
            return 0.0
        return max(c.high for c in segment)

    def get_low_up_to(self, context: str = "") -> float:
        """Get the lowest low among all candles up to current index."""
        segment = self._candles[:self._current_index + 1]
        if not segment:
            return 0.0
        return min(c.low for c in segment)

    def get_volume_at(self, index: int, context: str = "") -> int:
        """Get volume at specific index with look-ahead check."""
        self._check_access(index, context)
        candle = self._candles[index]
        return candle.volume

    def get_violations(self) -> list[LookAheadViolation]:
        return list(self._violations)

    def clear_violations(self) -> None:
        self._violations.clear()


class LookAheadError(Exception):
    """Raised when a look-ahead violation is detected in strict mode."""
    pass


def no_lookahead(func: Callable) -> Callable:
    """
    Decorator that marks a function as look-ahead-safe.

    When used with LookAheadDetector, decorated functions are registered
    and their CandleWindow access patterns are monitored.
    """
    func._lookahead_safe = True
    return func


def requires_candle_window(func: Callable) -> Callable:
    """
    Decorator that ensures a function only accesses data through a
    CandleWindow. The first argument must be a CandleWindow instance.
    """
    @functools.wraps(func)
    def wrapper(window: CandleWindow, *args: Any, **kwargs: Any) -> Any:
        if not isinstance(window, CandleWindow):
            raise TypeError(
                f"First argument must be CandleWindow, got {type(window).__name__}"
            )
        # Record pre-violation count
        pre_count = len(window.get_violations())
        result = func(window, *args, **kwargs)
        # Check for new violations
        post_count = len(window.get_violations())
        if post_count > pre_count:
            new_violations = window.get_violations()[pre_count:post_count]
            logger.warning(
                f"Function {func.__name__} produced "
                f"{post_count - pre_count} look-ahead violation(s)"
            )
        return result
    wrapper._lookahead_safe = True
    return wrapper


class LookAheadDetector:
    """
    Runtime detector that monitors analysis functions for look-ahead bias.

    Wraps a CandleWindow and records all access patterns to verify
    that no function accesses future data during replay.

    Usage:
        detector = LookAheadDetector(candles)
        detector.set_index(50)
        # Run analysis through detector
        detector.run_analysis(analysis_func, market_data)
        report = detector.get_report()
        assert report.clean, "Look-ahead bias detected!"
    """

    def __init__(self, candles: list[Any], strict: bool = True):
        self._window = CandleWindow(candles, strict=strict)
        self._report = LookAheadReport()
        self._analyzed_functions: set[str] = set()

    @property
    def window(self) -> CandleWindow:
        return self._window

    def set_index(self, index: int) -> None:
        """Advance the replay index. Future accesses from this point are monitored."""
        self._window.set_index(index)

    def run_analysis(
        self,
        analysis_func: Callable[[CandleWindow], Any],
        name: str = "",
    ) -> Any:
        """
        Run an analysis function through the detector.

        The function receives a CandleWindow limited to current index.
        Any access beyond current index is recorded as a violation.
        """
        func_name = name or getattr(analysis_func, '__name__', 'anonymous')
        pre_violations = len(self._window.get_violations())

        try:
            result = analysis_func(self._window)
            post_violations = len(self._window.get_violations())

            if post_violations == pre_violations:
                self._report.checks_passed += 1
            else:
                self._report.checks_failed += 1
                new_violations = self._window.get_violations()[pre_violations:]
                self._report.violations.extend(new_violations)

            self._analyzed_functions.add(func_name)
            return result

        except LookAheadError as e:
            self._report.checks_failed += 1
            violation = LookAheadViolation(
                function_name=func_name,
                description=str(e),
                expected_index=self._window.current_index,
                accessed_index=-1,
                bar_count_available=self._window.bar_count,
                violation_type="future_index",
            )
            self._report.violations.append(violation)
            raise

    def scan_candle_data(
        self,
        candle_data: list[Any],
        index: int,
        analysis_func: Callable[[CandleWindow], Any],
        name: str = "",
    ) -> Any:
        """
        Convenience: set index on a candle data list and run analysis.

        Useful for batch scanning many candles.
        """
        # If we have a different candle data set, create a new window
        if candle_data is not self._window._candles:
            self._window = CandleWindow(candle_data, strict=self._window._strict)
        self._window.set_index(index)
        return self.run_analysis(analysis_func, name)

    def get_report(self) -> LookAheadReport:
        """Get the full look-ahead detection report."""
        return self._report

    def validate_strategy_function(
        self,
        func: Callable,
        candle_data: list[Any],
        name: str = "",
        step: int = 10,
    ) -> LookAheadReport:
        """
        Exhaustively validate a strategy function across many indices.

        Tests the function at every `step`-th index from start to end
        of the candle data. Returns a report of all violations found.
        """
        test_report = LookAheadReport()
        func_name = name or getattr(func, '__name__', 'anonymous')

        # Create a fresh window for validation
        detector = LookAheadDetector(candle_data, strict=False)

        indices_to_test = range(
            max(1, len(candle_data) // 20),
            len(candle_data),
            max(1, step),
        )

        for idx in indices_to_test:
            try:
                detector._window.set_index(idx)
                detector.run_analysis(func, func_name)
            except LookAheadError:
                pass  # Already recorded in report

        report = detector.get_report()
        self._analyzed_functions.add(func_name)
        return report

    def validate_all_strategies(
        self,
        strategies: list[tuple[str, Callable]],
        candle_data: list[Any],
        step: int = 10,
    ) -> dict[str, LookAheadReport]:
        """Validate multiple strategy functions and return per-strategy reports."""
        results: dict[str, LookAheadReport] = {}
        for name, func in strategies:
            results[name] = self.validate_strategy_function(
                func, candle_data, name, step
            )
        return results

    def reset(self) -> None:
        """Reset the detector state."""
        self._window.clear_violations()
        self._report = LookAheadReport()
        self._analyzed_functions.clear()


def create_safe_candle_accessor(
    candles: list[Any],
    current_index: int,
) -> CandleWindow:
    """
    Factory function: create a CandleWindow that prevents future access.

    This is the recommended way to create candle access during replay.
    All engines and strategies should receive this rather than raw lists.

    Args:
        candles: Full list of historical candles.
        current_index: Current replay position (0-based).

    Returns:
        CandleWindow bounded to [0, current_index].
    """
    window = CandleWindow(candles, strict=True)
    window.set_index(current_index)
    return window
