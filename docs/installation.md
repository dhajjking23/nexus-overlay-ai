# Installation Guide

Complete guide to deploy NEXUS OVERLAY AI on Oracle Cloud VPS (Ubuntu 22.04).

---

## Prerequisites

- Oracle Cloud Free Tier (or any Ubuntu 22.04 VPS)
- SSH access with key authentication
- Domain name (optional, can use IP directly)
- GitHub account

---

## 1. VPS Setup

### Connect to VPS
```bash
ssh -i ~/.ssh/your-key.pem ubuntu@YOUR_VPS_IP
```

### Run Deployment Script
```bash
# Clone repo
git clone https://github.com/dhajjking23/nexus-overlay-ai.git
cd nexus-overlay-ai

# Run installer (needs sudo)
sudo bash deployment/install.sh
```

The script will:
- Install Python 3, pip, venv, git, sqlite3
- Create virtual environment
- Install Python dependencies
- Create `.env` config file
- Initialize SQLite database
- Set up systemd service

---

## 2. Configure Environment

```bash
sudo nano /home/ubuntu/nexus-overlay-ai/.env
```

**Required fields:**
```bash
# Transport
TRANSPORT_HOST=0.0.0.0
TRANSPORT_PORT=8765
HTTP_BRIDGE_PORT=8766
HEALTH_PORT=8767

# Database
DATABASE_PATH=./data/nexus_overlay.db

# Logging
LOG_LEVEL=INFO

# Security - CHANGE THESE!
AUTH_TOKEN=your-random-secure-token-here
SECRET_KEY=another-random-secret-here

# AI Provider (optional - free tier at openrouter.ai)
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxx
```

**Generate secure tokens:**
```bash
# Run on VPS or locally
openssl rand -hex 32
```

---

## 3. Open Oracle Cloud Security List

This is **CRITICAL** — the VPS firewall is separate from Ubuntu ufw.

### Steps:
1. Go to Oracle Cloud Console → **Networking** → **Virtual Cloud Networks**
2. Click your VCN name
3. Under **Resources**, click **Security Lists**
4. Find the security list for your **subnet** (not the VCN default)
5. Click **Add Ingress Rules** → Add these three rules:

| Rule | Source Type | Source CIDR | IP Protocol | Source Port | Destination Port |
|------|-------------|-------------|-------------|-------------|------------------|
| WebSocket | CIDR | 0.0.0.0/0 | TCP | All | 8765 |
| HTTP Bridge | CIDR | 0.0.0.0/0 | TCP | All | 8766 |
| Health | CIDR | 0.0.0.0/0 | TCP | All | 8767 |

6. Click **Add Ingress Rules**

> **Note:** If using a load balancer or reverse proxy, restrict Source CIDR to your proxy IPs.

---

## 4. Start the Service

```bash
sudo systemctl start nexus-overlay
sudo systemctl status nexus-overlay
```

**Expected output:**
```
● nexus-overlay.service - NEXUS OVERLAY AI Backend
     Loaded: loaded (/etc/systemd/system/nexus-overlay.service; enabled; vendor preset: enabled)
     Active: active (running) since Mon 2026-09-15 18:17:42 UTC; 2s ago
   Main PID: 245902 (python3)
      Tasks: 18 (limit: 4680)
     Memory: 37.8M
     CGroup: /system.slice/nexus-overlay.service
             └─245902 /home/ubuntu/nexus-overlay-ai/venv/bin/python3 -m backend.main
```

### View logs
```bash
sudo journalctl -u nexus-overlay -f
```

---

## 5. Verify Endpoints

```bash
# Local verification
curl http://localhost:8767/health
curl http://localhost:8766/
curl -X POST http://localhost:8766/message -H "Content-Type: application/json" -d '{"protocol_version":"1.0","message_type":"MARKET_TICK","sequence":1,"symbol":"XAUUSD","timeframe":"TICK","payload":{"bid":2500.50,"ask":2500.75,"spread":0.25,"volume":100}}'

# Public verification (from your local machine)
curl http://YOUR_VPS_IP:8767/health
curl http://YOUR_VPS_IP:8766/
```

**Expected health response:**
```json
{
  "status": "ok",
  "uptime_seconds": 45.2,
  "version": "1.0.0",
  "engines_loaded": 16,
  "mt5_connected": false,
  "android_connected": false
}
```

---

## 6. MT5 EA Setup

### On Windows Machine with MetaTrader 5:

1. **Copy EA files:**
   ```
   bridge/MQL5/NexusDataBridgeEA.mq5 → <MT5 Data Folder>/MQL5/Experts/
   bridge/MQL5/NexusOverlayIndicator.mq5 → <MT5 Data Folder>/MQL5/Indicators/
   ```

2. **Open MetaEditor (F4 in MT5), compile both files (F7)**

3. **Attach EA to XAUUSD chart:**
   - Drag `NexusDataBridgeEA` onto XAUUSD chart
   - Enable **Allow WebRequest for listed URL** → Add: `http://YOUR_VPS_IP:8766`

