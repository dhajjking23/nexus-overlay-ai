# NEXUS OVERLAY AI — Installation Guide

## Prerequisites

### VPS / Server
- Ubuntu 22.04+ (or similar Linux)
- Python 3.10+
- 1GB+ RAM
- 10GB+ disk

### MT5 Desktop
- Windows or Linux (via Wine)
- MetaTrader 5 installed
- Account (demo or live)
- XAUUSD symbol available

### Android
- Android 8.0+ (API 26+)
- Overlay permission
- Internet access

---

## Backend Installation (Ubuntu VPS)

```bash
# 1. Clone repository
git clone https://github.com/YOUR_USERNAME/nexus-overlay-ai.git
cd nexus-overlay-ai

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure
cp config/.env.example .env
# Edit .env with your API keys

# 5. Create data directory
mkdir -p data

# 6. Start backend
python -m backend.main
```

Backend will start WebSocket server on port 8765.

## MT5 Setup (Windows or Wine)

### Option A: Native Windows MT5
1. Install MetaTrader 5
2. Copy `bridge/MQL5/NexusDataBridgeEA.mq5` to MT5 data folder:
   `MQL5/Experts/NexusDataBridgeEA.mq5`
3. Compile in MetaEditor
4. Copy `bridge/MQL5/NexusOverlayIndicator.mq5` to:
   `MQL5/Indicators/NexusOverlayIndicator.mq5`
5. Compile in MetaEditor
6. Attach EA to XAUUSD chart
7. Configure EA with backend IP:port

### Option B: Wine on Ubuntu
```bash
# Install Wine
sudo dpkg --add-architecture i386
sudo apt update
sudo apt install -y wine wine32 wine64 winetricks

# Download MT5
wget https://download.mql5.com/cdn/web/12345/mt5setup.exe
wine mt5setup.exe

# Install MT5 (follow wizard)
# Then copy MQL5 files as in Option A
```

## Android Installation

1. Open `android/` folder in Android Studio
2. Build and install on device
3. Grant overlay permission
4. Configure server IP in Settings
5. Open MT5 on device
6. Start overlay service

## Docker Deployment (Alternative)

```bash
docker compose up -d
```

## Systemd Service

```bash
sudo cp deployment/systemd/nexus-overlay.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable nexus-overlay
sudo systemctl start nexus-overlay
```

## Firewall

```bash
# Allow WebSocket port
sudo ufw allow 8765/tcp
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| WebSocket connection refused | Check firewall, ensure backend running |
| MT5 EA not sending data | Check EA logs, verify file permissions |
| Android overlay not showing | Grant SYSTEM_ALERT_WINDOW permission |
| AI not responding | Check API key in .env |
| High CPU | Reduce tick processing, check candle intervals |
