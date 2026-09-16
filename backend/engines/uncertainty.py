"""
NEXUS OVERLAY AI - Uncertainty Engine

Quantifies directional ambiguity and explicit uncertainty levels for trading decisions.
This replaces the binary "confident/not confident" with a structured uncertainty assessment.

Design ref: audit section 33 (uncertainty quantification), section 80 (reason codes)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class UncertaintyLevel(Enum):
    """Explicit uncertainty tiers."""
    NONE = "NONE"              # Clear directional bias
    LOW = "LOW"                # Minor ambiguity
    MODERATE = "MODERATE"      # Meaningful ambiguity
    HIGH = "HIGH"              # Conflicting evidence
    EXTREME = "EXTREME"        # No reliable signal


@dataclass
class UncertaintyFactor:
    """Single contributor to uncertainty."""
    name: str
    weight: float          # 0.0 - 1.0 contribution weight
    value: float           # 0.0 - 100.0 uncertainty score
    description: str = ""


@dataclass
class UncertaintyAssessment:
    """Complete uncertainty analysis for a decision."""
    overall_level: UncertaintyLevel
    composite_score: float          # 0-100 (0 = certain, 100 = maximum uncertainty)
    factors: List[UncertaintyFactor] = field(default_factory=list)
    directional_ambiguity: float = 0.0   # 0-100: how much bullish/bearish evidence conflicts
    missing_confirmation: List[str] = field(default_factory=list)
    invalidation_risks: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "overall_level": self.overall_level.value,
            "composite_score": round(self.composite_score, 1),
            "directional_ambiguity": round(self.directional_ambiguity, 1),
            "factors": [{"name": f.name, "weight": f.weight, "value": f.value, "description": f.description} for f in self.factors],
            "missing_confirmation": self.missing_confirmation,
            "invalidation_risks": self.invalidation_risks,
        }


class UncertaintyEngine:
    """
    Calculates explicit uncertainty for trade decisions.

    Uncertainty sources:
    - MTF conflict (higher timeframe vs entry timeframe)
    - Directional conflict (bullish vs bearish evidence balance)
    - Data quality degradation
    - Spread/volatility anomaly
    - Signal age / staleness
    - Missing confirmations (e.g., no BOS, no liquidity sweep)
    - Invalidation risk proximity
    """

    def __init__(self, config: Optional[dict] = None) -> None:
        self._config = config or {}
        # Weights for each uncertainty factor (sum ≈ 1.0)
        self._weights = {
            "mtf_conflict": 0.25,
            "directional_conflict": 0.20,
            "data_quality": 0.15,
            "spread_volatility": 0.15,
            "signal_age": 0.10,
            "missing_confirmation": 0.10,
            "invalidation_proximity": 0.05,
        }

    def assess(
        self,
        bullish_score: float,              # 0-100
        bearish_score: float,              # 0-100
        mtf_alignment: str,                # "aligned" | "partial" | "conflicting"
        data_quality: float,               # 0-100
        spread: float,                     # current spread
        avg_spread: float,                 # normal spread
        volatility_atr: float,             # current ATR
        avg_atr: float,                    # normal ATR
        signal_age_candles: int,           # age in candles
        max_signal_age_candles: int,       # threshold
        missing_confirmations: List[str],  # e.g., ["BOS", "LIQUIDITY_SWEEP"]
        invalidation_distance_pips: float, # pips to invalidation
        sl_distance_pips: float,           # pips to SL
    ) -> UncertaintyAssessment:
        """
        Compute full uncertainty assessment.
        All scores 0-100 where higher = more uncertain.
        """
        factors: List[UncertaintyFactor] = []

        # 1. MTF Conflict
        mtf_uncertainty = {
            "aligned": 10.0,
            "partial": 45.0,
            "conflicting": 85.0,
        }.get(mtf_alignment, 50.0)
        factors.append(UncertaintyFactor(
            name="MTF Conflict",
            weight=self._weights["mtf_conflict"],
            value=mtf_uncertainty,
            description=f"MTF alignment: {mtf_alignment}"
        ))

        # 2. Directional Conflict (how balanced is bullish vs bearish)
        total_directional = bullish_score + bearish_score
        if total_directional > 0:
            directional_ambiguity = 100.0 * (1.0 - abs(bullish_score - bearish_score) / total_directional)
        else:
            directional_ambiguity = 100.0  # No directional evidence = maximum ambiguity
        factors.append(UncertaintyFactor(
            name="Directional Conflict",
            weight=self._weights["directional_conflict"],
            value=directional_ambiguity,
            description=f"Bullish: {bullish_score:.0f}, Bearish: {bearish_score:.0f}"
        ))

        # 3. Data Quality
        data_quality_uncertainty = 100.0 - data_quality
        factors.append(UncertaintyFactor(
            name="Data Quality",
            weight=self._weights["data_quality"],
            value=data_quality_uncertainty,
            description=f"Data quality: {data_quality:.0f}/100"
        ))

        # 4. Spread/Volatility Anomaly
        spread_ratio = spread / max(avg_spread, 0.01)
        vol_ratio = volatility_atr / max(avg_atr, 0.01)
        anomaly = max(spread_ratio, vol_ratio)
        spread_vol_uncertainty = min(100.0, (anomaly - 1.0) * 50.0)  # 50% per 1x anomaly
        factors.append(UncertaintyFactor(
            name="Spread/Volatility Anomaly",
            weight=self._weights["spread_volatility"],
            value=spread_vol_uncertainty,
            description=f"Spread ratio: {spread_ratio:.2f}, Vol ratio: {vol_ratio:.2f}"
        ))

        # 5. Signal Age
        if max_signal_age_candles > 0:
            age_ratio = signal_age_candles / max_signal_age_candles
            age_uncertainty = min(100.0, age_ratio * 100.0)
        else:
            age_uncertainty = 0.0
        factors.append(UncertaintyFactor(
            name="Signal Age",
            weight=self._weights["signal_age"],
            value=age_uncertainty,
            description=f"Signal age: {signal_age_candles}/{max_signal_age_candles} candles"
        ))

        # 6. Missing Confirmations
        missing_weight = min(100.0, len(missing_confirmations) * 20.0)  # 20 per missing
        factors.append(UncertaintyFactor(
            name="Missing Confirmations",
            weight=self._weights["missing_confirmation"],
            value=missing_weight,
            description=f"Missing: {', '.join(missing_confirmations) if missing_confirmations else 'None'}"
        ))

        # 7. Invalidation Proximity (how close is invalidation relative to SL)
        if sl_distance_pips > 0:
            inv_ratio = invalidation_distance_pips / sl_distance_pips
            inv_uncertainty = min(100.0, (1.0 - inv_ratio) * 100.0)  # Close invalidation = high uncertainty
        else:
            inv_uncertainty = 50.0
        factors.append(UncertaintyFactor(
            name="Invalidation Proximity",
            weight=self._weights["invalidation_proximity"],
            value=inv_uncertainty,
            description=f"Invalidation at {invalidation_distance_pips:.1f} pips, SL at {sl_distance_pips:.1f} pips"
        ))

        # Composite score (weighted sum)
        composite = sum(f.weight * f.value for f in factors)

        # Determine level
        if composite <= 15:
            level = UncertaintyLevel.NONE
        elif composite <= 30:
            level = UncertaintyLevel.LOW
        elif composite <= 55:
            level = UncertaintyLevel.MODERATE
        elif composite <= 75:
            level = UncertaintyLevel.HIGH
        else:
            level = UncertaintyLevel.EXTREME

        return UncertaintyAssessment(
            overall_level=level,
            composite_score=composite,
            factors=factors,
            directional_ambiguity=directional_ambiguity,
            missing_confirmation=missing_confirmations,
            invalidation_risks=[f"Invalidation within {invalidation_distance_pips:.1f} pips"] if invalidation_distance_pips < sl_distance_pips * 0.5 else [],
        )

    def quick_assess(self, thesis) -> UncertaintyAssessment:
        """
        Quick assessment from a TradeThesis object.
        """
        # Extract from thesis
        bullish = getattr(thesis, 'bullish_score', 50.0)
        bearish = getattr(thesis, 'bearish_score', 50.0)
        mtf = getattr(thesis, 'mtf_alignment', 'partial')
        dq = getattr(thesis, 'data_quality', 80.0)
        spread = getattr(thesis, 'spread', 0.3)
        avg_spread = getattr(thesis, 'avg_spread', 0.3)
        atr = getattr(thesis, 'volatility_atr', 2.0)
        avg_atr = getattr(thesis, 'avg_atr', 2.0)
        signal_age = getattr(thesis, 'signal_age_candles', 0)
        max_age = getattr(thesis, 'max_signal_age_candles', 10)
        missing = getattr(thesis, 'missing_confirmations', [])
        inv_dist = getattr(thesis, 'invalidation_distance_pips', 10.0)
        sl_dist = getattr(thesis, 'sl_distance_pips', 10.0)

        return self.assess(
            bullish_score=bullish,
            bearish_score=bearish,
            mtf_alignment=mtf,
            data_quality=dq,
            spread=spread,
            avg_spread=avg_spread,
            volatility_atr=atr,
            avg_atr=avg_atr,
            signal_age_candles=signal_age,
            max_signal_age_candles=max_age,
            missing_confirmations=missing,
            invalidation_distance_pips=inv_dist,
            sl_distance_pips=sl_dist,
        )


# Re-export for convenience
__all__ = [
    "UncertaintyEngine",
    "UncertaintyLevel",
    "UncertaintyFactor",
    "UncertaintyAssessment",
]