"""
NEXUS OVERLAY AI - Evidence Graph Engine

The Evidence Graph is the directional intelligence system. It separates
bullish, bearish, and neutral evidence to prevent direction confusion.

Instead of a single confluence score (which masks direction), the Evidence
Graph tracks:
  - bullish_score / bearish_score / neutral_score
  - net_directional_score (bullish - bearish)
  - conflict_score (how much evidence contradicts)
  - supporting_evidence (for the proposed direction)
  - counter_evidence (against the proposed direction)
  - missing_confirmation (what's needed to strengthen the thesis)
  - invalidation_conditions (what would invalidate the thesis)

This is the deterministic brain that AI can advise but never replace.

Design ref: audit sections XIII, XXVI, XXVII, XXVIII
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class Direction(Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class ConflictSeverity(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class EvidenceItem:
    """A single piece of evidence in the graph."""
    source: str  # e.g. "structure_engine", "price_action_engine"
    reason_code: str  # e.g. "BOS_BULLISH", "HTF_BEARISH", "LIQUIDITY_SWEEP"
    direction: Direction
    strength: float  # 0-100
    description: str  # Human-readable explanation
    timeframe: str = ""  # Which timeframe this evidence is from
    confidence: float = 1.0  # How certain this detection is (0-1)
    timestamp: int = 0  # When this evidence was generated


@dataclass
class MissingConfirmation:
    """Tracks what confirmation is missing for stronger conviction."""
    source: str
    reason_code: str
    description: str
    priority: str = "MEDIUM"  # HIGH, MEDIUM, LOW


@dataclass
class InvalidationCondition:
    """Tracks what would invalidate the current thesis."""
    source: str
    reason_code: str
    description: str
    current_status: str = "VALID"  # VALID, APPROACHING, INVALIDATED


@dataclass
class EvidenceGraph:
    """
    Directional evidence aggregator.

    The Evidence Graph takes evidence from all engines and produces a
    clear directional assessment with supporting and counter evidence.

    Key innovation: Instead of a single score that masks direction,
    we maintain separate bullish and bearish scores.

    Usage:
        graph = EvidenceGraph()
        graph.add_evidence(EvidenceItem(
            source="structure_engine", reason_code="BOS_BEARISH",
            direction=Direction.BEARISH, strength=80.0,
            description="H1 Break of Structure bearish",
            timeframe="H1"
        ))
        ...
        assessment = graph.assess()
        # assessment.net_directional_score < 0 → BEARISH
        # assessment.supporting_evidence → why BEARISH
        # assessment.counter_evidence → what says BULLISH
    """

    def __init__(self) -> None:
        self._evidence: List[EvidenceItem] = []
        self._missing_confirmations: List[MissingConfirmation] = []
        self._invalidation_conditions: List[InvalidationCondition] = []

        # Timeframe weights (higher TF = more weight)
        self._tf_weights: Dict[str, float] = {
            "H4": 1.0,
            "H1": 0.9,
            "M30": 0.8,
            "M15": 0.7,
            "M5": 0.5,
            "M3": 0.3,
            "M1": 0.2,
        }

    def add_evidence(self, evidence: EvidenceItem) -> None:
        """Add a piece of evidence to the graph."""
        self._evidence.append(evidence)

    def add_missing_confirmation(self, mc: MissingConfirmation) -> None:
        """Track a missing confirmation."""
        self._missing_confirmations.append(mc)

    def add_invalidation_condition(self, ic: InvalidationCondition) -> None:
        """Track an invalidation condition."""
        self._invalidation_conditions.append(ic)

    def clear(self) -> None:
        """Reset the evidence graph for a new analysis cycle."""
        self._evidence.clear()
        self._missing_confirmations.clear()
        self._invalidation_conditions.clear()

    def _get_tf_weight(self, timeframe: str) -> float:
        """Get the weight for a timeframe."""
        return self._tf_weights.get(timeframe, 0.5)

    def _weighted_strength(self, evidence: EvidenceItem) -> float:
        """Calculate weighted strength considering timeframe and confidence."""
        tf_weight = self._get_tf_weight(evidence.timeframe)
        return evidence.strength * tf_weight * evidence.confidence

    def assess(self) -> EvidenceAssessment:
        """
        Process all evidence and produce a directional assessment.

        Returns EvidenceAssessment with:
          - bullish_score, bearish_score, neutral_score
          - net_directional_score (bullish - bearish)
          - conflict_score
          - supporting_evidence, counter_evidence
          - missing_confirmation, invalidation_conditions
          - proposed_direction, agreement_ratio
        """
        bullish_score = 0.0
        bearish_score = 0.0
        neutral_score = 0.0
        total_weight = 0.0

        for ev in self._evidence:
            weighted = self._weighted_strength(ev)
            if ev.direction == Direction.BULLISH:
                bullish_score += weighted
            elif ev.direction == Direction.BEARISH:
                bearish_score += weighted
            else:
                neutral_score += weighted
            total_weight += ev.strength * self._get_tf_weight(ev.timeframe)

        # Normalize scores to 0-100 range
        if total_weight > 0:
            bullish_score = (bullish_score / total_weight) * 100
            bearish_score = (bearish_score / total_weight) * 100
            neutral_score = (neutral_score / total_weight) * 100

        # Net directional score
        net_directional_score = bullish_score - bearish_score

        # Conflict score: how much evidence contradicts the majority
        total_evidence_count = len([e for e in self._evidence
                                    if e.direction != Direction.NEUTRAL])
        if total_evidence_count > 0:
            bullish_count = sum(1 for e in self._evidence
                               if e.direction == Direction.BULLISH)
            bearish_count = sum(1 for e in self._evidence
                               if e.direction == Direction.BEARISH)
            majority = max(bullish_count, bearish_count)
            conflict_score = (1 - majority / total_evidence_count) * 100
        else:
            conflict_score = 0.0

        # Determine proposed direction
        if net_directional_score > 10:
            proposed_direction = Direction.BULLISH
        elif net_directional_score < -10:
            proposed_direction = Direction.BEARISH
        else:
            proposed_direction = Direction.NEUTRAL

        # Calculate agreement ratio
        if total_evidence_count > 0:
            agreeing = sum(1 for e in self._evidence
                          if e.direction == proposed_direction
                          or e.direction == Direction.NEUTRAL)
            agreement_ratio = agreeing / total_evidence_count
        else:
            agreement_ratio = 0.0

        # Build supporting and counter evidence lists
        supporting = []
        counter = []
        for ev in self._evidence:
            if ev.direction == proposed_direction:
                supporting.append(ev)
            elif ev.direction != Direction.NEUTRAL:
                counter.append(ev)

        # Sort by weighted strength
        supporting.sort(key=lambda e: self._weighted_strength(e), reverse=True)
        counter.sort(key=lambda e: self._weighted_strength(e), reverse=True)

        # Determine conflict severity
        conflict_severity = self._determine_conflict_severity(
            conflict_score, net_directional_score, total_evidence_count
        )

        return EvidenceAssessment(
            bullish_score=round(bullish_score, 2),
            bearish_score=round(bearish_score, 2),
            neutral_score=round(neutral_score, 2),
            net_directional_score=round(net_directional_score, 2),
            conflict_score=round(conflict_score, 2),
            conflict_severity=conflict_severity,
            proposed_direction=proposed_direction,
            agreement_ratio=round(agreement_ratio, 2),
            supporting_evidence=supporting,
            counter_evidence=counter,
            missing_confirmation=list(self._missing_confirmations),
            invalidation_conditions=list(self._invalidation_conditions),
            total_evidence_count=total_evidence_count,
        )

    def _determine_conflict_severity(
        self,
        conflict_score: float,
        net_directional: float,
        evidence_count: int,
    ) -> ConflictSeverity:
        """Determine the severity of conflicting evidence."""
        if evidence_count == 0:
            return ConflictSeverity.CRITICAL
        abs_net = abs(net_directional)
        if conflict_score < 10 and abs_net > 30:
            return ConflictSeverity.LOW
        elif conflict_score < 25 and abs_net > 15:
            return ConflictSeverity.MEDIUM
        elif conflict_score < 50:
            return ConflictSeverity.HIGH
        else:
            return ConflictSeverity.CRITICAL


@dataclass(frozen=True)
class EvidenceAssessment:
    """The result of EvidenceGraph.assess() — a complete directional picture."""
    bullish_score: float  # 0-100
    bearish_score: float  # 0-100
    neutral_score: float  # 0-100
    net_directional_score: float  # -100 to +100
    conflict_score: float  # 0-100 (higher = more conflict)
    conflict_severity: ConflictSeverity
    proposed_direction: Direction
    agreement_ratio: float  # 0-1 (what fraction agrees with proposed direction)
    supporting_evidence: List[EvidenceItem] = field(default_factory=list)
    counter_evidence: List[EvidenceItem] = field(default_factory=list)
    missing_confirmation: List[MissingConfirmation] = field(default_factory=list)
    invalidation_conditions: List[InvalidationCondition] = field(default_factory=list)
    total_evidence_count: int = 0

    @property
    def has_major_conflict(self) -> bool:
        """Check if there's a critical or high conflict."""
        return self.conflict_severity in (
            ConflictSeverity.HIGH, ConflictSeverity.CRITICAL
        )

    @property
    def top_supporting_reason_codes(self) -> List[str]:
        """Get the reason codes of top supporting evidence."""
        return [e.reason_code for e in self.supporting_evidence[:5]]

    @property
    def top_counter_reason_codes(self) -> List[str]:
        """Get the reason codes of top counter evidence."""
        return [e.reason_code for e in self.counter_evidence[:5]]

    @property
    def missing_reason_codes(self) -> List[str]:
        """Get reason codes for missing confirmations."""
        return [m.reason_code for m in self.missing_confirmation]
