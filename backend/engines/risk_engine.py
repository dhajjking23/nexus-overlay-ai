"""
NEXUS OVERLAY AI - Risk Engine
Pre-trade validation gate.
"""
from __future__ import annotations
import logging
from typing import Any
from backend.models import RiskValidation, MarketRegime, now_ms

logger = logging.getLogger(__name__)


class RiskEngine:
    def __init__(self, config: dict[str, Any] | None = None, event_bus=None):
        self._config = config or {}
        self._event_bus = event_bus
        rc = self._config.get("risk", {})
        self._min_rr = rc.get("min_rr", 1.5)
        self._min_conf = rc.get("min_confidence", 70)
        self._max_spread = rc.get("max_spread", 1.0)
        self._stale_threshold = self._config.get("safety", {}).get("stale_data_threshold_ms", 10000)

    def validate(self, spread: float, volatility_atr: float, rr: float,
                 sl_distance: float, tp1_distance: float,
                 regime: MarketRegime | dict | str, data_quality: float,
                 session_active: bool, signal_age_candles: int,
                 mtf_conflicts: int, last_tick_age_ms: int) -> RiskValidation:
        checks: dict[str, bool] = {}
        failed: list[str] = []

        checks["spread"] = spread <= self._max_spread
        if not checks["spread"]:
            failed.append(f"Spread {spread:.2f} > max {self._max_spread}")

        checks["min_rr"] = rr >= self._min_rr
        if not checks["min_rr"]:
            failed.append(f"RR {rr:.2f} < min {self._min_rr}")

        checks["sl_distance"] = sl_distance > 0.05
        if not checks["sl_distance"]:
            failed.append(f"SL distance too small: {sl_distance:.2f}")

        checks["tp_distance"] = tp1_distance > 0.05
        if not checks["tp_distance"]:
            failed.append(f"TP1 distance too small: {tp1_distance:.2f}")

        checks["regime"] = not (regime in (MarketRegime.UNCERTAIN, "UNCERTAIN") if hasattr(regime, 'value') else str(regime) == "UNCERTAIN")
        if not checks["regime"]:
            failed.append(f"Regime uncertain: {regime}")

        checks["data_freshness"] = data_quality >= 50
        if not checks["data_freshness"]:
            failed.append(f"Data quality low: {data_quality:.1f}")

        checks["session"] = session_active
        if not checks["session"]:
            failed.append("No active trading session")

        checks["signal_age"] = signal_age_candles <= 5
        if not checks["signal_age"]:
            failed.append(f"Signal too old: {signal_age_candles} candles")

        checks["mtf_conflicts"] = mtf_conflicts <= 2
        if not checks["mtf_conflicts"]:
            failed.append(f"Too many MTF conflicts: {mtf_conflicts}")

        checks["data_stale"] = last_tick_age_ms <= self._stale_threshold
        if not checks["data_stale"]:
            failed.append(f"Data stale: {last_tick_age_ms}ms old")

        checks["abnormal_vol"] = volatility_atr <= 100  # arbitrary cap
        if not checks["abnormal_vol"]:
            failed.append(f"Abnormal volatility: {volatility_atr:.2f}")

        passed = all(checks.values())
        return RiskValidation(
            passed=passed, checks=checks, failed_reasons=failed,
            rr=rr, min_rr=self._min_rr, spread=spread, max_spread=self._max_spread,
            data_quality=data_quality, timestamp=now_ms()
        )