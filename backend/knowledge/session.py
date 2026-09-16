"""
NEXUS OVERLAY AI - Session Knowledge Base

Codifies trading session definitions with IANA timezones.
Handles DST automatically — no hardcoded UTC offsets.

Sessions determine: liquidity, volatility, institutional activity,
and optimal trading windows.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class SessionConcept:
    """Defines a trading session with its characteristics.

    Uses IANA timezone names so Python's zoneinfo handles DST automatically.
    Never hardcode UTC offsets for sessions — DST changes them.
    """
    name: str
    code: str  # Machine-readable code
    timezone_iana: str  # IANA timezone, e.g. "Europe/London"
    start_hour_local: int  # Hour in session's local timezone (0-23)
    end_hour_local: int  # Hour in session's local timezone (0-23)
    start_minute_local: int = 0
    end_minute_local: int = 0
    description: str = ""
    typical_spread_range: str = ""  # e.g. "15-30 points for XAUUSD"
    typical_volatility: str = ""  # e.g. "HIGH"
    characteristics: List[str] = field(default_factory=list)
    institutional_participation: str = ""  # HIGH / MEDIUM / LOW
    best_for: List[str] = field(default_factory=list)  # Best strategies
    avoid: List[str] = field(default_factory=list)  # What to avoid
    notes: List[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════
# TRADING SESSIONS — Using IANA timezones for DST correctness
# ═══════════════════════════════════════════════════════════

TOKYO_SESSION = SessionConcept(
    name="Tokyo (Asian) Session",
    code="ASIAN",
    timezone_iana="Asia/Tokyo",
    start_hour_local=9,
    end_hour_local=15,  # 09:00-15:00 JST
    start_minute_local=0,
    end_minute_local=0,
    description=(
        "The Asian session, centered on Tokyo. Lower volatility for XAUUSD "
        "compared to London/NY. Often establishes the range that London/NY "
        "will break out of."
    ),
    typical_spread_range="20-40 points",
    typical_volatility="LOW to MODERATE",
    characteristics=[
        "Lower volume for gold compared to Western sessions",
        "Often establishes an intraday range",
        "Range-bound price action common",
        "Sets up Asian High/Low as liquidity targets for London",
        "Bank of Japan influences JPY pairs; indirect gold impact",
        "Chinese economic data can cause spikes",
        "Thin market — larger spreads possible",
    ],
    institutional_participation="LOW",
    best_for=[
        "Range identification — mark the Asian range for London breakout",
        "Accumulation/distribution detection",
        "Range-bound strategies (mean reversion within range)",
    ],
    avoid=[
        "Trend-following trades (low directional momentum)",
        "Breakout entries within Asian session (often false breakouts)",
        "Low spread requirements (spreads widen in thin market)",
    ],
    notes=[
        "Asian High and Low are key liquidity levels for London session",
        "Gold often consolidates during Asian session",
        "Watch for Bank of Japan interventions",
        "Chinese market opens at 09:30 CST (08:30 JST) can affect gold",
    ],
)

LONDON_SESSION = SessionConcept(
    name="London Session",
    code="LONDON",
    timezone_iana="Europe/London",
    start_hour_local=8,
    end_hour_local=16,  # 08:00-16:00 GMT/BST (IANA handles DST)
    start_minute_local=0,
    end_minute_local=0,
    description=(
        "The most active session for gold. London FIX times are critical. "
        "Institutional flows dominate. Typically breaks the Asian range."
    ),
    typical_spread_range="15-25 points",
    typical_volatility="HIGH",
    characteristics=[
        "Highest volume session for XAUUSD",
        "London FIX at 10:30 and 15:00 GMT — major institutional activity",
        "Typically breaks the Asian range in the first 1-2 hours",
        "London Open drive is one of the most reliable moves",
        "European Central Bank decisions impact during session",
        "Strongest directional moves of the day often start here",
        "Spreads are tightest during this session for gold",
    ],
    institutional_participation="HIGH",
    best_for=[
        "Trend-following — London drive establishes direction",
        "Breakout strategies — Asian range breakout",
        "Liquidity sweeps — targeting Asian High/Low",
        "BOS/CHOCH — structure forms most clearly during London",
        "Scalping — tight spreads, high volume",
    ],
    avoid=[
        "Entering during London FIX spikes (10:30, 15:00 GMT) without confirmation",
        "Counter-trend trades during strong London drive",
        "Trading during first 5-10 minutes — spread spike at open",
    ],
    notes=[
        "London Open Drive: First 2-4 hours often set the daily trend",
        "The Asian High/Low becomes a key target during London",
        "London FIX (10:30 GMT) often causes sharp moves in gold",
        "DST: Europe/London shifts between GMT and BST — IANA handles this",
        "13:00-14:00 GMT: Pre-NY positioning, can be choppy",
    ],
)

NEW_YORK_SESSION = SessionConcept(
    name="New York Session",
    code="NEW_YORK",
    timezone_iana="America/New_York",
    start_hour_local=8,
    end_hour_local=17,  # 08:00-17:00 EST/EDT (IANA handles DST)
    start_minute_local=0,
    end_minute_local=0,
    description=(
        "Second most active session. US economic data releases drive volatility. "
        "FOMC, NFP, CPI events create major moves in gold."
    ),
    typical_spread_range="15-30 points",
    typical_volatility="HIGH",
    characteristics=[
        "Major US data releases: NFP, CPI, FOMC, PPI, PCE, GDP",
        "FOMC announcements at 14:00 ET — extreme volatility for gold",
        "COMEX gold trading adds institutional depth",
        "US Dollar strength/weakness directly impacts gold",
        "Trend continuation or reversal from London session",
        "NY FIX at 10:00 ET — institutional activity",
        "Afternoon session can see profit-taking",
    ],
    institutional_participation="HIGH",
    best_for=[
        "News-based trading (US economic data)",
        "Trend continuation from London session",
        "USD-correlated strategies (DXY inverse)",
        "FOMC/NFP event trading (with preparation)",
        "Reversal setups at session extremes",
    ],
    avoid=[
        "New entries 30 minutes before major US data releases",
        "Large positions during FOMC without tight risk management",
        "Trading during the 13:00-14:00 ET dead zone (pre-FOMC or pre-data)",
        "Ignoring spread widening during news events",
    ],
    notes=[
        "FOMC: The single most impactful event for gold intraday",
        "NFP: First Friday — major volatility spike expected",
        "NY-London overlap (13:00-16:00 ET) has highest combined volume",
        "US 10Y yield movements correlate inversely with gold",
        "DST: America/New_York shifts between EST and EDT — IANA handles this",
    ],
)

LONDON_NEW_YORK_OVERLAP = SessionConcept(
    name="London-New York Overlap",
    code="OVERLAP",
    timezone_iana="America/New_York",  # Using NY timezone for reference
    start_hour_local=13,  # 13:00 ET = 18:00 GMT = late London
    end_hour_local=16,  # 16:00 ET = 21:00 GMT = London close
    start_minute_local=0,
    end_minute_local=0,
    description=(
        "The overlap period when both London and New York sessions are active. "
        "This is the highest-volume, highest-volatility window of the day. "
        "Institutional flows from both sides of the Atlantic converge."
    ),
    typical_spread_range="12-22 points (tightest)",
    typical_volatility="VERY HIGH",
    characteristics=[
        "Highest combined volume of the day",
        "Both European and American institutions active simultaneously",
        "Strongest directional moves often occur during overlap",
        "London afternoon positioning meets NY afternoon activity",
        "FOMC announcements often fall within this window",
        "Innovation in spreads — tightest of the day",
    ],
    institutional_participation="VERY HIGH",
    best_for=[
        "Major directional trades — strongest moves of the day",
        "Scalping — tightest spreads, highest liquidity",
        "Momentum trading — directional conviction is highest",
        "End-of-day position management",
    ],
    avoid=[
        "Range-bound strategies — market is too volatile",
        "Over-leveraging — moves are fast and large",
        "Ignoring risk management — volatility is extreme",
    ],
    notes=[
        "This is when institutional order flow is highest",
        "London close (16:00 GMT) can cause position squaring",
        "Best window for high-confidence setups",
        "Actual overlap hours vary with DST — use zone-aware calculation",
    ],
)

# ═══════════════════════════════════════════════════════════
# SESSION TIMING HELPER — No hardcoded UTC offsets
# ═══════════════════════════════════════════════════════════

# Quick-lookup: IANA timezone for each session code
SESSION_TIMEZONE_MAP = {
    "ASIAN": "Asia/Tokyo",
    "LONDON": "Europe/London",
    "NEW_YORK": "America/New_York",
    "OVERLAP": "America/New_York",  # Reference timezone
}

# Master list of all session concepts
ALL_SESSION_CONCEPTS: List[SessionConcept] = [
    TOKYO_SESSION,
    LONDON_SESSION,
    NEW_YORK_SESSION,
    LONDON_NEW_YORK_OVERLAP,
]