4. **Critical EA Inputs:**
   | Input | Value |
   |-------|-------|
   | `InpUseHTTP` | `true` |
   | `InpHTTPHost` | `YOUR_VPS_IP` (e.g., `161.118.225.156`) |
   | `InpHTTPPort` | `8766` |
   | `InpAuthToken` | (match `.env` AUTH_TOKEN, or leave empty) |
   | `InpSendTicks` | `true` |
   | `InpSendCandles` | `true` |
   | `InpHeartbeatSec` | `5` |

5. **Check Experts tab** for connection logs:
   ```
   [NexusBridge] HTTP connected to 161.118.225.156:8766
   [NexusBridge] Closed candle detected: M5 2026.09.15 18:20:00
   ```

---

## 7. Android App Setup

### Build APK
1. Open `android/` folder in **Android Studio Ladybug+**
2. **File** → **Open** → select `android/`
3. Wait for Gradle sync
4. **Build** → **Build Bundle(s)/APK(s)** → **Build APK(s)**
5. Click **locate** → copy `app-debug.apk` to phone

### Install & Configure
1. Install APK on Android device
2. **Grant permissions when prompted:**
   - `Display over other apps` (SYSTEM_ALERT_WINDOW)
   - `Network access`
3. Open app → **Settings**:
   - Server Host: `YOUR_VPS_IP` (e.g., `161.118.225.156`)
   - Server Port: `8765`
   - Auth Token: (match `.env` AUTH_TOKEN, or leave empty)
   - Overlay Mode: `Standard`
   - Auto Connect: `On`
4. Tap **Connect** → wait for "Connected" status
5. Tap **Start Overlay** → grant overlay permission if asked
6. Overlay appears on screen with real-time signal data

---

## 8. Troubleshooting

### Service won't start
```bash
# Check logs
sudo journalctl -u nexus-overlay -n 50

# Common issues:
# - Port already in use: sudo lsof -i :8765
# - Missing .env: check /home/ubuntu/nexus-overlay-ai/.env exists
# - Python path: ensure venv is activated in service file
```

### Ports not accessible externally
```bash
# Verify service is listening on 0.0.0.0 (not 127.0.0.1)
ss -tlnp | grep 8765

# Check Oracle Security List again — this is the #1 cause
# ufw on Ubuntu is usually disabled/inactive
sudo ufw status
```

### MT5 EA not connecting
```bash
# Check EA logs in MT5 Experts tab
# Verify HTTP bridge is running:
curl http://YOUR_VPS_IP:8766/

# Test from MT5 machine:
curl -X POST http://YOUR_VPS_IP:8766/message -H "Content-Type: application/json" -d '{"protocol_version":"1.0","message_type":"HEARTBEAT","sequence":1,"symbol":"XAUUSD","timeframe":"TICK","payload":{"client_type":"TEST"}}'
```

### Android app not connecting
- Verify WebSocket port 8765 is open in Oracle Security List
- Check server IP/port in app settings
- If AUTH_TOKEN is set in .env, must match in app settings
- Check VPS logs: `sudo journalctl -u nexus-overlay -f`

---

## 9. Maintenance

### Update code
```bash
cd /home/ubuntu/nexus-overlay-ai
git pull origin main
sudo systemctl restart nexus-overlay
```

### Backup database
```bash
cp /home/ubuntu/nexus-overlay-ai/data/nexus_overlay.db /home/ubuntu/backups/nexus_$(date +%F).db
```

### View resource usage
```bash
systemctl status nexus-overlay
# Memory: should stay under 200MB
# CPU: should be < 5% idle, spikes on tick processing
```

---

## 10. Security Notes

- **Always change default AUTH_TOKEN and SECRET_KEY**
- **Restrict Security List CIDR** if you have static IPs
- **Use HTTPS reverse proxy** (nginx + certbot) for production
- **Monitor logs** for unauthorized connection attempts
- **Keep VPS updated**: `sudo apt update && sudo apt upgrade -y`

---

## Quick Reference

| Service | Port | Protocol | Auth Required |
|---------|------|----------|---------------|
| WebSocket | 8765 | WS | If AUTH_TOKEN set |
| HTTP Bridge | 8766 | HTTP POST | If AUTH_TOKEN set |
| Health | 8767 | HTTP GET | No |

| Config File | Location |
|-------------|----------|
| Main config | `config/default_config.yaml` |
| Environment | `/home/ubuntu/nexus-overlay-ai/.env` |
| Service file | `/etc/systemd/system/nexus-overlay.service` |
| Database | `/home/ubuntu/nexus-overlay-ai/data/nexus_overlay.db` |
| Logs | `sudo journalctl -u nexus-overlay` |

---

## Support

- Issues: https://github.com/dhajjking23/nexus-overlay-ai/issues
- Architecture: `docs/architecture.md`
- Protocol: `docs/protocol.md`