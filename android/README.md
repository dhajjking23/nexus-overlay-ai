# Nexus Overlay AI - Android App

## Overview

Real-time trading signal overlay for Android. Receives signals from the Nexus Overlay AI Python backend via WebSocket and displays them as a floating overlay on top of any trading app.

## Architecture

### Tech Stack
- **Language**: Kotlin
- **UI**: Jetpack Compose (Material 3)
- **Architecture**: MVVM with ViewModel + StateFlow
- **Networking**: OkHttp WebSocket client
- **DI**: Manual (no Hilt/Dagger for simplicity)
- **Min SDK**: 26 (Android 8.0)
- **Target SDK**: 34 (Android 14)

### Key Components

```
┌─────────────────────────────────────────┐
│              MainActivity                │
│  ┌──────────────────────────────────┐   │
│  │        Compose UI                 │   │
│  │  ┌──────────┐  ┌──────────────┐  │   │
│  │  │Dashboard │  │  Settings    │  │   │
│  │  │ Screen   │  │  Screen      │  │   │
│  │  └────┬─────┘  └──────┬───────┘  │   │
│  └───────┼───────────────┼──────────┘   │
│          │               │              │
│  ┌───────▼───────────────▼──────────┐   │
│  │          MainViewModel           │   │
│  │     (StateFlow + actions)        │   │
│  └───────┬───────────────┬──────────┘   │
│          │               │              │
│  ┌───────▼─────┐  ┌──────▼──────────┐  │
│  │ WebSocket   │  │  SignalStore    │  │
│  │ Client      │  │  (StateFlow)    │  │
│  └─────────────┘  └─────────────────┘  │
│                                         │
│  ┌──────────────────────────────────┐   │
│  │       OverlayService             │   │
│  │  (SYSTEM_ALERT_WINDOW)           │   │
│  │  Compact / Standard / Pro modes  │   │
│  └──────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

### Data Flow

1. **WebSocket Client** connects to Python backend (ws://host:port)
2. **SignalStore** receives parsed signals and exposes as StateFlow
3. **MainViewModel** observes SignalStore and manages UI state
4. **DashboardScreen** shows full signal details, MTF matrix, regime info
5. **OverlayService** draws floating window with signal info
6. **OverlayComposables** render Compact/Standard/Pro overlay modes

## Setup

### Prerequisites
- Android Studio Hedgehog (2023.1.1) or later
- JDK 17+
- Android SDK 34

### Build & Run

```bash
cd android/
./gradlew assembleDebug
```

Or open in Android Studio and run on device/emulator.

### Configuration

1. Open the app
2. Go to Settings
3. Enter WebSocket server address (default: `ws://192.168.1.100:8765`)
4. Enable overlay mode
5. Grant SYSTEM_ALERT_WINDOW permission when prompted

## Permissions

| Permission | Purpose |
|---|---|
| `INTERNET` | WebSocket connection to backend |
| `ACCESS_NETWORK_STATE` | Check network availability |
| `SYSTEM_ALERT_WINDOW` | Floating overlay window |
| `FOREGROUND_SERVICE` | Keep overlay alive in background |
| `POST_NOTIFICATIONS` | Show connection status notifications |

## Overlay Modes

### Compact Mode
- Small floating pill showing signal direction + price
- Minimal footprint, tap to expand
- 48dp height, auto-hide after 10s

### Standard Mode
- Medium panel with signal info, entry, SL, TP levels
- Draggable, resizable
- ~200dp height

### Pro Mode
- Full dashboard with MTF matrix, regime, evidence
- All 7 timeframes displayed
- ~400dp height

## Message Protocol

Messages received via WebSocket follow:

```json
{
  "protocol_version": "1.0",
  "message_type": "SIGNAL_UPDATE",
  "sequence": 42,
  "symbol": "XAUUSD",
  "timeframe": "M5",
  "timestamp": "2024-01-15T10:30:00Z",
  "payload": {
    "signal": "BUY",
    "entry": 2045.50,
    "sl": 2040.00,
    "tp1": 2050.00,
    "tp2": 2055.00,
    "tp3": 2060.00,
    "confidence": 0.85,
    "mtf_matrix": {...},
    "regime": "trending_up",
    "evidence": [...]
  }
}
```

## Project Structure

```
android/
├── app/
│   ├── build.gradle.kts
│   └── src/main/
│       ├── AndroidManifest.xml
│       └── java/com/nexus/overlay/
│           ├── MainActivity.kt
│           ├── data/
│           │   ├── WebSocketClient.kt
│           │   └── SignalStore.kt
│           ├── viewmodel/
│           │   └── MainViewModel.kt
│           └── ui/
│               ├── theme/
│               │   └── Theme.kt
│               ├── overlay/
│               │   ├── OverlayService.kt
│               │   └── OverlayComposables.kt
│               ├── dashboard/
│               │   └── DashboardScreen.kt
│               └── settings/
│                   └── SettingsScreen.kt
├── build.gradle.kts
└── README.md
```
