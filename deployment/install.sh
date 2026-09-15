#!/bin/bash
# NEXUS OVERLAY AI — Deployment Script for Ubuntu VPS
# Usage: sudo bash deployment/install.sh
# Run from the project directory or after cloning the repo.

set -euo pipefail

echo "============================================"
echo "  NEXUS OVERLAY AI — Installation Script"
echo "============================================"

# --- Configuration ---
PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/nexus-overlay-ai}"
PYTHON_VERSION="python3"
VENV_DIR="$PROJECT_DIR/venv"
GIT_REPO="https://github.com/dhajjking23/nexus-overlay-ai.git"

# --- System Dependencies ---
echo "[1/8] Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv git sqlite3 curl

# --- Create Project Directory ---
echo "[2/8] Setting up project directory..."
if [ ! -d "$PROJECT_DIR" ]; then
    git clone "$GIT_REPO" "$PROJECT_DIR"
else
    cd "$PROJECT_DIR"
    git pull origin main 2>/dev/null || true
fi

mkdir -p "$PROJECT_DIR/data/backups"
mkdir -p "$PROJECT_DIR/logs"
cd "$PROJECT_DIR"

# --- Python Virtual Environment ---
echo "[3/8] Setting up Python virtual environment..."
if [ ! -d "$VENV_DIR" ]; then
    $PYTHON_VERSION -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"

# --- Install Python Dependencies ---
echo "[4/8] Installing Python dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

# --- Configuration ---
echo "[5/8] Setting up configuration..."
if [ ! -f "$PROJECT_DIR/.env" ]; then
    cat > "$PROJECT_DIR/.env" << 'ENVEOF'
# NEXUS OVERLAY AI - Environment Configuration
# Transport
TRANSPORT_HOST=0.0.0.0
TRANSPORT_PORT=8765
HTTP_BRIDGE_PORT=8766
HEALTH_PORT=8767

# Database
DATABASE_PATH=./data/nexus_overlay.db

# Logging
LOG_LEVEL=INFO

# Security (CHANGE THESE!)
AUTH_TOKEN=CHANGE_ME_TO_A_RANDOM_STRING
SECRET_KEY=CHANGE_ME_TO_A_RANDOM_STRING

# AI Provider (add your key or leave empty for deterministic mode)
OPENROUTER_API_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
ENVEOF
    chmod 600 "$PROJECT_DIR/.env"
    echo ">>> IMPORTANT: Edit $PROJECT_DIR/.env with your API keys and auth tokens <<<"
else
    echo ".env already exists, skipping."
fi

# --- Database Initialization ---
echo "[6/8] Initializing database..."
cd "$PROJECT_DIR"
source "$VENV_DIR/bin/activate"
$PYTHON_VERSION -c "
import asyncio, os, sys
sys.path.insert(0, '.')
from backend.database.db import DatabaseManager
db = DatabaseManager(os.getenv('DATABASE_PATH', './data/nexus_overlay.db'))
asyncio.run(db.initialize())
print('Database initialized.')
asyncio.run(db.close())
" 2>/dev/null || echo "Database init skipped (will auto-create on first run)"

# --- Systemd Service ---
echo "[7/8] Setting up systemd service..."
# Run as ubuntu user if exists, else root
SVC_USER="ubuntu"
if ! id -u "$SVC_USER" &>/dev/null; then
    SVC_USER="root"
fi

cat > /etc/systemd/system/nexus-overlay.service << SVCEOF
[Unit]
Description=NEXUS OVERLAY AI Backend
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=$SVC_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$VENV_DIR/bin/python3 -m backend.main
Restart=always
RestartSec=5
TimeoutStopSec=15

EnvironmentFile=-$PROJECT_DIR/.env
Environment=PYTHONUNBUFFERED=1

LimitNOFILE=65536
MemoryMax=512M

StandardOutput=journal
StandardError=journal
SyslogIdentifier=nexus-overlay

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable nexus-overlay.service

# --- Verify Ports ---
echo "[8/8] Checking network ports..."
PORTS="8765:WebSocket 8766:HTTP-Bridge 8767:Health"
for entry in $PORTS; do
    port="${entry%%:*}"
    name="${entry##*:}"
    echo "  Port $port ($name) — ensure this is open in Oracle Cloud Security List"
done

echo ""
echo "============================================"
echo "  Installation Complete!"
echo "============================================"
echo ""
echo "OPEN PORTS IN ORACLE CLOUD CONSOLE:"
echo "  1. Go to: https://cloud.oracle.com/networking/security-lists"
echo "  2. Find your VPS subnet's Security List"
echo "  3. Add Ingress Rules for TCP ports: 8765, 8766, 8767"
echo ""
echo "START THE SERVICE:"
echo "  sudo systemctl start nexus-overlay"
echo "  sudo systemctl status nexus-overlay"
echo "  sudo journalctl -u nexus-overlay -f"
echo ""
echo "VERIFY:"
echo "  curl http://localhost:8767/health    # Health check"
echo "  curl http://localhost:8765            # WebSocket (will show upgrade needed)"
echo ""
echo "ANDROID APP:"
echo "  Set server IP to: YOUR_PUBLIC_IP"
echo "  Set server port to: 8765"
echo "  Set auth token to: (value from .env AUTH_TOKEN)"
echo ""
echo "MT5 EA:"
echo "  Copy bridge/MQL5/NexusDataBridgeEA.mq5 to MT5 Experts folder"
echo "  Set InpUseHTTP = true"
echo "  Set InpHTTPHost = YOUR_PUBLIC_IP"
echo "  Set InpHTTPPort = 8766"
echo ""
