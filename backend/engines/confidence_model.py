"""
NEXUS OVERLAY AI - Confidence Model
Structured confidence calculation with documented weights.

DESIGN:
  deterministic_score — computed ONLY from technical, MTF, risk, data.
  AI has ZERO influence on this score.  When AI is unavailable,
  deterministic_score is *identical*.

  ai_advisory_score — a separate, optional layer produced by AI.
  It is informational only and never blended into deterministic_score.
"""
from __future__ import annotations
import logging
from typing import Any
from backend.models import ConfidenceModel, now_ms

logger = logging.getLogger(__name__)


class ConfidenceModelEngine:
    """Calculates structured confidence from multiple components.

    Formula (AI-free):
        deterministic_score = (
            technical_confluence * w_tech +
            mtf_agreement        * w_mtf +
            risk_quality         * w_risk +
            data_quality         * w_data
        ) / (w_tech + w_mtf + w_risk + w_data)

    ai_advisory_score = ai_confidence  (passed through, NOT blended)

    Default weights (sum = 1.0 for deterministic):
        technical: 0.35
        mtf:       0.25
        risk:      0.15
        data:      0.15
        ai:        0.10  (used only for ai_advisory_score, NOT in deterministic)
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

        # ── Deterministic score: AI-FREE ──
        w_sum = self._w_tech + self._w_mtf + self._w_risk + self._w_data
        if w_sum > 0:
            det = (technical * self._w_tech + mtf * self._w_mtf +
                   risk * self._w_risk + dq * self._w_data) / w_sum
        else:
            det = (technical + mtf + risk + dq) / 4

        det = max(0, min(100, round(det, 2)))

        # ── AI advisory score: separate layer ──
        ai_score = ai  # passed through, not blended

        return ConfidenceModel(
            technical_score=technical, risk_score=risk,
            data_quality_score=dq, ai_confidence=ai,
            mtf_agreement=mtf,
            deterministic_score=det,
            ai_advisory_score=ai_score,
            timestamp=now_ms(),
        )
