"""
NEXUS OVERLAY AI - Confidence Model
Structured confidence calculation with documented weights.
"""
from __future__ import annotations
import logging
from typing import Any
from backend.models import ConfidenceModel, now_ms

logger = logging.getLogger(__name__)


class ConfidenceModelEngine:
    """Calculates structured confidence from multiple components.
    
    Formula:
        final_confidence = (
            technical_confluence * weight_technical +
            mtf_agreement * weight_mtf +
            risk_quality * weight_risk +
            data_quality * weight_data +
            ai_confidence * weight_ai
        )
    
    Default weights (sum = 1.0):
        technical: 0.35
        mtf:       0.25
        risk:      0.15
        data:      0.15
        ai:        0.10
    
    AI cannot override deterministic risk rules.
    If AI is unavailable (confidence = 0), remaining weights are rescaled.
    """

    def __init__(self, config: dict[str, Any] | None = None, event_bus=None):
        self._config = config or {}
        self._event_bus = event_bus
        dc = self._config.get("decision", {}).get("confidence_weights", {})
        self._w_tech = dc.get("technical_confluence", 0.35)
        self._w_mtf = dc.get("mtf_agreement", 0.25)
        self._w_risk = dc.get("risk_quality", 0.15)
        self._w_data = dc.get("data_quality", 0.15)
        self._w_ai = dc.get("ai_assessment", 0.10)

    def calculate(self, technical_confluence: float, mtf_agreement: float,
                  risk_quality: float, data_quality: float,
                  ai_confidence: float) -> ConfidenceModel:
        technical = max(0, min(100, technical_confluence))
        mtf = max(0, min(100, mtf_agreement))
        risk = max(0, min(100, risk_quality))
        dq = max(0, min(100, data_quality))
        ai = max(0, min(100, ai_confidence))
        if ai == 0:
            w_sum = self._w_tech + self._w_mtf + self._w_risk + self._w_data
            if w_sum > 0:
                final = (technical * self._w_tech + mtf * self._w_mtf +
                         risk * self._w_risk + dq * self._w_data) / w_sum
            else:
                final = (technical + mtf + risk + dq) / 4
        else:
            total_w = self._w_tech + self._w_mtf + self._w_risk + self._w_data + self._w_ai
            final = (technical * self._w_tech + mtf * self._w_mtf +
                     risk * self._w_risk + dq * self._w_data + ai * self._w_ai) / total_w
        final = max(0, min(100, round(final, 2)))
        return ConfidenceModel(
            technical_score=technical, risk_score=risk,
            data_quality_score=dq, ai_confidence=ai,
            mtf_agreement=mtf, final_confidence=final, timestamp=now_ms()
        )