"""
NEXUS OVERLAY AI - Initial Schema Migration (001)
Creates all tables for the NEXUS OVERLAY AI database.
"""
from __future__ import annotations
import aiosqlite

from backend.database.models import (
    SCHEMA_VERSION_DDL,
    MARKET_DATA_DDL,
    DECISION_LOG_DDL,
    SIGNAL_HISTORY_DDL,
    STRATEGY_ANALYSIS_DDL,
    AI_ANALYSIS_DDL,
    SYSTEM_EVENTS_DDL,
    SETTINGS_DDL,
    PERFORMANCE_METRICS_DDL,
    DEFAULT_SETTINGS,
)


async def up(db: aiosqlite.Connection) -> None:
    """Create all tables for initial schema."""
    
    # Schema version tracking
    await db.execute("DROP TABLE IF EXISTS schema_version")
    await db.executescript(SCHEMA_VERSION_DDL)
    
    # Market data (OHLCV + tick)
    await db.executescript(MARKET_DATA_DDL)
    
    # Decision log (permanent record)
    await db.executescript(DECISION_LOG_DDL)
    
    # Signal history (lifecycle tracking)
    await db.executescript(SIGNAL_HISTORY_DDL)
    
    # Strategy analysis
    await db.executescript(STRATEGY_ANALYSIS_DDL)
    
    # AI analysis results
    await db.executescript(AI_ANALYSIS_DDL)
    
    # System events
    await db.executescript(SYSTEM_EVENTS_DDL)
    
    # Settings (key-value)
    await db.executescript(SETTINGS_DDL)
    
    # Performance metrics
    await db.executescript(PERFORMANCE_METRICS_DDL)
    
    # Seed default settings
    for key, (value, category) in DEFAULT_SETTINGS.items():
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value, category) VALUES (?, ?, ?)",
            (key, value, category),
        )
    
    await db.commit()
    print("Migration 001_initial: All tables created successfully")


async def down(db: aiosqlite.Connection) -> None:
    """Drop all tables (reverse of up)."""
    tables = [
        "performance_metrics",
        "settings",
        "system_events",
        "ai_analysis",
        "strategy_analysis",
        "signal_history",
        "decision_log",
        "market_data",
    ]
    
    for table in tables:
        await db.execute(f"DROP TABLE IF EXISTS {table}")
    
    await db.commit()
    print("Migration 001_initial: All tables dropped")