# NEXUS OVERLAY AI — Transport Protocol v1.0

## Overview

JSON-based protocol for real-time communication between MT5 EA, Python Backend, and Android clients.

## Connection

- Transport: WebSocket
- Default port: 8765
- Endpoint: `ws://host:8765`
- Multiple clients can connect simultaneously
- Client types: `MT5_EA`, `ANDROID_APP`

## Message Format

Every message is a JSON object:

```json
{
  "protocol_version": "1.0",
  "message_type": "MARKET_TICK",
  "sequence": 182731,
  "symbol": "XAUUSD",
  "timeframe": "M1",
  "timestamp": 1789180000123,
  "payload": { ... },
  "checksum": "sha256-hex"
}
```

## Message Types

### MT5 → Backend

#### MARKET_TICK
```json
{
  "message_type": "MARKET_TICK",
  "payload": {
    "bid": 3652.42,
    "ask": 3652.65,
    "spread": 0.23,
    "volume": 142,
    "flags": 0
  }
}
```

#### CANDLE_CLOSED
```json
{
  "message_type": "CANDLE_CLOSED",
  "timeframe": "M5",
  "payload": {
    "open": 3650.10,
    "high": 3653.80,
    "low": 3648.50,
    "close": 3652.42,
    "volume": 4521,
    "spread": 0.23,
    "complete": true
  }
}
```

#### SYMBOL_INFO
```json
{
  "message_type": "SYMBOL_INFO",
  "payload": {
    "name": "XAUUSD",
    "digits": 2,
    "point": 0.01,
    "tick_size": 0.01,
    "contract_size": 100,
    "min_lot": 0.01,
    "max_lot": 100.0,
    "spread": 0.23,
    "description": "Gold vs US Dollar"
  }
}
```

#### HEARTBEAT
```json
{
  "message_type": "HEARTBEAT",
  "payload": {
    "client_type": "MT5_EA",
    "uptime_seconds": 3600,
    "connected": true,
    "last_tick_time": 1789180000000
  }
}
```

#### CONNECTION_STATUS
```json
{
  "message_type": "CONNECTION_STATUS",
  "payload": {
    "connected": true,
    "broker": "MetaQuotes-Demo",
    "account": 12345678,
    "trade_allowed": false
  }
}
```

### Backend → Android

#### MARKET_SNAPSHOT
```json
{
  "message_type": "MARKET_SNAPSHOT",
  "payload": {
    "price": 3652.42,
    "bid": 3652.42,
    "ask": 3652.65,
    "spread": 0.23,
    "data_quality": 95
  }
}
```

#### SIGNAL_CREATED / SIGNAL_UPDATED
```json
{
  "message_type": "SIGNAL_CREATED",
  "payload": {
    "signal_id": "sig_20260914_001",
    "decision": "SELL",
    "confidence": 87,
    "entry": 3652.40,
    "sl": 3655.10,
    "tp1": 3649.70,
    "tp2": 3646.80,
    "tp3": 3643.90,
    "rr": 2.1,
    "trend": "BEARISH",
    "regime": "TRENDING_BEARISH",
    "evidence": [
      "H1 bearish structure",
      "M15 bearish structure",
      "M5 lower-high/lower-low",
      "Buy-side liquidity sweep",
      "Bearish engulfing",
      "EMA alignment"
    ],
    "invalidations": [
      "M5 close above 3655.10",
      "Bearish structure broken"
    ],
    "data_quality_score": 92,
    "lifecycle_state": "NEW",
    "timestamp": 1789180000123
  }
}
```

#### SIGNAL_INVALIDATED
```json
{
  "message_type": "SIGNAL_INVALIDATED",
  "payload": {
    "signal_id": "sig_20260914_001",
    "reason": "M5 structure changed to bullish",
    "timestamp": 1789180050000
  }
}
```

#### SYSTEM_STATUS
```json
{
  "message_type": "SYSTEM_STATUS",
  "payload": {
    "status": "ONLINE",
    "mt5_connected": true,
    "data_live": true,
    "ai_ready": true,
    "decision_ready": true,
    "data_quality": 95,
    "websocket_clients": 2
  }
}
```

### Android → Backend

#### CONFIG_UPDATE
```json
{
  "message_type": "CONFIG_UPDATE",
  "payload": {
    "key": "risk.min_rr",
    "value": 2.0
  }
}
```

#### CALIBRATE_OVERLAY
```json
{
  "message_type": "CALIBRATE_OVERLAY",
  "payload": {
    "chart_left": 0,
    "chart_top": 120,
    "chart_width": 1080,
    "chart_height": 1400,
    "price_top": 3700.00,
    "price_bottom": 3600.00
  }
}
```

## Heartbeat & Reconnection

- Heartbeat interval: 5 seconds
- Stale data timeout: 10 seconds
- Reconnect: exponential backoff 1s → 2s → 4s → 8s → 16s → 30s (max)
- Max reconnect attempts: 10
- Sequence validation: reject messages with sequence gaps

## Duplicate Detection

- Backend tracks last sequence number per client
- Duplicate sequences are silently dropped
- Sequence gaps trigger reconnect/sync request

## Checksum

- SHA-256 of payload JSON string
- Optional — used for data integrity verification
- Blank checksum = not verified (allowed for heartbeat)

## Error Messages

```json
{
  "message_type": "ERROR",
  "payload": {
    "code": "STALE_DATA",
    "message": "Data older than 10000ms threshold",
    "severity": "WARNING",
    "recoverable": true
  }
}
```

Error codes: `STALE_DATA`, `MALFORMED_MESSAGE`, `UNSUPPORTED_VERSION`, `SEQUENCE_GAP`, `DUPLICATE`, `RATE_LIMITED`, `INTERNAL_ERROR`
