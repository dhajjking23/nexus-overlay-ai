"""
NEXUS OVERLAY AI - Database Manager
Async CRUD operations for all tables using aiosqlite.
Decision log, signal history, settings, performance metrics.
"""
from __future__ import annotations
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

import aiosqlite

from backend.config_loader import get_config
from backend.database.models import (
    SCHEMA_VERSION, TABLE_DEFINITIONS, DEFAULT_SETTINGS,
)

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Async database manager for NEXUS OVERLAY AI.
    
    Features:
    - Full CRUD for all tables
    - Async operations via aiosqlite
    - Automatic schema creation and migration
    - Connection pooling (single connection with async safety)
    - Thread-safe with lock
    """
    
    def __init__(self, db_path: str | None = None):
        if db_path:
            self._db_path = db_path
        else:
            cfg = get_config()
            self._db_path = cfg.get("database.path", "./data/nexus_overlay.db")
        
        self._db: Optional[aiosqlite.Connection] = None
        self._initialized = False
        self._lock = None  # Will be created in event loop
    
    @property
    def db_path(self) -> str:
        return self._db_path
    
    @property
    def is_initialized(self) -> bool:
        return self._initialized
    
    async def initialize(self) -> None:
        """Initialize database connection and create tables."""
        import asyncio
        self._lock = asyncio.Lock()
        
        # Ensure directory exists
        db_dir = Path(self._db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        
        # Enable WAL mode for better concurrent read performance
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA synchronous=NORMAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        
        # Create all tables
        for table_name, table_def in TABLE_DEFINITIONS.items():
            await self._db.executescript(table_def["ddl"])
        
        await self._db.commit()
        
        # Run migrations
        await self._apply_migrations()
        
        # Seed default settings
        await self._seed_settings()
        
        self._initialized = True
        logger.info(f"Database initialized: {self._db_path}")
    
    async def close(self) -> None:
        """Close database connection."""
        if self._db:
            await self._db.close()
            self._db = None
            self._initialized = False
            logger.info("Database closed")
    
    async def _apply_migrations(self) -> None:
        """Apply pending migrations."""
        # Get current version
        async with self._db.execute(
            "SELECT MAX(version) FROM schema_version"
        ) as cursor:
            row = await cursor.fetchone()
            current_version = row[0] if row and row[0] else 0
        
        if current_version < SCHEMA_VERSION:
            # Insert version record
            await self._db.execute(
                "INSERT OR REPLACE INTO schema_version (version, description) VALUES (?, ?)",
                (SCHEMA_VERSION, "Current schema")
            )
            await self._db.commit()
            logger.info(f"Schema version updated to {SCHEMA_VERSION}")
    
    async def _seed_settings(self) -> None:
        """Insert default settings if not present."""
        for key, (value, category) in DEFAULT_SETTINGS.items():
            await self._db.execute(
                "INSERT OR IGNORE INTO settings (key, value, category) VALUES (?, ?, ?)",
                (key, value, category),
            )
        await self._db.commit()
    
    # ================================================================
    # Market Data CRUD
    # ================================================================
    
    async def insert_market_data(
        self, symbol: str, timeframe: str, timestamp: int,
        open: float, high: float, low: float, close: float,
        volume: int, spread: float,
        tick_bid: float = 0, tick_ask: float = 0,
    ) -> int:
        """Insert a market data candle. Returns row id."""
        async with self._lock:
            cursor = await self._db.execute(
                """INSERT INTO market_data
                   (symbol, timeframe, timestamp, open, high, low, close, volume, spread, tick_bid, tick_ask)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (symbol, timeframe, timestamp, open, high, low, close, volume, spread, tick_bid, tick_ask),
            )
            await self._db.commit()
            return cursor.lastrowid
    
    async def get_market_data(
        self, symbol: str, timeframe: str, limit: int = 200, offset: int = 0,
    ) -> list[dict]:
        """Get market data candles, most recent first."""
        async with self._lock:
            async with self._db.execute(
                """SELECT * FROM market_data
                   WHERE symbol = ? AND timeframe = ?
                   ORDER BY timestamp DESC LIMIT ? OFFSET ?""",
                (symbol, timeframe, limit, offset),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    async def get_market_data_range(
        self, symbol: str, timeframe: str,
        start_ts: int, end_ts: int,
    ) -> list[dict]:
        """Get market data within a timestamp range."""
        async with self._lock:
            async with self._db.execute(
                """SELECT * FROM market_data
                   WHERE symbol = ? AND timeframe = ? AND timestamp BETWEEN ? AND ?
                   ORDER BY timestamp ASC""",
                (symbol, timeframe, start_ts, end_ts),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    async def cleanup_market_data(self, days: int = 30) -> int:
        """Delete market data older than N days. Returns rows deleted."""
        async with self._lock:
            cutoff = int(__import__('time').time() * 1000) - (days * 86400 * 1000)
            cursor = await self._db.execute(
                "DELETE FROM market_data WHERE timestamp < ?", (cutoff,)
            )
            await self._db.commit()
            return cursor.rowcount
    
    # ================================================================
    # Decision Log CRUD
    # ================================================================
    
    async def insert_decision_log(self, entry: dict) -> str:
        """
        Insert a decision log entry.
        Entry dict should have all columns as keys.
        Returns the entry id.
        """
        entry_id = entry.get("id", "")
        async with self._lock:
            # Serialize complex fields
            strategy_scores = json.dumps(entry.get("strategy_scores", {}), default=str)
            indicator_snapshot = json.dumps(entry.get("indicator_snapshot", {}), default=str)
            evidence = json.dumps(entry.get("evidence", []), default=str)
            invalidations = json.dumps(entry.get("invalidations", []), default=str)
            
            await self._db.execute(
                """INSERT OR REPLACE INTO decision_log
                   (id, timestamp, symbol, timeframe, decision, confidence,
                    entry, sl, tp1, tp2, tp3, rr, market_regime, trend, structure,
                    liquidity_state, strategy_scores, indicator_snapshot,
                    evidence, invalidations, ai_assessment, data_quality, signal_status,
                    outcome, actual_pnl)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                           ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry_id, entry.get("timestamp", 0), entry.get("symbol", ""),
                    entry.get("timeframe", ""), entry.get("decision", "WAIT"),
                    entry.get("confidence", 0), entry.get("entry", 0),
                    entry.get("sl", 0), entry.get("tp1", 0), entry.get("tp2", 0),
                    entry.get("tp3", 0), entry.get("rr", 0),
                    entry.get("market_regime", ""), entry.get("trend", ""),
                    entry.get("structure", ""), entry.get("liquidity_state", ""),
                    strategy_scores, indicator_snapshot,
                    evidence, invalidations, entry.get("ai_assessment", ""),
                    entry.get("data_quality", 0), entry.get("signal_status", "NEW"),
                    entry.get("outcome", ""), entry.get("actual_pnl", 0),
                ),
            )
            await self._db.commit()
            return entry_id
    
    async def get_decision_log(
        self, symbol: str | None = None, decision: str | None = None,
        limit: int = 100, offset: int = 0,
    ) -> list[dict]:
        """Get decision log entries with optional filters."""
        conditions = []
        params: list[Any] = []
        
        if symbol:
            conditions.append("symbol = ?")
            params.append(symbol)
        if decision:
            conditions.append("decision = ?")
            params.append(decision)
        
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.extend([limit, offset])
        
        async with self._lock:
            async with self._db.execute(
                f"""SELECT * FROM decision_log {where}
                    ORDER BY timestamp DESC LIMIT ? OFFSET ?""",
                params,
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    async def get_decision_stats(self, symbol: str = "XAUUSD") -> dict:
        """Get decision statistics for performance analysis."""
        async with self._lock:
            async with self._db.execute(
                """SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN decision = 'BUY' THEN 1 ELSE 0 END) as buys,
                    SUM(CASE WHEN decision = 'SELL' THEN 1 ELSE 0 END) as sells,
                    SUM(CASE WHEN decision = 'WAIT' THEN 1 ELSE 0 END) as waits,
                    AVG(confidence) as avg_confidence,
                    AVG(rr) as avg_rr,
                    AVG(data_quality) as avg_data_quality
                   FROM decision_log WHERE symbol = ?""",
                (symbol,),
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else {}
    
    # ================================================================
    # Signal History CRUD
    # ================================================================
    
    async def insert_signal(self, signal: dict) -> str:
        """Insert a trading signal into history."""
        signal_id = signal.get("signal_id", "")
        async with self._lock:
            evidence = json.dumps(signal.get("evidence", []), default=str)
            invalidations = json.dumps(signal.get("invalidations", []), default=str)
            
            await self._db.execute(
                """INSERT OR REPLACE INTO signal_history
                   (id, timestamp, symbol, timeframe, decision, confidence,
                    entry, sl, tp1, tp2, tp3, rr, trend, regime,
                    lifecycle_state, evidence, invalidations, data_quality_score)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    signal_id, signal.get("timestamp", 0), signal.get("symbol", ""),
                    signal.get("timeframe", ""), signal.get("decision", "WAIT"),
                    signal.get("confidence", 0), signal.get("entry", 0),
                    signal.get("sl", 0), signal.get("tp1", 0), signal.get("tp2", 0),
                    signal.get("tp3", 0), signal.get("rr", 0),
                    signal.get("trend", ""), signal.get("regime", ""),
                    signal.get("lifecycle_state", "NEW"),
                    evidence, invalidations,
                    signal.get("data_quality_score", 100.0),
                ),
            )
            await self._db.commit()
            return signal_id
    
    async def update_signal_lifecycle(
        self, signal_id: str, lifecycle_state: str, invalidations: list[str] | None = None,
    ) -> None:
        """Update signal lifecycle state."""
        async with self._lock:
            if invalidations is not None:
                inv_json = json.dumps(invalidations, default=str)
                await self._db.execute(
                    """UPDATE signal_history
                       SET lifecycle_state = ?, invalidations = ?, updated_at = datetime('now')
                       WHERE id = ?""",
                    (lifecycle_state, inv_json, signal_id),
                )
            else:
                await self._db.execute(
                    """UPDATE signal_history
                       SET lifecycle_state = ?, updated_at = datetime('now')
                       WHERE id = ?""",
                    (lifecycle_state, signal_id),
                )
            await self._db.commit()
    
    async def get_active_signals(self, symbol: str = "XAUUSD") -> list[dict]:
        """Get all active signals for a symbol."""
        async with self._lock:
            async with self._db.execute(
                """SELECT * FROM signal_history
                   WHERE symbol = ? AND lifecycle_state IN ('NEW', 'CONFIRMED', 'ACTIVE')
                   ORDER BY timestamp DESC""",
                (symbol,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    async def get_signal_history(
        self, symbol: str = "XAUUSD", limit: int = 50,
    ) -> list[dict]:
        """Get signal history for a symbol."""
        async with self._lock:
            async with self._db.execute(
                """SELECT * FROM signal_history
                   WHERE symbol = ?
                   ORDER BY timestamp DESC LIMIT ?""",
                (symbol, limit),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    # ================================================================
    # Strategy Analysis CRUD
    # ================================================================
    
    async def insert_strategy_analysis(self, analysis: dict) -> int:
        """Insert a strategy analysis result."""
        async with self._lock:
            evidence = json.dumps(analysis.get("evidence", []), default=str)
            cursor = await self._db.execute(
                """INSERT INTO strategy_analysis
                   (signal_id, strategy_name, direction, score, confidence,
                    evidence, timeframe, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    analysis.get("signal_id"), analysis.get("strategy_name", ""),
                    analysis.get("direction", "WAIT"), analysis.get("score", 0),
                    analysis.get("confidence", 0), evidence,
                    analysis.get("timeframe", ""), analysis.get("timestamp", 0),
                ),
            )
            await self._db.commit()
            return cursor.lastrowid
    
    async def get_strategy_analyses(self, signal_id: str) -> list[dict]:
        """Get all strategy analyses for a signal."""
        async with self._lock:
            async with self._db.execute(
                """SELECT * FROM strategy_analysis
                   WHERE signal_id = ? ORDER BY score DESC""",
                (signal_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    # ================================================================
    # AI Analysis CRUD
    # ================================================================
    
    async def insert_ai_analysis(self, analysis: dict) -> int:
        """Insert an AI analysis result."""
        async with self._lock:
            cursor = await self._db.execute(
                """INSERT INTO ai_analysis
                   (signal_id, provider, assessment, confidence, explanation,
                    snapshot_hash, timestamp, latency_ms)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    analysis.get("signal_id"), analysis.get("provider", ""),
                    analysis.get("assessment", "neutral"),
                    analysis.get("confidence", 0),
                    analysis.get("explanation", ""),
                    analysis.get("snapshot_hash", ""),
                    analysis.get("timestamp", 0),
                    analysis.get("latency_ms", 0),
                ),
            )
            await self._db.commit()
            return cursor.lastrowid
    
    async def get_ai_analyses(
        self, signal_id: str | None = None, provider: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Get AI analyses with optional filters."""
        conditions = []
        params: list[Any] = []
        
        if signal_id:
            conditions.append("signal_id = ?")
            params.append(signal_id)
        if provider:
            conditions.append("provider = ?")
            params.append(provider)
        
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)
        
        async with self._lock:
            async with self._db.execute(
                f"""SELECT * FROM ai_analysis {where}
                    ORDER BY timestamp DESC LIMIT ?""",
                params,
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    # ================================================================
    # System Events CRUD
    # ================================================================
    
    async def insert_system_event(
        self, event_type: str, source: str, message: str,
        severity: str = "INFO", payload: dict | None = None, timestamp: int = 0,
    ) -> int:
        """Insert a system event."""
        import time
        ts = timestamp or int(time.time() * 1000)
        payload_json = json.dumps(payload, default=str) if payload else None
        
        async with self._lock:
            cursor = await self._db.execute(
                """INSERT INTO system_events
                   (event_type, source, severity, message, payload, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (event_type, source, severity, message, payload_json, ts),
            )
            await self._db.commit()
            return cursor.lastrowid
    
    async def get_system_events(
        self, event_type: str | None = None, severity: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Get system events with optional filters."""
        conditions = []
        params: list[Any] = []
        
        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)
        if severity:
            conditions.append("severity = ?")
            params.append(severity)
        
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)
        
        async with self._lock:
            async with self._db.execute(
                f"""SELECT * FROM system_events {where}
                    ORDER BY timestamp DESC LIMIT ?""",
                params,
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    # ================================================================
    # Settings CRUD
    # ================================================================
    
    async def get_setting(self, key: str, default: str | None = None) -> str | None:
        """Get a setting value by key."""
        async with self._lock:
            async with self._db.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ) as cursor:
                row = await cursor.fetchone()
                return row["value"] if row else default
    
    async def set_setting(self, key: str, value: str, category: str = "general") -> None:
        """Set a setting value."""
        async with self._lock:
            await self._db.execute(
                """INSERT OR REPLACE INTO settings (key, value, category, updated_at)
                   VALUES (?, ?, ?, datetime('now'))""",
                (key, value, category),
            )
            await self._db.commit()
    
    async def get_all_settings(self, category: str | None = None) -> dict[str, str]:
        """Get all settings, optionally filtered by category."""
        async with self._lock:
            if category:
                async with self._db.execute(
                    "SELECT key, value FROM settings WHERE category = ?",
                    (category,),
                ) as cursor:
                    rows = await cursor.fetchall()
                    return {row["key"]: row["value"] for row in rows}
            else:
                async with self._db.execute(
                    "SELECT key, value FROM settings"
                ) as cursor:
                    rows = await cursor.fetchall()
                    return {row["key"]: row["value"] for row in rows}
    
    async def update_settings(self, settings: dict[str, str], category: str = "general") -> int:
        """Bulk update settings. Returns count updated."""
        count = 0
        async with self._lock:
            for key, value in settings.items():
                await self._db.execute(
                    """INSERT OR REPLACE INTO settings (key, value, category, updated_at)
                       VALUES (?, ?, ?, datetime('now'))""",
                    (key, str(value), category),
                )
                count += 1
            await self._db.commit()
        return count
    
    # ================================================================
    # Performance Metrics CRUD
    # ================================================================
    
    async def record_metric(
        self, metric_name: str, metric_value: float,
        tags: dict | None = None, timestamp: int = 0,
    ) -> int:
        """Record a performance metric."""
        import time
        ts = timestamp or int(time.time() * 1000)
        tags_json = json.dumps(tags, default=str) if tags else None
        
        async with self._lock:
            cursor = await self._db.execute(
                """INSERT INTO performance_metrics
                   (metric_name, metric_value, tags, timestamp)
                   VALUES (?, ?, ?, ?)""",
                (metric_name, metric_value, tags_json, ts),
            )
            await self._db.commit()
            return cursor.lastrowid
    
    async def get_metric_history(
        self, metric_name: str, limit: int = 100,
    ) -> list[dict]:
        """Get metric history for a given metric name."""
        async with self._lock:
            async with self._db.execute(
                """SELECT * FROM performance_metrics
                   WHERE metric_name = ?
                   ORDER BY timestamp DESC LIMIT ?""",
                (metric_name, limit),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    async def get_metric_stats(self, metric_name: str) -> dict:
        """Get aggregate stats for a metric."""
        async with self._lock:
            async with self._db.execute(
                """SELECT
                    COUNT(*) as count,
                    AVG(metric_value) as avg_value,
                    MIN(metric_value) as min_value,
                    MAX(metric_value) as max_value
                   FROM performance_metrics WHERE metric_name = ?""",
                (metric_name,),
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else {}
    
    # ================================================================
    # Utility
    # ================================================================
    
    async def execute_raw(self, sql: str, params: tuple = ()) -> list[dict]:
        """Execute raw SQL and return results (for advanced queries)."""
        async with self._lock:
            async with self._db.execute(sql, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    async def vacuum(self) -> None:
        """Vacuum the database to reclaim space."""
        await self._db.execute("VACUUM")
        logger.info("Database vacuumed")
    
    async def backup(self, backup_path: str) -> None:
        """Backup database to file."""
        async with aiosqlite.connect(backup_path) as backup_db:
            await self._db.backup(backup_db)
        logger.info(f"Database backed up to {backup_path}")


# ============================================================
# Singleton access
# ============================================================
_db_manager: DatabaseManager | None = None


def get_db(db_path: str | None = None) -> DatabaseManager:
    """Get global database manager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager(db_path)
    return _db_manager