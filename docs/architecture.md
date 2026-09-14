# NEXUS OVERLAY AI — Architecture

## System Overview

Real-Time XAUUSD AI Trading Overlay — modular system that analyzes MT5 market data and displays trading decisions via Android overlay.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────┐
│                    MT5 Platform                      │
│  ┌──────────────┐    ┌─────────────────────────┐    │
│  │ NexusData    │    │ NexusOverlay            │    │
│  │ Bridge EA    │    │ Indicator               │    │
│  │ (MQL5)       │    │ (MQL5)                  │    │
│  └──────┬───────┘    └────────────┬────────────┘    │
│         │ writes JSON files       │ reads signal     │
└─────────┼─────────────────────────┼──────────────────┘
          │                         │
          ▼                         │
┌──────────────────┐                │
│  File Watcher    │                │
│  (Python)        │                │
└────────┬─────────┘                │
         │                          │
         ▼                          │
┌──────────────────────────────────────────────────────┐
│                Python Backend                        │
│                                                      │
│  ┌─────────────────────────────────────────────┐     │
│  │            Transport Layer                   │     │
│  │    (WebSocket Server — port 8765)           │     │
│  └──────────┬──────────────────────┬───────────┘     │
│             │                      │                  │
│             ▼                      │                  │
│  ┌──────────────────┐             │                  │
│  │ Market Data      │◄─────── MT5 EA data            │
│  │ Engine           │                                 │
│  └────────┬─────────┘                                 │
│           │                                           │
│           ▼                                           │
│  ┌──────────────────┐                                 │
│  │ Indicator Engine │ EMA/RSI/MACD/ADX/ATR/BB        │
│  └────────┬─────────┘                                 │
│           │                                           │
│     ┌─────┼─────┬──────────┬──────────┐              │
│     ▼     ▼     ▼          ▼          ▼              │
│  ┌──────┐┌────────┐┌──────────┐┌──────────┐          │
│  │Struct││PriceAct││Liquidity ││Zone Eng  │          │
│  │Engine││Engine  ││Engine    ││          │          │
│  └──┬───┘└───┬────┘└────┬─────┘└────┬─────┘          │
│     │        │          │           │                 │
│     └────────┴──────────┴───────────┘                 │
│                    │                                  │
│              ┌─────▼──────┐                           │
│              │ MTF Engine  │ Multi-timeframe           │
│              └─────┬──────┘                           │
│                    │                                  │
│         ┌──────────┼──────────┐                       │
│         ▼          ▼          ▼                       │
│  ┌──────────┐┌──────────┐┌──────────┐                │
│  │Session   ││Regime    ││Confluence│                │
│  │Engine    ││Engine    ││Engine    │                │
│  └────┬─────┘└────┬─────┘└────┬─────┘                │
│       │           │           │                       │
│       └───────────┴───────────┘                       │
│                   │                                   │
│            ┌──────▼──────┐                            │
│            │Strategy Eng │ 6 strategies               │
│            └──────┬──────┘                            │
│                   │                                   │
│            ┌──────▼──────┐                            │
│            │Risk Engine  │ Validation gate            │
│            └──────┬──────┘                            │
│                   │                                   │
│      ┌────────────┼────────────┐                      │
│      ▼            ▼            ▼                      │
│ ┌─────────┐ ┌─────────┐ ┌─────────┐                 │
│ │Entry Eng│ │SL Engine│ │TP Engine│                 │
│ └────┬────┘ └────┬────┘ └────┬────┘                 │
│      └────────────┴───────────┘                      │
│                   │                                   │
│            ┌──────▼──────┐                            │
│            │ Confidence  │                            │
│            │ Model       │                            │
│            └──────┬──────┘                            │
│                   │                                   │
│            ┌──────▼──────┐                            │
│            │ AI Analysis │ OpenAI/Claude/Local         │
│            └──────┬──────┘                            │
│                   │                                   │
│            ┌──────▼──────┐                            │
│            │ Decision    │ SINGLE SOURCE OF TRUTH     │
│            │ Engine      │ BUY / SELL / WAIT          │
│            └──────┬──────┘                            │
│                   │                                   │
│  ┌────────────────┴──────────────────────┐            │
│  │         Signal / Event Bus            │            │
│  │    (WebSocket broadcast to clients)   │            │
│  └────────────────┬──────────────────────┘            │
│                   │                                   │
│            ┌──────▼──────┐                            │
│            │ Safety      │ Global safety layer        │
│            │ Governor    │                            │
│            └─────────────┘                            │
│                                                      │
│  ┌──────────────┐  ┌──────────────┐                  │
│  │ Database     │  │ Replay       │                  │
│  │ (SQLite)     │  │ Engine       │                  │
│  └──────────────┘  └──────────────┘                  │
└──────────────────────┬───────────────────────────────┘
                       │ WebSocket
                       ▼
┌──────────────────────────────────────────────────────┐
│              Android Application                     │
│  ┌──────────────────────────────────────────────┐    │
│  │  WebSocket Client ──► Signal Store           │    │
│  │                            │                  │    │
│  │              ┌─────────────┴─────────┐        │    │
│  │              ▼                       ▼        │    │
│  │     ┌─────────────┐  ┌──────────────────┐    │    │
│  │     │ Overlay     │  │ Dashboard        │    │    │
│  │     │ Service     │  │ (Full UI)        │    │    │
│  │     │ (Floating)  │  │                  │    │    │
│  │     └─────────────┘  └──────────────────┘    │    │
│  └──────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────┘
```

## Data Flow

1. MT5 EA collects XAUUSD tick/candle data → writes JSON files
2. File watcher reads → Python Market Data Engine normalizes
3. Engines run in sequence (indicators → structure → MTF → strategies → risk → decision)
4. Decision Engine produces FINAL BUY/SELL/WAIT signal
5. Signal broadcasts via WebSocket to connected Android clients
6. Android overlay renders signal above MT5 app

## Key Design Principles

- **Decision Engine = Single Source of Truth** — no other module can publish final decisions
- **Risk Engine = Safety Gate** — must validate before any BUY/SELL signal
- **AI = Analytical Assistant** — can never bypass Risk or Decision engines
- **No fabrication** — missing data = WAIT, uncertain = WAIT, conflicting = WAIT
- **Modular & extensible** — adding symbols/brokers/strategies doesn't require rewrite

## Technology Stack

| Component | Technology |
|-----------|-----------|
| MT5 Bridge | MQL5 Expert Advisor |
| Backend | Python 3.10+ / asyncio |
| Transport | WebSocket (websockets lib) |
| Database | SQLite (aiosqlite) |
| AI | OpenAI / Claude / Local (Ollama) |
| Android | Kotlin / Jetpack Compose |
| Overlay | SYSTEM_ALERT_WINDOW service |

## Safety Rules

1. ANALYSIS is separated from EXECUTION — first version is analysis-only
2. No auto-trading by default
3. No AI override of risk rules
4. Signals expire after configurable candles
5. Old signals visually marked as stale in offline mode
