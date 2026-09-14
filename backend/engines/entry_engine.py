"""
NEXUS OVERLAY AI - Entry Engine
Calculates entry type and price.
"""
from __future__ import annotations
import logging
from typing import Any
from backend.models import (
    CandleData, EntryCalculation, EntryType, MarketStructure,
    PriceActionPattern, Zone, MarketRegime, TrendDirection, now_ms
)

logger = logging.getLogger(__name__)


class EntryEngine:
    def __init__(self, config: dict[str, Any] | None = None, event_bus=None):
        self._config = config or {}
        self._event_bus = event_bus
        ec = self._config.get("entry", {})
        self._confirmation_candles = ec.get("confirmation_candles", 1)
        self._retest_tolerance = ec.get("retest_tolerance_pips", 2.0) * 0.01

    def calculate(self, candles: list[CandleData], structure: MarketStructure | None,
                  zones: list[Zone], regime: MarketRegime | dict | str,
                  price_action: list[PriceActionPattern] | None = None) -> EntryCalculation:
        if not candles:
            return EntryCalculation(
                entry_type=EntryType.MARKET, price=0.0,
                reason="no_data", confirmation_candles=0, timestamp=now_ms())
        current = candles[-1].close
        if structure and structure.trend != TrendDirection.NEUTRAL:
            entry_type = EntryType.CONFIRMATION
            reason = f"structure_{structure.trend.value.lower()}"
        elif zones:
            zone = zones[0]
            if abs(current - zone.midpoint) < self._retest_tolerance:
                entry_type = EntryType.ZONE
                reason = f"zone_retest_{zone.zone_type.value}"
            else:
                entry_type = EntryType.LIMIT
                reason = f"limit_at_zone_{zone.zone_type.value}"
        elif price_action:
            pa = price_action[0]
            entry_type = EntryType.CONFIRMATION
            reason = f"pa_{pa.pattern.value.lower()}"
        else:
            entry_type = EntryType.MARKET
            reason = "market"
        return EntryCalculation(
            entry_type=entry_type, price=current, reason=reason,
            confirmation_candles=self._confirmation_candles, timestamp=now_ms()
        )