"""
NEXUS OVERLAY AI - Decision Eligibility Engine

Determines whether the system is LEGALLY ALLOWED to produce a trade decision.
This is the final gate before any BUY/SELL/WAIT decision is emitted.

Design ref: audit section 31 (decision eligibility), section 79 (TradeThesis gates)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class EligibilityStatus(Enum):
    """Whether a decision can be legally produced."""
    ELIGIBLE = "ELIGIBLE"                    # All gates passed
    INELIGIBLE_DATA = "INELIGIBLE_DATA"      # Data quality/staleness
    INELIGIBLE_MARKET = "INELIGIBLE_MARKET"  # Market closed, no liquidity
    INELIGIBLE_TRANSPORT = "INELIGIBLE_TRANSPORT"  # Transport disconnected
    INELIGIBLE_RISK = "INELIGIBLE_RISK"      # Risk gates failed
    INELIGIBLE_CONFLICT = "INELIGIBLE_CONFLICT"    # Critical MTF/directional conflict
    INELIGIBLE_SAFETY = "INELIGIBLE_SAFETY"  # Safety governor hard block
    INELIGIBLE_ENGINE = "INELIGIBLE_ENGINE"  # Critical engine in ERROR state
    INELIGIBLE_SETUP = "INELIGIBLE_SETUP"    # No valid setup detected
    INELIGIBLE_CONFIG = "INELIGIBLE_CONFIG"  # Config invalid or changed


@dataclass
class EligibilityCheck:
    """Result of a single eligibility gate."""
    gate_name: str
    passed: bool
    reason: str = ""
    severity: str = "INFO"  # INFO, WARNING, CRITICAL


@dataclass
class DecisionEligibilityResult:
    """Complete eligibility assessment."""
    status: EligibilityStatus
    checks: List[EligibilityCheck] = field(default_factory=list)
    can_decide: bool = False
    blocking_reasons: List[str] = field(default_factory=list)
    warning_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "can_decide": self.can_decide,
            "checks": [{"gate": c.gate_name, "passed": c.passed, "reason": c.reason, "severity": c.severity} for c in self.checks],
            "blocking_reasons": self.blocking_reasons,
            "warning_reasons": self.warning_reasons,
        }


class DecisionEligibility:
    """
    Final gate: Can we legally produce a trading decision?

    Checks in order (first blocking failure stops):
    1. CONFIG GATE: Config valid, not changed unexpectedly
    2. TRANSPORT GATE: MT5/WebSocket connected
    3. MARKET GATE: Market open, symbol available
    4. DATA GATE: Data quality, staleness, freshness
    5. ENGINE GATE: All critical engines READY/DEGRADED (not ERROR/OFFLINE)
    6. SAFETY GATE: Safety governor passes
    7. RISK GATE: Risk validation passes
    8. CONFLICT GATE: No CRITICAL MTF/directional conflict
    9. SETUP GATE: At least one valid setup exists

    If ANY gate is CRITICAL and fails -> INELIGIBLE, WAIT with reason.
    """

    def __init__(self, config: Optional[dict] = None) -> None:
        self._config = config or {}

    def check(
        self,
        # Config
        config_valid: bool = True,
        config_changed: bool = False,
        # Transport
        mt5_connected: bool = True,
        websocket_connected: bool = True,
        # Market
        market_open: bool = True,
        symbol_available: bool = True,
        # Data
        data_quality: float = 100.0,          # 0-100
        data_age_ms: int = 0,
        max_data_age_ms: int = 30000,
        bid: float = 0.0,
        ask: float = 0.0,
        spread: float = 0.0,
        max_spread: float = 100.0,
        # Engine health
        engine_states: dict = None,           # {engine_name: "READY"|"DEGRADED"|"ERROR"|"OFFLINE"}
        # Safety
        safety_passed: bool = True,
        safety_reasons: List[str] = None,
        # Risk
        risk_passed: bool = True,
        risk_reasons: List[str] = None,
        # Conflict
        mtf_alignment: str = "aligned",       # aligned, partial, conflicting
        directional_conflict: float = 0.0,    # 0-100
        max_directional_conflict: float = 70.0,
        # Setup
        has_valid_setup: bool = False,
        setup_types: List[str] = None,
    ) -> DecisionEligibilityResult:
        """
        Run all eligibility gates.
        """
        checks: List[EligibilityCheck] = []
        blocking: List[str] = []
        warnings: List[str] = []

        # Helper
        def add_check(name: str, passed: bool, reason: str = "", severity: str = "INFO"):
            checks.append(EligibilityCheck(name, passed, reason, severity))
            if not passed:
                if severity == "CRITICAL":
                    blocking.append(reason or name)
                else:
                    warnings.append(reason or name)

        # 1. CONFIG GATE
        if not config_valid:
            add_check("CONFIG", False, "Config validation failed", "CRITICAL")
        elif config_changed:
            add_check("CONFIG_CHANGED", False, "Config changed during runtime", "CRITICAL")
        else:
            add_check("CONFIG", True, "Config valid and stable")

        # 2. TRANSPORT GATE
        if not mt5_connected:
            add_check("TRANSPORT_MT5", False, "MT5 bridge disconnected", "CRITICAL")
        else:
            add_check("TRANSPORT_MT5", True, "MT5 connected")
        if not websocket_connected:
            add_check("TRANSPORT_WS", False, "WebSocket transport disconnected", "CRITICAL")
        else:
            add_check("TRANSPORT_WS", True, "WebSocket connected")

        # 3. MARKET GATE
        if not market_open:
            add_check("MARKET_OPEN", False, "Market is closed", "CRITICAL")
        else:
            add_check("MARKET_OPEN", True, "Market open")
        if not symbol_available:
            add_check("SYMBOL", False, "Symbol not available", "CRITICAL")
        else:
            add_check("SYMBOL", True, "Symbol available")

        # 4. DATA GATE
        if bid <= 0 or ask <= 0:
            add_check("DATA_PRICE", False, "Invalid price data (bid/ask <= 0)", "CRITICAL")
        else:
            add_check("DATA_PRICE", True, "Valid price data")

        if data_quality < 30.0:  # Hard floor
            add_check("DATA_QUALITY", False, f"Data quality {data_quality:.0f} below minimum 30", "CRITICAL")
        elif data_quality < 60.0:
            add_check("DATA_QUALITY", True, f"Data quality {data_quality:.0f} (degraded)", "WARNING")
            warnings.append(f"Data quality degraded: {data_quality:.0f}/100")
        else:
            add_check("DATA_QUALITY", True, f"Data quality {data_quality:.0f}")

        if data_age_ms > max_data_age_ms:
            add_check("DATA_STALENESS", False, f"Data age {data_age_ms}ms > max {max_data_age_ms}ms", "CRITICAL")
        else:
            add_check("DATA_STALENESS", True, f"Data age {data_age_ms}ms OK")

        if spread > max_spread:
            add_check("DATA_SPREAD", False, f"Spread {spread:.2f} > max {max_spread:.2f}", "CRITICAL")
        else:
            add_check("DATA_SPREAD", True, f"Spread {spread:.2f} OK")

        # 5. ENGINE GATE
        if engine_states:
            for name, state in engine_states.items():
                if state == "ERROR":
                    add_check(f"ENGINE_{name.upper()}", False, f"Engine {name} in ERROR state", "CRITICAL")
                elif state == "OFFLINE":
                    add_check(f"ENGINE_{name.upper()}", False, f"Engine {name} is OFFLINE", "CRITICAL")
                elif state == "DEGRADED":
                    add_check(f"ENGINE_{name.upper()}", True, f"Engine {name} DEGRADED", "WARNING")
                    warnings.append(f"Engine {name} degraded")
                else:
                    add_check(f"ENGINE_{name.upper()}", True, f"Engine {name} READY")
        else:
            add_check("ENGINES", True, "No engine states provided (legacy mode)")

        # 6. SAFETY GATE
        if not safety_passed:
            add_check("SAFETY", False, f"Safety governor: {'; '.join(safety_reasons or ['unknown'])}", "CRITICAL")
        else:
            add_check("SAFETY", True, "Safety governor passed")

        # 7. RISK GATE
        if not risk_passed:
            add_check("RISK", False, f"Risk validation: {'; '.join(risk_reasons or ['unknown'])}", "CRITICAL")
        else:
            add_check("RISK", True, "Risk validation passed")

        # 8. CONFLICT GATE
        if mtf_alignment == "conflicting":
            add_check("CONFLICT_MTF", False, "MTF alignment: CONFLICTING", "CRITICAL")
        elif mtf_alignment == "partial":
            add_check("CONFLICT_MTF", True, "MTF alignment: PARTIAL", "WARNING")
            warnings.append("MTF partially aligned")

        if directional_conflict > max_directional_conflict:
            add_check("CONFLICT_DIRECTIONAL", False, f"Directional conflict {directional_conflict:.0f} > max {max_directional_conflict:.0f}", "CRITICAL")
        elif directional_conflict > max_directional_conflict * 0.7:
            add_check("CONFLICT_DIRECTIONAL", True, f"Directional conflict {directional_conflict:.0f} (elevated)", "WARNING")
            warnings.append(f"Elevated directional conflict: {directional_conflict:.0f}")

        # 9. SETUP GATE
        if not has_valid_setup:
            add_check("SETUP", False, "No valid trading setup detected", "CRITICAL")
        else:
            add_check("SETUP", True, f"Valid setup(s): {', '.join(setup_types or ['unknown'])}")

        # Determine final status
        if blocking:
            status = EligibilityStatus.INELIGIBLE_DATA
            for reason in blocking:
                if "MT5" in reason or "WebSocket" in reason or "TRANSPORT" in reason:
                    status = EligibilityStatus.INELIGIBLE_TRANSPORT
                    break
                elif "MARKET" in reason or "SYMBOL" in reason:
                    status = EligibilityStatus.INELIGIBLE_MARKET
                    break
                elif "DATA" in reason or "STALE" in reason or "SPREAD" in reason or "QUALITY" in reason:
                    status = EligibilityStatus.INELIGIBLE_DATA
                    break
                elif "ENGINE" in reason:
                    status = EligibilityStatus.INELIGIBLE_ENGINE
                    break
                elif "SAFETY" in reason:
                    status = EligibilityStatus.INELIGIBLE_SAFETY
                    break
                elif "RISK" in reason:
                    status = EligibilityStatus.INELIGIBLE_RISK
                    break
                elif "CONFLICT" in reason and "MTF" in reason:
                    status = EligibilityStatus.INELIGIBLE_CONFLICT
                    break
                elif "CONFLICT" in reason:
                    status = EligibilityStatus.INELIGIBLE_CONFLICT
                    break
                elif "SETUP" in reason:
                    status = EligibilityStatus.INELIGIBLE_SETUP
                    break
                elif "CONFIG" in reason:
                    status = EligibilityStatus.INELIGIBLE_CONFIG
                    break
        else:
            status = EligibilityStatus.ELIGIBLE

        return DecisionEligibilityResult(
            status=status,
            checks=checks,
            can_decide=len(blocking) == 0,
            blocking_reasons=blocking,
            warning_reasons=warnings,
        )


# Re-export
__all__ = [
    "DecisionEligibility",
    "EligibilityStatus",
    "EligibilityCheck",
    "DecisionEligibilityResult",
]