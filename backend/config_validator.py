"""
NEXUS OVERLAY AI - Configuration Validator

Validates configuration at startup to catch misconfiguration early.
Fail-fast on critical errors. Collect warnings for non-critical issues.

Usage:
    from backend.config_validator import validate_config
    result = validate_config(config_dict)
    if not result.ok():
        logger.critical(f"Config validation failed: {result.errors}")
        sys.exit(1)
"""
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("nexus_overlay.config_validator")


# ── Required sections and their expected types ────────────────────────
# Each entry: (section_name, expected_type_or_None, is_critical)
# expected_type_or_None: None means any dict, otherwise the expected type.
REQUIRED_SECTIONS: list[tuple[str, type | None, bool]] = [
    ("system", dict, True),
    ("symbol", dict, True),
    ("timeframes", dict, True),
    ("transport", dict, True),
    ("security", dict, True),
    ("indicators", dict, True),
    ("structure", dict, True),
    ("liquidity", dict, True),
    ("zones", dict, True),
    ("sessions", dict, True),
    ("regime", dict, True),
    ("strategies", dict, True),
    ("confluence", dict, True),
    ("risk", dict, True),
    ("entry", dict, True),
    ("sl", dict, True),
    ("tp", dict, True),
    ("ai", dict, True),
    ("decision", dict, True),
    ("signal", dict, True),
    ("data_quality", dict, True),
    ("safety", dict, True),
    ("database", dict, True),
    ("alerts", dict, False),
    ("performance", dict, False),
    ("config_lock", dict, False),
]

# Critical fields that must exist within sections: (path, expected_type)
CRITICAL_FIELDS: list[tuple[str, type | tuple[type, ...]]] = [
    ("system.version", str),
    ("system.log_level", str),
    ("symbol.name", str),
    ("transport.host", str),
    ("transport.port", int),
    ("security.auth_enabled", bool),
    ("ai.enabled", bool),
    ("risk.min_rr", (int, float)),
    ("risk.max_spread", (int, float)),
    ("database.type", str),
]

# Valid ranges for numeric fields: (path, min_val, max_val)
NUMERIC_RANGES: list[tuple[str, float, float]] = [
    ("transport.port", 1, 65535),
    ("transport.http_port", 1, 65535),
    ("transport.health_port", 1, 65535),
    ("risk.min_rr", 0.1, 100.0),
    ("risk.max_spread", 0.0, 100.0),
    ("risk.max_risk_per_trade_pct", 0.01, 100.0),
    ("risk.max_daily_trades", 1, 1000),
    ("sl.atr_multiplier", 0.1, 10.0),
    ("sl.min_sl_pips", 0.0, 1000.0),
    ("sl.max_sl_pips", 0.0, 1000.0),
    ("indicators.momentum.rsi_period", 2, 500),
    ("indicators.momentum.rsi_oversold", 0, 50),
    ("indicators.momentum.rsi_overbought", 50, 100),
]

# Transport binding must be internal
ALLOWED_HOSTS: set[str] = {"127.0.0.1", "localhost", "::1"}


@dataclass
class ConfigValidationResult:
    """Result of config validation."""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def ok(self) -> bool:
        """True if no critical errors."""
        return len(self.errors) == 0

    def add_error(self, msg: str) -> None:
        self.errors.append(f"ERROR: {msg}")

    def add_warning(self, msg: str) -> None:
        self.warnings.append(f"WARNING: {msg}")


def _get_nested(d: dict, path: str) -> Any:
    """Get a nested value from dict using dot-separated path."""
    keys = path.split(".")
    current = d
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    return current


