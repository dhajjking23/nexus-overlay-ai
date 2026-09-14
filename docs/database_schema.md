# NEXUS OVERLAY AI — Database Schema (SQLite)

## Tables

### market_data
Stores aggregated candle data per timeframe.

```sql
CREATE TABLE market_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    open_price REAL NOT NULL,
    high_price REAL NOT NULL,
    low_price REAL NOT NULL,
    close_price REAL NOT NULL,
    volume INTEGER NOT NULL,
    spread REAL,
    timestamp INTEGER NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(symbol, timeframe, timestamp)
);

CREATE INDEX idx_market_data_lookup ON market_data(symbol, timeframe, timestamp);
```

### decision_log
Permanent log of every decision produced.

```sql
CREATE TABLE decision_log (
    id TEXT PRIMARY KEY,
    timestamp INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    decision TEXT NOT NULL,  -- BUY, SELL, WAIT
    confidence INTEGER NOT NULL,
    entry_price REAL,
    sl_price REAL,
    tp1_price REAL,
    tp2_price REAL,
    tp3_price REAL,
    rr REAL,
    market_regime TEXT,
    trend TEXT,
    structure TEXT,
    liquidity_state TEXT,
    strategy_scores TEXT,  -- JSON
    indicator_snapshot TEXT,  -- JSON
    evidence TEXT,  -- JSON array
    invalidations TEXT,  -- JSON array
    ai_assessment TEXT,
    data_quality REAL,
    signal_status TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_decision_log_ts ON decision_log(timestamp);
```

### signal_history
Tracks signal lifecycle changes.

```sql
CREATE TABLE signal_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id TEXT NOT NULL,
    state TEXT NOT NULL,  -- NEW, CONFIRMED, ACTIVE, WEAKENING, INVALIDATED, EXPIRED, COMPLETED
    previous_state TEXT,
    reason TEXT,
    timestamp INTEGER NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_signal_history_id ON signal_history(signal_id);
```

### strategy_analysis
Per-strategy assessment history.

```sql
CREATE TABLE strategy_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy TEXT NOT NULL,
    direction TEXT NOT NULL,
    score INTEGER NOT NULL,
    confidence REAL NOT NULL,
    evidence TEXT,  -- JSON array
    timeframe TEXT,
    timestamp INTEGER NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_strategy_analysis_ts ON strategy_analysis(timestamp);
```

### ai_analysis
AI provider responses.

```sql
CREATE TABLE ai_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    assessment TEXT NOT NULL,
    confidence REAL NOT NULL,
    explanation TEXT,
    snapshot_hash TEXT,  -- hash of input market snapshot
    latency_ms INTEGER,
    timestamp INTEGER NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_ai_analysis_ts ON ai_analysis(timestamp);
```

### system_events
System-level events (connections, errors, etc).

```sql
CREATE TABLE system_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,  -- INFO, WARNING, ERROR, CRITICAL
    source TEXT,
    message TEXT NOT NULL,
    details TEXT,  -- JSON
    timestamp INTEGER NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_system_events_type ON system_events(event_type, timestamp);
```

### settings
Key-value settings store.

```sql
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    value_type TEXT DEFAULT 'string',  -- string, int, float, bool, json
    updated_at TEXT DEFAULT (datetime('now'))
);
```

### performance_metrics
System performance tracking.

```sql
CREATE TABLE performance_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    metric_unit TEXT,  -- ms, percent, count, bytes
    timestamp INTEGER NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_perf_metrics_name ON performance_metrics(metric_name, timestamp);
```

### schema_version
Migration tracking.

```sql
CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY,
    description TEXT,
    applied_at TEXT DEFAULT (datetime('now'))
);
```

## Backup Strategy

- Backup database daily via cron
- Retain last 7 backups
- Backup path: `./data/backups/nexus_overlay_YYYYMMDD.db`
