"""
NEXUS OVERLAY AI - Database Models
SQLAlchemy-style table definitions using aiosqlite raw SQL.
Schema versioning with migration support.
"""
from __future__ import annotations
from typing import Any

# Current schema version - increment with each migration
SCHEMA_VERSION = 1
SCHEMA_VERSION_TABLE = "schema_version"

# ============================================================
# Table DDL Definitions (raw SQL for aiosqlite)
# ============================================================

SCHEMA_VERSION_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now')),
    description TEXT
);
"""

MARKET_DATA_DDL = """
CREATE TABLE IF NOT EXISTS market_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume INTEGER NOT NULL DEFAULT 0,
    spread REAL NOT NULL DEFAULT 0,
    tick_bid REAL,
    tick_ask REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_market_data_symbol_tf_ts
    ON market_data(symbol, timeframe, timestamp);
CREATE INDEX IF NOT EXISTS idx_market_data_timestamp
    ON market_data(timestamp);
"""

DECISION_LOG_DDL = """
CREATE TABLE IF NOT EXISTS decision_log (
    id TEXT PRIMARY KEY,
    timestamp INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    decision TEXT NOT NULL,
    confidence INTEGER NOT NULL DEFAULT 0,
    entry REAL,
    sl REAL,
    tp1 REAL,
    tp2 REAL,
    tp3 REAL,
    rr REAL DEFAULT 0,
    market_regime TEXT,
    trend TEXT,
    structure TEXT,
    liquidity_state TEXT,
    strategy_scores TEXT,
    indicator_snapshot TEXT,
    evidence TEXT,
    invalidations TEXT,
    ai_assessment TEXT,
    data_quality REAL DEFAULT 0,
    signal_status TEXT,
    outcome TEXT,
    actual_pnl REAL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_decision_log_symbol_ts
    ON decision_log(symbol, timestamp);
CREATE INDEX IF NOT EXISTS idx_decision_log_decision
    ON decision_log(decision);
"""

SIGNAL_HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS signal_history (
    id TEXT PRIMARY KEY,
    timestamp INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    decision TEXT NOT NULL,
    confidence INTEGER NOT NULL,
    entry REAL NOT NULL,
    sl REAL NOT NULL,
    tp1 REAL NOT NULL,
    tp2 REAL NOT NULL,
    tp3 REAL NOT NULL,
    rr REAL NOT NULL,
    trend TEXT,
    regime TEXT,
    lifecycle_state TEXT NOT NULL DEFAULT 'NEW',
    evidence TEXT,
    invalidations TEXT,
    data_quality_score REAL DEFAULT 100.0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_signal_history_symbol
    ON signal_history(symbol);
CREATE INDEX IF NOT EXISTS idx_signal_history_lifecycle
    ON signal_history(lifecycle_state);
CREATE INDEX IF NOT EXISTS idx_signal_history_ts
    ON signal_history(timestamp);
"""

STRATEGY_ANALYSIS_DDL = """
CREATE TABLE IF NOT EXISTS strategy_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id TEXT,
    strategy_name TEXT NOT NULL,
    direction TEXT NOT NULL,
    score INTEGER NOT NULL DEFAULT 0,
    confidence REAL NOT NULL DEFAULT 0,
    evidence TEXT,
    timeframe TEXT,
    timestamp INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (signal_id) REFERENCES signal_history(id)
);
CREATE INDEX IF NOT EXISTS idx_strategy_analysis_signal
    ON strategy_analysis(signal_id);
CREATE INDEX IF NOT EXISTS idx_strategy_analysis_name
    ON strategy_analysis(strategy_name);
"""

AI_ANALYSIS_DDL = """
CREATE TABLE IF NOT EXISTS ai_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id TEXT,
    provider TEXT NOT NULL,
    assessment TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0,
    explanation TEXT,
    snapshot_hash TEXT,
    timestamp INTEGER NOT NULL,
    latency_ms INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (signal_id) REFERENCES signal_history(id)
);
CREATE INDEX IF NOT EXISTS idx_ai_analysis_signal
    ON ai_analysis(signal_id);
CREATE INDEX IF NOT EXISTS idx_ai_analysis_provider
    ON ai_analysis(provider);
"""

SYSTEM_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS system_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    source TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'INFO',
    message TEXT NOT NULL,
    payload TEXT,
    timestamp INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_system_events_type
    ON system_events(event_type);
CREATE INDEX IF NOT EXISTS idx_system_events_ts
    ON system_events(timestamp);
"""

SETTINGS_DDL = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'general',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

PERFORMANCE_METRICS_DDL = """
CREATE TABLE IF NOT EXISTS performance_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    tags TEXT,
    timestamp INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_perf_metrics_name
    ON performance_metrics(metric_name);
CREATE INDEX IF NOT EXISTS idx_perf_metrics_ts
    ON performance_metrics(timestamp);
"""


# ============================================================
# Table definitions registry
# ============================================================

TABLE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "schema_version": {
        "ddl": SCHEMA_VERSION_DDL,
        "description": "Schema version tracking",
    },
    "market_data": {
        "ddl": MARKET_DATA_DDL,
        "description": "OHLCV candle data and tick data storage",
    },
    "decision_log": {
        "ddl": DECISION_LOG_DDL,
        "description": "Permanent decision log with full context",
    },
    "signal_history": {
        "ddl": SIGNAL_HISTORY_DDL,
        "description": "Signal lifecycle history",
    },
    "strategy_analysis": {
        "ddl": STRATEGY_ANALYSIS_DDL,
        "description": "Individual strategy assessment results",
    },
    "ai_analysis": {
        "ddl": AI_ANALYSIS_DDL,
        "description": "AI provider analysis results",
    },
    "system_events": {
        "ddl": SYSTEM_EVENTS_DDL,
        "description": "System event log",
    },
    "settings": {
        "ddl": SETTINGS_DDL,
        "description": "Runtime settings (key-value store)",
    },
    "performance_metrics": {
        "ddl": PERFORMANCE_METRICS_DDL,
        "description": "Performance metric time series",
    },
}


# ============================================================
# Default settings
# ============================================================

DEFAULT_SETTINGS: dict[str, tuple[str, str]] = {
    # (value, category)
    "system.version": ("1.0.0", "system"),
    "system.name": ("Nexus Overlay AI", "system"),
    "symbol.name": ("XAUUSD", "symbol"),
    "ai.enabled": ("true", "ai"),
    "ai.provider": ("openai", "ai"),
    "transport.port": ("8765", "transport"),
    "database.path": ("./data/nexus_overlay.db", "database"),
    "risk.min_rr": ("1.5", "risk"),
    "risk.min_confidence": ("70", "risk"),
    "risk.max_spread": ("1.0", "risk"),
    "signal.expiry_candles": ("5", "signal"),
}