def validate_config(config: dict) -> ConfigValidationResult:
    """
    Validate the entire configuration dict.

    Checks:
      1. All required sections exist
      2. Types are correct for critical fields
      3. Numeric ranges are valid
      4. Transport binding is internal-only
      5. No unknown critical issues

    Returns ConfigValidationResult with errors and warnings.
    """
    result = ConfigValidationResult()

    if not config:
        result.add_error("Configuration is empty or None")
        return result

    # ── 1. Required sections ──────────────────────────────────────
    for section_name, expected_type, is_critical in REQUIRED_SECTIONS:
        if section_name not in config:
            msg = f"Missing required section: '{section_name}'"
            if is_critical:
                result.add_error(msg)
            else:
                result.add_warning(msg)
            continue

        if expected_type is not None:
            if not isinstance(config[section_name], expected_type):
                result.add_error(
                    f"Section '{section_name}' expected {expected_type.__name__}, "
                    f"got {type(config[section_name]).__name__}"
                )

    # ── 2. Critical field types ───────────────────────────────────
    for field_path, expected_type in CRITICAL_FIELDS:
        value = _get_nested(config, field_path)
        if value is None:
            result.add_error(f"Missing critical field: '{field_path}'")
            continue

        if not isinstance(expected_type, tuple):
            expected_type = (expected_type,)

        if not isinstance(value, expected_type):
            type_names = "/".join(t.__name__ for t in expected_type)
            result.add_error(
                f"Field '{field_path}' expected {type_names}, "
                f"got {type(value).__name__}: {value!r}"
            )

    # ── 3. Numeric ranges ─────────────────────────────────────────
    for field_path, min_val, max_val in NUMERIC_RANGES:
        value = _get_nested(config, field_path)
        if value is None:
            continue  # Already caught as missing field if critical
        try:
            num = float(value)
            if num < min_val or num > max_val:
                result.add_error(
                    f"Field '{field_path}' = {num} is outside valid range "
                    f"[{min_val}, {max_val}]"
                )
        except (TypeError, ValueError):
            result.add_error(
                f"Field '{field_path}' = {value!r} is not a valid number"
            )

    # ── 4. Transport binding (security check) ─────────────────────
    transport_host = _get_nested(config, "transport.host")
    if transport_host is not None:
        if str(transport_host) not in ALLOWED_HOSTS:
            result.add_error(
                f"Transport host '{transport_host}' is externally bound! "
                f"Must use one of {ALLOWED_HOSTS} for internal-only binding. "
                f"Use reverse proxy (nginx/caddy) for public access."
            )

    # ── 5. AI configuration sanity ────────────────────────────────
    ai_enabled = _get_nested(config, "ai.enabled")
    if ai_enabled is True:
        result.add_warning(
            "AI is enabled in default config. Consider setting ai.enabled=false "
            "unless you have configured an AI provider key."
        )

    # ── 6. Security sanity ────────────────────────────────────────
    auth_enabled = _get_nested(config, "security.auth_enabled")
    if auth_enabled is False:
        result.add_warning(
            "Authentication is DISABLED. This is unsafe for production."
        )

    # ── 7. HMAC secret check ──────────────────────────────────────
    hmac_secret = _get_nested(config, "security.hmac_secret")
    if auth_enabled and (not hmac_secret or hmac_secret == ""):
        result.add_warning(
            "Security auth_enabled=true but hmac_secret is empty. "
            "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
        )

    # Log results
    if result.errors:
        for err in result.errors:
            logger.error(f"[Config Validation] {err}")
    if result.warnings:
        for warn in result.warnings:
            logger.warning(f"[Config Validation] {warn}")

    return result


def fail_fast_validate(config: dict) -> ConfigValidationResult:
    """
    Validate config and exit on critical errors.
    Use during startup to ensure configuration is valid before proceeding.
    """
    result = validate_config(config)
    if not result.ok():
        logger.critical(
            f"Configuration validation FAILED with {len(result.errors)} error(s). "
            f"Fix the errors above and restart."
        )
        for err in result.errors:
            logger.critical(f"  {err}")
        sys.exit(1)
    else:
        logger.info(
            f"Configuration validation PASSED "
            f"({len(result.warnings)} warning(s))"
        )
    return result
