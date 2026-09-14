# 🔴 NEXUS OVERLAY AI

**Real-Time XAUUSD AI Trading Overlay**

MT5 → Python Backend → Android Overlay — modular, auditable, deterministic trading intelligence.

---

## Architecture

```
MT5 EA → WebSocket → Python Backend (20+ engines) → WebSocket → Android Overlay
```

### Engine Pipeline

| Engine | Purpose |
|--------|---------|
| Market Data Engine | Tick normalization, candle construction, timeframe aggregation |
| Indicator Engine | EMA, RSI, MACD, ADX, ATR, Bollinger (pure Python) |
| Price Action Engine | 16 pattern types with context |
| Structure Engine | HH/HL/LH/LL, BOS, CHOCH detection |
| Liquidity Engine | Sweeps, stop runs, equal levels |
| Zone Engine | S/R, order blocks, fair value gaps |
| MTF Engine | Hierarchical 7-timeframe analysis |
| Session Engine | Asian/London/NY detection |
| Regime Engine | Trending/range/volatility classification |
| Strategy Engine | 6 independent strategies |
| Confluence Engine | Weighted evidence matrix |
| Risk Engine | Pre-trade validation gate |
| Entry/SL/TP Engine | Dynamic price calculation |
| Confidence Model | Structured confidence scoring |
| AI Layer | OpenAI/Claude/Local with fallback |
| Decision Engine | **SINGLE SOURCE OF TRUTH** — BUY/SELL/WAIT |
| Safety Governor | Global safety checks |
| Event Bus | Async pub/sub for decoupled modules |

### Components

| Component | Tech | Location |
|-----------|------|----------|
| MT5 Bridge | MQL5 EA + Indicator | `bridge/MQL5/` |
| Backend | Python 3.10+ / asyncio | `backend/` |
| Transport | WebSocket (port 8765) | `backend/transport/` |
| Database | SQLite (aiosqlite) | `backend/database/` |
| AI | OpenAI / Claude / Ollama | `backend/ai/` |
| Android | Kotlin / Jetpack Compose | `android/` |
| Overlay | SYSTEM_ALERT_WINDOW | `android/.../overlay/` |

## Quick Start

### Backend
```bash
git clone https://github.com/YOUR_USERNAME/nexus-overlay-ai.git
cd nexus-overlay-ai
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp config/.env.example .env  # Edit with your keys
python -m backend.main
```

### MT5
1. Copy `bridge/MQL5/NexusDataBridgeEA.mq5` → MT5 `MQL5/Experts/`
2. Copy `bridge/MQL5/NexusOverlayIndicator.mq5` → MT5 `MQL5/Indicators/`
3. Compile in MetaEditor
4. Attach EA to XAUUSD chart

### Android
1. Open `android/` in Android Studio
2. Build & install
3. Grant overlay permission
4. Configure server IP
5. Start overlay

## Key Principles

- **Decision Engine = Single Source of Truth** — only it can publish BUY/SELL/WAIT
- **Risk Engine = Safety Gate** — must validate before any signal
- **AI = Assistant** — never bypasses risk rules
- **No fabrication** — uncertain = WAIT, missing data = WAIT
- **Analysis ≠ Execution** — first version is analysis-only, no auto-trading

## Configuration

All config in `config/default_config.yaml` with env variable overrides. See `config/.env.example`.

## Documentation

- [Architecture](docs/architecture.md)
- [Protocol](docs/protocol.md)
- [Decision Model](docs/decision_model.md)
- [Database Schema](docs/database_schema.md)
- [Installation](docs/installation.md)
- [Development Guide](docs/development.md)

## License

MIT
