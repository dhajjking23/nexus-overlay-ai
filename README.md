# 🔴 NEXUS OVERLAY AI

**Real-Time XAUUSD AI Trading Overlay**

MT5 → Python Backend → Android Overlay — modular, auditable, deterministic trading intelligence.

---

## Architecture

```
MT5 EA → HTTP Bridge (port 8766) → Python Backend (20+ engines) → WebSocket (port 8765) → Android Overlay
                              ↘ Health Check (port 8767)
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
| AI Layer | OpenAI/Claude/OpenRouter/Local with fallback |
| Decision Engine | **SINGLE SOURCE OF TRUTH** — BUY/SELL/WAIT |
| Safety Governor | Global safety checks |
| Event Bus | Async pub/sub for decoupled modules |

### Transport Layer

| Endpoint | Port | Protocol | Purpose |
|----------|------|----------|---------|
| WebSocket Server | 8765 | WebSocket | Backend ↔ Android, Backend ↔ MT5 (WS capable) |
| HTTP Bridge | 8766 | HTTP POST | **MT5 EA pushes ticks/candles** (EA cannot use WS) |
| Health Check | 8767 | HTTP GET | `/health` + `/status` for monitoring |

### Components

| Component | Tech | Location |
|-----------|------|----------|
| MT5 Bridge | MQL5 EA + Indicator | `bridge/MQL5/` |
| Backend | Python 3.10+ / asyncio | `backend/` |
| WebSocket Transport | websockets library | `backend/transport/websocket_server.py` |
| HTTP Bridge | aiohttp.web | `backend/transport/http_bridge.py` |
| Auth/RateLimit | hmac + token bucket | `backend/auth.py` |
| Health Server | aiohttp.web | `backend/health.py` |
| Database | SQLite (aiosqlite) | `backend/database/` |
| AI | OpenAI / Claude / OpenRouter / Ollama | `backend/ai/` |
| Android | Kotlin / Jetpack Compose | `android/` |
| Overlay | SYSTEM_ALERT_WINDOW | `android/.../overlay/` |

## Quick Start

### Backend (VPS)

```bash
# 1. Clone
git clone https://github.com/dhajjking23/nexus-overlay-ai.git
cd nexus-overlay-ai

# 2. Run deployment script (installs deps, creates .env, sets up systemd)
sudo bash deployment/install.sh

# 3. Edit .env with your API keys
sudo nano /home/ubuntu/nexus-overlay-ai/.env

# 4. Open ports in Oracle Cloud Console (Security List):
#    - TCP 8765 (WebSocket)
#    - TCP 8766 (HTTP Bridge for MT5 EA)
#    - TCP 8767 (Health check)

# 5. Start
sudo systemctl start nexus-overlay
sudo systemctl status nexus-overlay
sudo journalctl -u nexus-overlay -f
```

### MT5 Expert Advisor

1. Copy `bridge/MQL5/NexusDataBridgeEA.mq5` → MT5 `MQL5/Experts/`
2. Copy `bridge/MQL5/NexusOverlayIndicator.mq5` → MT5 `MQL5/Indicators/`
3. Compile in MetaEditor (F7)
4. Attach `NexusDataBridgeEA` to XAUUSD chart
5. **EA Inputs (critical):**
   - `InpUseHTTP = true` (use HTTP bridge, not file bridge)
   - `InpHTTPHost = YOUR_VPS_PUBLIC_IP` (e.g., `161.118.225.156`)
   - `InpHTTPPort = 8766` (HTTP Bridge port)
   - `InpAuthToken = (value from .env AUTH_TOKEN, if set)`

### Android App

1. Open `android/` folder in Android Studio
2. Build → Make Project → Build Bundle(s)/APK(s) → Build APK(s)
3. Install on device
4. **Grant SYSTEM_ALERT_WINDOW permission** when prompted
5. Open app → Settings:
   - Server Host: `YOUR_VPS_PUBLIC_IP` (e.g., `161.118.225.156`)
   - Server Port: `8765` (WebSocket)
   - Auth Token: (value from .env AUTH_TOKEN, if set — leave empty if not configured)
6. Tap **Connect** → **Start Overlay**

## Verification Endpoints

```bash
# Health check
curl http://YOUR_VPS_IP:8767/health
# {"status": "ok", "uptime_seconds": 123, "version": "1.0.0", "engines_loaded": 16, "mt5_connected": false, "android_connected": false}

# Full system status
curl http://YOUR_VPS_IP:8767/status
# Returns WebSocket server status with connected clients

# HTTP Bridge status
curl http://YOUR_VPS_IP:8766/
# {"service": "nexus-overlay-http-bridge", "running": true, ...}

# Test tick push (simulate MT5 EA)
curl -X POST http://YOUR_VPS_IP:8766/message \
  -H "Content-Type: application/json" \
  -d '{"protocol_version":"1.0","message_type":"MARKET_TICK","sequence":1,"symbol":"XAUUSD","timeframe":"TICK","payload":{"bid":2500.50,"ask":2500.75,"spread":0.25,"volume":100}}'
# {"status": "ok", "sequence": 1, "message_type": "MARKET_TICK"}
```

## Configuration

All config in `config/default_config.yaml` with env variable overrides. See `config/.env.example`.

Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `TRANSPORT_PORT` | 8765 | WebSocket port |
| `HTTP_BRIDGE_PORT` | 8766 | HTTP Bridge port |
| `HEALTH_PORT` | 8767 | Health check port |
| `AUTH_TOKEN` | (empty) | Optional auth token for all connections |
| `SECRET_KEY` | (empty) | Internal secret for rate limiting |
| `OPENROUTER_API_KEY` | (empty) | AI provider key (free tier at openrouter.ai) |
| `LOG_LEVEL` | INFO | Logging level |

**When AUTH_TOKEN is set:** All connections (WS + HTTP) must include it.

## Key Principles

- **Decision Engine = Single Source of Truth** — only it can publish BUY/SELL/WAIT
- **Risk Engine = Safety Gate** — must validate before any signal
- **AI = Assistant** — never bypasses risk rules
- **No fabrication** — uncertain = WAIT, missing data = WAIT
- **Analysis ≠ Execution** — first version is analysis-only, no auto-trading
- **Auth is optional** — if no token configured, all connections allowed

## Documentation

- [Architecture](docs/architecture.md)
- [Protocol](docs/protocol.md)
- [Decision Model](docs/decision_model.md)
- [Database Schema](docs/database_schema.md)
- [Installation](docs/installation.md)
- [Development Guide](docs/development.md)

## License

MIT