"""
NEXUS OVERLAY AI - Risk Knowledge Base

Codifies risk concepts and scoring as deterministic data.
Every risk factor has: definition, detection, scoring, thresholds, conflicts.

Risk is the SAFETY GATE — it must run before any decision is made.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class RiskLevel(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ConflictSeverity(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class RiskConcept:
    """Base class for all risk factors.

    Each risk factor has explicit detection, scoring rules, thresholds,
    and how it affects the overall risk assessment.
    """
    name: str
    code: str  # Machine-readable reason code
    level: RiskLevel
    definition: str
    detection_conditions: List[str]
    scoring_rules: str  # How to compute the risk score
    threshold_warning: float  # Threshold for WARNING level
    threshold_reject: float  # Threshold for REJECTION
    context: List[str]
    mitigation: List[str]  # How to mitigate this risk
    conflicts: List[str]
    weight: float = 1.0  # Weight in overall risk calculation (0-1)


# ═══════════════════════════════════════════════════════════
# RISK FACTORS — The bot's safety consciousness
# ═══════════════════════════════════════════════════════════

SPREAD_RISK = RiskConcept(
    name="Spread Risk",
    code="SPREAD_RISK",
    level=RiskLevel.HIGH,
    definition=(
        "Risk from the difference between bid and ask prices. Wide spreads "
        "increase effective cost and slippage. Can spike during low liquidity, "
        "news events, and session transitions."
    ),
    detection_conditions=[
        "Current spread exceeds normal range for the symbol",
        "Spread is wider than the configured maximum",
        "Spread is increasing rapidly",
        "Spread during non-active session is abnormally wide",
    ],
    scoring_rules=(
        "Score = 0 if spread <= normal_range_max. "
        "Score = 50 if spread between normal and warning. "
        "Score = 100 if spread > rejection threshold. "
        "For XAUUSD: normal <= 30pts, warning > 30pts, reject > 60pts."
    ),
    threshold_warning=30.0,  # Points
    threshold_reject=60.0,  # Points
    context=[
        "Spreads widen during session transitions",
        "Spreads spike during news releases",
        "Thin liquidity (Asian session, weekends) = wider spreads",
        "Broker-specific spread profiles",
    ],
    mitigation=[
        "Wait for spread to normalize",
        "Only trade during active sessions",
        "Reduce position size to account for spread cost",
        "Use spread filter before entry",
    ],
    conflicts=[
        "SPREAD_OK code should not be present alongside SPREAD_RISK",
    ],
    weight=0.20,  # High weight — spread directly impacts trade cost
)

VOLATILITY_RISK = RiskConcept(
    name="Volatility Risk",
    code="VOLATILITY_RISK",
    level=RiskLevel.MEDIUM,
    definition=(
        "Risk from abnormal or extreme volatility. Measured by ATR relative "
        "to its average. High volatility means larger price swings and wider "
        "stops needed. Low volatility may indicate impending breakout."
    ),
    detection_conditions=[
        "Current ATR is more than 2x its 20-period average",
        "Current ATR is less than 0.5x its 20-period average",
        "Sudden ATR spike indicating volatility expansion",
        "ATR consistently declining (potential compression/explosion)",
    ],
    scoring_rules=(
        "Score = 0 if ATR ratio is 0.5-1.5 (normal). "
        "Score = 40 if ratio > 1.5 or < 0.5 (elevated). "
        "Score = 70 if ratio > 2.0 or < 0.3 (high). "
        "Score = 100 if ratio > 3.0 (extreme)."
    ),
    threshold_warning=1.5,  # ATR ratio
    threshold_reject=3.0,  # ATR ratio
    context=[
        "High volatility widens SL/TP requirements",
        "Low volatility often precedes large moves",
        "ATR normalizes after news-driven spikes",
        "Session transitions often see volatility shifts",
    ],
    mitigation=[
        "Adjust position size inversely to volatility",
        "Widen SL/TP to accommodate volatility",
        "Avoid trading during extreme volatility",
        "Wait for volatility to normalize after news",
    ],
    conflicts=[
        "ATR_NORMAL code indicates acceptable volatility",
        "Opposing trend with high volatility = dangerous",
    ],
    weight=0.15,
)

RISK_REWARD_RISK = RiskConcept(
    name="Risk-Reward Risk",
    code="RR_RISK",
    level=RiskLevel.HIGH,
    definition=(
        "Risk from unfavorable risk-reward ratio. A trade must offer "
        "sufficient reward relative to the risk taken. Minimum RR should "
        "be configurable and enforced."
    ),
    detection_conditions=[
        "Calculated RR is below the minimum threshold",
        "TP targets are not reachable given current structure",
        "SL distance is too wide relative to recent price action",
        "No clear TP target identified",
    ],
    scoring_rules=(
        "Score = 0 if RR >= 2.0. "
        "Score = 30 if RR >= 1.5. "
        "Score = 60 if RR >= 1.0. "
        "Score = 100 if RR < 1.0. "
        "Score = 100 if RR cannot be calculated."
    ),
    threshold_warning=1.5,
    threshold_reject=1.0,
    context=[
        "Minimum RR is configurable (default 1.5)",
        "Higher RR = more robust strategy",
        "RR should be calculated from thesis invalidation, not arbitrary",
        "SL based on structural invalidation, not ATR multiplication",
    ],
    mitigation=[
        "Widen TP targets to include structural objectives",
        "Tighten SL to structural invalidation level",
        "Skip the trade if RR cannot meet minimum",
        "Wait for better entry to improve RR",
    ],
    conflicts=[
        "RR_OK code indicates acceptable risk-reward",
    ],
    weight=0.20,  # Critical — RR is a core risk metric
)

SESSION_RISK = RiskConcept(
    name="Session Risk",
    code="SESSION_RISK",
    level=RiskLevel.LOW,
    definition=(
        "Risk from trading during inactive or low-liquidity sessions. "
        "Thin markets have wider spreads, less reliable structure, "
        "and higher risk of erratic moves."
    ),
    detection_conditions=[
        "Current time falls outside active trading sessions",
        "Trading during Asian session for XAUUSD (lower liquidity)",
        "Trading during session transition period",
        "Weekend or holiday session",
    ],
    scoring_rules=(
        "Score = 0 during active sessions (London, NY, Overlap). "
        "Score = 30 during Asian session. "
        "Score = 50 during session transitions. "
        "Score = 80 during off-hours."
    ),
    threshold_warning=0.5,  # Time fraction outside active sessions
    threshold_reject=0.8,  # Almost entirely outside active sessions
    context=[
        "XAUUSD is most active during London and NY sessions",
        "Session transitions create spread spikes",
        "Asian session often range-bound for gold",
        "Use IANA timezone-aware session detection",
    ],
    mitigation=[
        "Only enter during active sessions",
        "Reduce position size outside active sessions",
        "Wait for session open for directional trades",
    ],
    conflicts=[
        "Active session detected = SESSION_RISK should not fire",
    ],
    weight=0.10,
)

NEWS_RISK = RiskConcept(
    name="News Risk",
    code="NEWS_RISK",
    level=RiskLevel.HIGH,
    definition=(
        "Risk from upcoming high-impact economic news. FOMC, NFP, CPI "
        "and other major releases can cause extreme volatility and "
        "unpredictable moves. NEWS_UNKNOWN is NOT SAFE."
    ),
    detection_conditions=[
        "High-impact news scheduled within the next 60 minutes",
        "FOMC/NFP/CPI/PPI within the trading window",
        "News provider reports upcoming event",
        "News provider is unavailable (NEWS_STATUS = UNKNOWN)",
    ],
    scoring_rules=(
        "Score = 0 if no news within 60 minutes. "
        "Score = 30 if news in 60-30 minutes. "
        "Score = 60 if news in 30-15 minutes. "
        "Score = 90 if news within 15 minutes. "
        "Score = 80 if news status is UNKNOWN (safety default)."
    ),
    threshold_warning=30.0,  # Minutes to event
    threshold_reject=15.0,  # Minutes to event
    context=[
        "Unknown = NOT SAFE (default safety assumption)",
        "User can choose strict news mode (avoid all news) or normal mode",
        "FOMC is the most impactful event for gold",
        "NFP causes the largest average move in gold",
        "CPI is second most impactful for gold",
    ],
    mitigation=[
        "Close or reduce positions before major news",
        "Wait for news release and post-release settling",
        "Widen SL to accommodate news volatility",
        "Avoid new entries 30 minutes before major data",
    ],
    conflicts=[
        "NEWS_OK code indicates no imminent news",
    ],
    weight=0.15,
)

DATA_QUALITY_RISK = RiskConcept(
    name="Data Quality Risk",
    code="DATA_QUALITY_RISK",
    level=RiskLevel.CRITICAL,
    definition=(
        "Risk from unreliable, stale, or incomplete market data. "
        "Decisions based on poor data are inherently dangerous. "
        "Data quality is measured on a 0-100 scale."
    ),
    detection_conditions=[
        "Data quality score below minimum threshold",
        "Data age exceeds maximum allowed staleness",
        "Missing candles or gaps in the data feed",
        "Bid/ask data is invalid or inconsistent",
        "MT5 bridge disconnected",
    ],
    scoring_rules=(
        "Score = 0 if data_quality >= 80. "
        "Score = 30 if data_quality >= 60. "
        "Score = 70 if data_quality >= 30. "
        "Score = 100 if data_quality < 30. "
        "Score = 100 if data_age > max_stale_ms."
    ),
    threshold_warning=60.0,  # Data quality 0-100
    threshold_reject=30.0,  # Data quality 0-100
    context=[
        "Data quality is a 0-100 scale throughout the system",
        "Stale data = WAIT always",
        "MT5 disconnection = immediate data quality concern",
        "Missing candles can cause incorrect structure analysis",
    ],
    mitigation=[
        "Wait for data to improve",
        "Check MT5 connection status",
        "Request data resync",
        "Fall back to higher timeframe (more stable data)",
    ],
    conflicts=[
        "DATA_STALE, DATA_UNAVAILABLE indicate data problems",
        "DATA_QUALITY_OK means data is acceptable",
    ],
    weight=0.25,  # Highest weight — bad data = bad decisions
)

SIGNAL_AGE_RISK = RiskConcept(
    name="Signal Age Risk",
    code="SIGNAL_AGE_RISK",
    level=RiskLevel.MEDIUM,
    definition=(
        "Risk from the time elapsed since the decision was made. "
        "In fast-moving markets, a signal can become outdated quickly. "
        "The older the signal, the less reliable the entry."
    ),
    detection_conditions=[
        "Time since decision exceeds maximum signal lifetime",
        "Market has moved significantly since decision",
        "Price has moved beyond the entry point",
        "Structure has changed since decision time",
    ],
    scoring_rules=(
        "Score = 0 if signal_age < 60 seconds. "
        "Score = 20 if age < 300 seconds (5 min). "
        "Score = 50 if age < 600 seconds (10 min). "
        "Score = 80 if age < 1800 seconds (30 min). "
        "Score = 100 if age > 1800 seconds."
    ),
    threshold_warning=300.0,  # seconds
    threshold_reject=1800.0,  # seconds (30 min)
    context=[
        "M1 scalping systems need very fresh signals",
        "Higher TF analysis is more tolerant of signal age",
        "Price movement since decision invalidates original thesis",
    ],
    mitigation=[
        "Re-evaluate if signal age is excessive",
        "Refresh analysis before entry",
        "Adjust entry to current price if still valid",
    ],
    conflicts=[
        "SIGNAL_FRESH code indicates signal is recent",
    ],
    weight=0.10,
)

# ═══════════════════════════════════════════════════════════
# CONFLICT SEVERITY DEFINITIONS
# ═══════════════════════════════════════════════════════════

CONFLICT_SEVERITY_LEVELS = {
    ConflictSeverity.LOW: {
        "description": "Minor disagreement between indicators or timeframes",
        "example": "H4 bearish, H1 bearish, M15 bullish (single outlier)",
        "action": "Proceed with caution, reduce confidence",
    },
    ConflictSeverity.MEDIUM: {
        "description": "Moderate disagreement across multiple timeframes",
        "example": "H4 bearish, H1 bearish, M15 bullish, M5 bearish",
        "action": "Reduced position size, tighter risk management",
    },
    ConflictSeverity.HIGH: {
        "description": "Major disagreement between timeframes",
        "example": "H4 bearish, H1 bullish, M30 bullish, M15 bullish",
        "action": "Wait for alignment, or reduce to minimum position",
    },
    ConflictSeverity.CRITICAL: {
        "description": "Fundamental disagreement — no clear direction",
        "example": "H4 bearish, H1 bullish, M30 bullish, M15 bearish, M5 bearish",
        "action": "WAIT — do not trade",
    },
}


# Master list of all risk concepts
ALL_RISK_CONCEPTS: List[RiskConcept] = [
    SPREAD_RISK,
    VOLATILITY_RISK,
    RISK_REWARD_RISK,
    SESSION_RISK,
    NEWS_RISK,
    DATA_QUALITY_RISK,
    SIGNAL_AGE_RISK,
]
