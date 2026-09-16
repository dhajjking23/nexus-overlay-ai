"""
NEXUS OVERLAY AI - Score Normalization Utilities
Centralized score normalization to enforce the 0-100 scale globally.

Contract: ALL scores in the system are on 0-100 scale unless explicitly
documented otherwise. These utilities prevent scale drift.

Scale definitions:
  - decision_score: 0-100 (the final composite score for a trade decision)
  - data_quality: 0-100 (how fresh/complete/clean the market data is)
  - confluence_score: 0-100 (how much evidence agrees on a direction)
  - confidence_model: 0-100 (composite confidence from weighted components)
  - strategy_score: 0-100 (individual strategy assessment strength)
  - risk_score: 0-100 (risk quality assessment)
"""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)


def clamp_0_100(value: float) -> float:
    """Clamp a numeric value to the [0, 100] range.
    This is the universal guard — use it before any score comparison."""
    return max(0.0, min(100.0, value))


def clamp_0_1(value: float) -> float:
    """Clamp a numeric value to the [0.0, 1.0] range (for probabilities/ratios)."""
    return max(0.0, min(1.0, value))


def to_100_scale(value: float, current_min: float = 0.0, current_max: float = 1.0) -> float:
    """Convert a value from an arbitrary range to 0-100.

    Common use case: normalizing a 0-1 probability to 0-100.
    If current_min=0 and current_max=1 (default), this maps 0→0, 0.5→50, 1→100.
    """
    if current_max == current_min:
        return 50.0  # Undefined range, return neutral
    normalized = (value - current_min) / (current_max - current_min) * 100.0
    return clamp_0_100(normalized)


def normalize_confidence(value: float, source_scale: str = "0-100") -> float:
    """Normalize a confidence value to 0-100, detecting the source scale.

    Args:
        value: The raw confidence value
        source_scale: The scale the value is currently on:
            "0-1" or "0-100"

    Returns:
        Confidence on 0-100 scale

    Raises:
        ValueError: If source_scale is unrecognized
    """
    if source_scale == "0-1":
        return clamp_0_100(value * 100.0)
    elif source_scale == "0-100":
        return clamp_0_100(value)
    else:
        raise ValueError(f"Unknown source_scale: {source_scale}")


def data_quality_check(value: float) -> float:
    """Validate and clamp a data quality score to 0-100.

    Data quality MUST be 0-100 throughout the system.
    If a 0-1 value is detected, it is logged as a warning and converted.
    """
    if 0.0 <= value <= 1.0 and value != 0.0:
        # Likely a 0-1 scale value slipped in — convert and warn
        logger.warning(
            f"Data quality value {value} appears to be on 0-1 scale. "
            f"Converting to 0-100 scale: {value * 100}"
        )
        return value * 100.0
    return clamp_0_100(value)


def data_quality_threshold(default_min: float = 50.0) -> float:
    """Return a data quality threshold on the 0-100 scale.

    The default_config.yaml uses thresholds on 0-100 scale.
    Old code used 0.3 (0-1 scale) which would pass almost everything.
    """
    return clamp_0_100(default_min)


def validate_score_range(value: float, name: str, expected_min: float = 0.0,
                         expected_max: float = 100.0) -> float:
    """Validate that a score is within the expected range and clamp if not.

    Logs a warning if the score was out of range (indicates a scale bug).
    """
    if value < expected_min or value > expected_max:
        logger.warning(
            f"Score '{name}' out of expected range [{expected_min}-{expected_max}]: "
            f"{value}. Clamping."
        )
        return max(expected_min, min(expected_max, value))
    return value
