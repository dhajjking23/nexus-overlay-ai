"""
NEXUS OVERLAY AI - Safety Governor
Global safety layer that runs before the decision engine.

Checks:
  - Stale data
  - Excessive spread
  - Abnormal volatility
  - Insufficient risk-reward
  - Conflicting multi-timeframe analysis
  - Missing candle data
  - AI unavailable
  - Transport disconnected
  - Malformed data
  - Invalid prices

Can return WAIT. Never fabricates missing values.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from backend.models import (
    DecisionState,
    StrategyAssessment,
    RiskValidation,
    MultiTimeframeAnalysis,
    AIAssessment,
    CandleData,
    now_ms,
)
from backend.event_bus import EventType, get_event_bus
from backend.config_loader import get_config

logger = logging.getLogger(__name__)


@dataclass
class SafetyCheck:
    """Result of a single safety check."""
    name: str
    passed: bool
    severity: str  # INFO, WARNING, CRITICAL, BLOCK
    message: str
    timestamp: int = field(default_factory=now_ms)


@dataclass
class SafetyVerdict:
    """Aggregated safety verdict."""
    passed: bool  # overall pass/fail
    block: bool  # hard block (must WAIT)
    checks: list[SafetyCheck] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    timestamp: int = field(default_factory=now_ms)

    @property
    def warning_count(self) -> int:
        return sum(1 for c in self.checks if c.severity == "WARNING" and c.passed)

    @property
    def block_count(self) -> int:
        return sum(1 for c in self.checks if c.severity in ("BLOCK", "CRITICAL") and not c.passed)


class SafetyGovernor:
    """
    Global safety layer — the last line of defense before a trade.
    
    Runs before the decision engine. If any BLOCK-level check fails,
    the governor forces a WAIT decision regardless of what strategies say.
    
    NEVER fabricates missing values — if data is absent, that's a safety concern.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self._config = config or get_config().get_section("safety") or {}
        self._logger = logging.getLogger("nexus.engine.safety")
        self._running = False
        self._check_count = 0
        self._block_count = 0

        # Thresholds — all on 0-100 scale for data quality
        safety_cfg = self._config
        risk_cfg = (config or {}).get("risk", {})
        dq_cfg = (config or {}).get("data_quality", {})
        sym_cfg = (config or {}).get("symbol", {})
        self.max_spread_pips = safety_cfg.get("max_spread", risk_cfg.get("max_spread", 1.0)) / max(sym_cfg.get("point", 0.01), 0.0001)
        self.max_data_age_ms = risk_cfg.get("stale_data_threshold_ms", safety_cfg.get("stale_data_threshold_ms", 30_000))
        self.min_data_quality = dq_cfg.get("minimum_threshold", 50.0)  # 0-100 scale (was 0.3!)
        self.min_rr = risk_cfg.get("min_rr", safety_cfg.get("min_risk_reward", 1.0))
        self.max_volatility_mult = safety_cfg.get("max_volatility_atr_multiplier", 5.0)
        self.min_candles_required = safety_cfg.get("min_candles", 1)
        self.pip_value = sym_cfg.get("point", 0.01)  # for XAUUSD

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._logger.info("Safety governor started")

    async def stop(self) -> None:
        self._running = False
        self._logger.info("Safety governor stopped")

    def _add_check(
        self,
        checks: list[SafetyCheck],
        name: str,
        passed: bool,
        severity: str,
        message: str,
    ) -> None:
        checks.append(SafetyCheck(
            name=name,
            passed=passed,
            severity=severity,
            message=message,
        ))
        if not passed and severity in ("BLOCK", "CRITICAL"):
            self._block_count += 1

    def _spread_to_pips(self, spread: float) -> float:
        """Convert spread to pips."""
        return spread / self.pip_value if self.pip_value > 0 else spread

    async def validate(
        self,
        *,
        # Price data
        price: float = 0.0,
        bid: float = 0.0,
        ask: float = 0.0,
        spread: float = 0.0,
        # Data quality
        data_quality: float = 1.0,
        data_age_ms: int = 0,
        candle_count: int = 0,
        last_candle: Optional[CandleData] = None,
        # Transport
        transport_connected: bool = True,
        # Risk
        risk_validation: Optional[RiskValidation] = None,
        # MTF
        mtf: Optional[MultiTimeframeAnalysis] = None,
        # AI
        ai_assessment: Optional[AIAssessment] = None,
        ai_available: bool = True,
        # Market state
        market_open: bool = True,
        symbol: str = "XAUUSD",
        # Volatility
        current_volatility: float = 0.0,
        avg_volatility: float = 0.0,
    ) -> SafetyVerdict:
        """
        Run all safety checks. Returns SafetyVerdict.
        
        If verdict.block is True, the decision engine MUST produce WAIT.
        This method NEVER fabricates values — missing data is flagged.
        """
        self._check_count += 1
        checks: list[SafetyCheck] = []
        warnings: list[str] = []
        blocks: list[str] = []

        # ═══════════════════════════════════════════
        # 1. TRANSPORT CONNECTION
        # ═══════════════════════════════════════════
        if not transport_connected:
            self._add_check(
                checks, "transport", False, "BLOCK",
                "Transport disconnected — no live data"
            )
            blocks.append("Transport disconnected")
        else:
            self._add_check(
                checks, "transport", True, "INFO",
                "Transport connected"
            )

        # ═══════════════════════════════════════════
        # 2. MARKET OPEN
        # ═══════════════════════════════════════════
        if not market_open:
            self._add_check(
                checks, "market_open", False, "BLOCK",
                "Market is closed"
            )
            blocks.append("Market closed")
        else:
            self._add_check(
                checks, "market_open", True, "INFO",
                "Market is open"
            )

        # ═══════════════════════════════════════════
        # 3. VALID PRICES
        # ═══════════════════════════════════════════
        if price <= 0:
            self._add_check(
                checks, "valid_price", False, "BLOCK",
                f"Invalid price: {price}"
            )
            blocks.append(f"Invalid price: {price}")
        elif bid <= 0 or ask <= 0:
            self._add_check(
                checks, "valid_price", False, "BLOCK",
                f"Invalid bid/ask: bid={bid}, ask={ask}"
            )
            blocks.append(f"Invalid bid/ask: bid={bid}, ask={ask}")
        elif bid > ask and bid > 0 and ask > 0:
            self._add_check(
                checks, "valid_price", False, "BLOCK",
                f"Inverted spread: bid({bid}) > ask({ask})"
            )
            blocks.append(f"Inverted spread: bid > ask")
        else:
            self._add_check(
                checks, "valid_price", True, "INFO",
                f"Price valid: bid={bid:.2f}, ask={ask:.2f}"
            )

        # ═══════════════════════════════════════════
        # 4. SPREAD CHECK
        # ═══════════════════════════════════════════
        if spread < 0:
            self._add_check(
                checks, "spread", False, "BLOCK",
                f"Negative spread: {spread}"
            )
            blocks.append(f"Negative spread: {spread}")
        elif spread == 0:
            self._add_check(
                checks, "spread", False, "WARNING",
                "Spread is zero — possible data issue"
            )
            warnings.append("Spread is zero")
        else:
            spread_pips = self._spread_to_pips(spread)
            if spread_pips > self.max_spread_pips:
                self._add_check(
                    checks, "spread", False, "BLOCK",
                    f"Excessive spread: {spread_pips:.1f} pips > {self.max_spread_pips}"
                )
                blocks.append(f"Excessive spread: {spread_pips:.1f} pips")
            elif spread_pips > self.max_spread_pips * 0.7:
                self._add_check(
                    checks, "spread", True, "WARNING",
                    f"Wide spread: {spread_pips:.1f} pips (approaching limit)"
                )
                warnings.append(f"Wide spread: {spread_pips:.1f} pips")
            else:
                self._add_check(
                    checks, "spread", True, "INFO",
                    f"Spread OK: {spread_pips:.1f} pips"
                )

        # ═══════════════════════════════════════════
        # 5. DATA QUALITY
        # ═══════════════════════════════════════════
        if data_quality < self.min_data_quality:
            self._add_check(
                checks, "data_quality", False, "BLOCK",
                f"Data quality too low: {data_quality:.1f} < {self.min_data_quality}"
            )
            blocks.append(f"Data quality: {data_quality:.1f}")
        elif data_quality < self.min_data_quality * 1.5:
            self._add_check(
                checks, "data_quality", True, "WARNING",
                f"Data quality marginal: {data_quality:.1f}"
            )
            warnings.append(f"Data quality marginal: {data_quality:.1f}")
        else:
            self._add_check(
                checks, "data_quality", True, "INFO",
                f"Data quality OK: {data_quality:.1f}"
            )

        # ═══════════════════════════════════════════
        # 6. DATA STALENESS
        # ═══════════════════════════════════════════
        if data_age_ms > self.max_data_age_ms:
            self._add_check(
                checks, "data_stale", False, "BLOCK",
                f"Data stale: {data_age_ms}ms > {self.max_data_age_ms}ms"
            )
            blocks.append(f"Data stale: {data_age_ms}ms")
        elif data_age_ms > self.max_data_age_ms * 0.7:
            self._add_check(
                checks, "data_stale", True, "WARNING",
                f"Data aging: {data_age_ms}ms"
            )
            warnings.append(f"Data aging: {data_age_ms}ms")
        else:
            self._add_check(
                checks, "data_stale", True, "INFO",
                f"Data fresh: {data_age_ms}ms"
            )

        # ═══════════════════════════════════════════
        # 7. MISSING CANDLE DATA
        # ═══════════════════════════════════════════
        if candle_count < self.min_candles_required:
            self._add_check(
                checks, "candle_data", False, "BLOCK",
                f"Insufficient candles: {candle_count} < {self.min_candles_required}"
            )
            blocks.append(f"Insufficient candles: {candle_count}")
        else:
            self._add_check(
                checks, "candle_data", True, "INFO",
                f"Candle data OK: {candle_count} candles"
            )

        # Check candle integrity if available
        if last_candle is not None:
            if last_candle.open <= 0 or last_candle.high <= 0 or last_candle.low <= 0 or last_candle.close <= 0:
                self._add_check(
                    checks, "candle_integrity", False, "BLOCK",
                    f"Malformed candle: O={last_candle.open} H={last_candle.high} "
                    f"L={last_candle.low} C={last_candle.close}"
                )
                blocks.append("Malformed candle data")
            elif last_candle.high < last_candle.low:
                self._add_check(
                    checks, "candle_integrity", False, "BLOCK",
                    f"Invalid candle: high({last_candle.high}) < low({last_candle.low})"
                )
                blocks.append("Invalid candle: high < low")
            else:
                self._add_check(
                    checks, "candle_integrity", True, "INFO",
                    "Candle integrity OK"
                )

        # ═══════════════════════════════════════════
        # 8. ABNORMAL VOLATILITY
        # ═══════════════════════════════════════════
        if current_volatility > 0 and avg_volatility > 0:
            vol_ratio = current_volatility / avg_volatility
            if vol_ratio > self.max_volatility_mult:
                self._add_check(
                    checks, "volatility", False, "BLOCK",
                    f"Abnormal volatility: {vol_ratio:.1f}x average "
                    f"(current={current_volatility:.2f}, avg={avg_volatility:.2f})"
                )
                blocks.append(f"Abnormal volatility: {vol_ratio:.1f}x")
            elif vol_ratio > self.max_volatility_mult * 0.7:
                self._add_check(
                    checks, "volatility", True, "WARNING",
                    f"Elevated volatility: {vol_ratio:.1f}x average"
                )
                warnings.append(f"Elevated volatility: {vol_ratio:.1f}x")
            else:
                self._add_check(
                    checks, "volatility", True, "INFO",
                    f"Volatility normal: {vol_ratio:.1f}x average"
                )
        else:
            self._add_check(
                checks, "volatility", True, "INFO",
                "Volatility check skipped (no baseline)"
            )

        # ═══════════════════════════════════════════
        # 9. RISK-REWARD VALIDATION
        # ═══════════════════════════════════════════
        if risk_validation is not None:
            if not risk_validation.passed:
                self._add_check(
                    checks, "risk_reward", False, "BLOCK",
                    f"Risk validation failed: {', '.join(risk_validation.failed_reasons)}"
                )
                blocks.append(f"Risk rejected: {risk_validation.failed_reasons}")
            elif risk_validation.rr < self.min_rr:
                self._add_check(
                    checks, "risk_reward", False, "BLOCK",
                    f"Insufficient RR: {risk_validation.rr:.1f} < {self.min_rr}"
                )
                blocks.append(f"Insufficient RR: {risk_validation.rr:.1f}")
            else:
                self._add_check(
                    checks, "risk_reward", True, "INFO",
                    f"Risk OK: RR={risk_validation.rr:.1f}"
                )
        else:
            self._add_check(
                checks, "risk_reward", True, "WARNING",
                "Risk validation not provided — downstream must verify"
            )
            warnings.append("No risk validation available")

        # ═══════════════════════════════════════════
        # 10. CONFLICTING MTF
        # ═══════════════════════════════════════════
        if mtf is not None:
            if mtf.alignment == "conflicting":
                if len(mtf.conflicts) > 0:
                    self._add_check(
                        checks, "mtf_conflict", False, "WARNING",
                        f"MTF conflicting: {', '.join(mtf.conflicts)}"
                    )
                    warnings.append(f"MTF conflicts: {mtf.conflicts}")
                else:
                    self._add_check(
                        checks, "mtf_conflict", False, "WARNING",
                        "MTF alignment is 'conflicting' but no details"
                    )
                    warnings.append("MTF conflicting (no details)")
            else:
                self._add_check(
                    checks, "mtf_conflict", True, "INFO",
                    f"MTF alignment: {mtf.alignment}"
                )
        else:
            self._add_check(
                checks, "mtf_conflict", True, "WARNING",
                "MTF analysis not provided"
            )
            warnings.append("No MTF analysis")

        # ═══════════════════════════════════════════
        # 11. AI UNAVAILABLE
        # ═══════════════════════════════════════════
        if not ai_available:
            self._add_check(
                checks, "ai_available", False, "WARNING",
                "AI service unavailable"
            )
            warnings.append("AI unavailable")
        elif ai_assessment is not None:
            if ai_assessment.confidence < 0.3:
                self._add_check(
                    checks, "ai_confidence", False, "WARNING",
                    f"AI confidence very low: {ai_assessment.confidence:.2f}"
                )
                warnings.append(f"AI confidence low: {ai_assessment.confidence:.2f}")
            else:
                self._add_check(
                    checks, "ai_confidence", True, "INFO",
                    f"AI OK: provider={ai_assessment.provider.value}, "
                    f"confidence={ai_assessment.confidence:.2f}"
                )
        else:
            self._add_check(
                checks, "ai_available", True, "INFO",
                "AI assessment not yet available"
            )

        # ═══════════════════════════════════════════
        # 12. MALFORMED DATA (general)
        # ═══════════════════════════════════════════
        if price > 0 and bid > 0 and ask > 0:
            mid = (bid + ask) / 2
            price_drift = abs(price - mid) / mid * 100
            if price_drift > 1.0:
                self._add_check(
                    checks, "data_consistency", False, "BLOCK",
                    f"Price inconsistency: price={price:.2f} vs mid={mid:.2f} "
                    f"(drift={price_drift:.2f}%)"
                )
                blocks.append(f"Price drift: {price_drift:.2f}%")
            else:
                self._add_check(
                    checks, "data_consistency", True, "INFO",
                    "Data consistent"
                )
        else:
            self._add_check(
                checks, "data_consistency", True, "INFO",
                "Price consistency check skipped (missing values)"
            )

        # ═══════════════════════════════════════════
        # AGGREGATE VERDICT
        # ═══════════════════════════════════════════
        has_block = any(
            c.severity in ("BLOCK", "CRITICAL") and not c.passed for c in checks
        )

        verdict = SafetyVerdict(
            passed=not has_block,
            block=has_block,
            checks=checks,
            warnings=warnings,
            blocks=blocks,
        )

        if has_block:
            self._logger.warning(
                f"SAFETY BLOCK [{len(blocks)}]: {blocks}"
            )
            try:
                bus = get_event_bus()
                await bus.publish(
                    EventType.ERROR,
                    "safety_governor",
                    {
                        "type": "SAFETY_BLOCK",
                        "blocks": blocks,
                        "warnings": warnings,
                        "symbol": symbol,
                    },
                )
            except Exception as e:
                self._logger.error(f"Failed to emit safety block event: {e}")
        elif warnings:
            self._logger.info(
                f"Safety passed with {len(warnings)} warnings: {warnings}"
            )

        return verdict

    def _check_cfg(self, key: str, default):
        """Read a config value, checking both flat and nested ``safety:`` keys."""
        val = self._config.get(key)
        if val is not None:
            return val
        safety = self._config.get("safety", {})
        if isinstance(safety, dict):
            val = safety.get(key)
            if val is not None:
                return val
        return default

    def check(
        self,
        *,
        last_tick_age_ms: int = 0,
        spread: float = 0.0,
        volatility_atr: float = 0.0,
        atr_avg: float = 0.0,
        mtf_aligned: bool = True,
        data_quality: float = 100.0,
        connected: bool = True,
    ) -> dict:
        """
        Synchronous convenience check — backward-compatible interface.
        Returns {'passed': bool, 'failed_reasons': list[str]}.

        This is a simplified synchronous wrapper.  For the full safety
        audit (async, with event-bus publishing), use ``validate()``.
        """
        failed: list[str] = []

        # --- Transport ---
        if not connected:
            failed.append("Transport disconnected")

        # --- Stale data ---
        stale_threshold = self._check_cfg("stale_data_threshold_ms", 10_000)
        if last_tick_age_ms > stale_threshold:
            failed.append(
                f"Data stale: {last_tick_age_ms}ms > {stale_threshold}ms"
            )

        # --- Excessive spread ---
        max_spread = self._check_cfg("max_spread", 1.0)
        if spread > max_spread:
            failed.append(
                f"Excessive spread: {spread:.2f} > {max_spread}"
            )

        # --- Abnormal volatility ---
        if atr_avg > 0 and volatility_atr > 0:
            ratio = volatility_atr / atr_avg
            if ratio > self.max_volatility_mult:
                failed.append(
                    f"Abnormal volatility: {ratio:.1f}x average"
                )

        # --- Data quality ---
        if data_quality < self.min_data_quality:
            failed.append(
                f"Data quality too low: {data_quality:.1f} < {self.min_data_quality}"
            )

        return {
            "passed": len(failed) == 0,
            "failed_reasons": failed,
        }

    def get_stats(self) -> dict[str, Any]:
        """Get safety governor statistics."""
        return {
            "running": self._running,
            "check_count": self._check_count,
            "block_count": self._block_count,
            "config": {
                "max_spread_pips": self.max_spread_pips,
                "max_data_age_ms": self.max_data_age_ms,
                "min_data_quality": self.min_data_quality,
                "min_rr": self.min_rr,
                "max_volatility_mult": self.max_volatility_mult,
            },
        }