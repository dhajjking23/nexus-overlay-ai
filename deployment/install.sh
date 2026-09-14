#!/bin/bash
# NEXUS OVERLAY AI — Deployment Script for Ubuntu VPS
# Usage: sudo bash deployment/install.sh

set -e

echo "============================================"
echo "  NEXUS OVERLAY AI — Installation Script"
echo "============================================"

PROJECT_DIR="/opt/nexus-overlay-ai"
PYTHON_VERSION="python3"
VENV_DIR="$PROJECT_DIR/venv"

# --- System Dependencies ---
echo "[1/7] Installing system dependencies..."
apt update
apt install -y python3 python3-pip python3-venv git sqlite3

# --- Create Project Directory ---
echo "[2/7] Setting up project directory..."
mkdir -p "$PROJECT_DIR"
mkdir -p "$PROJECT_DIR/data/backups"
mkdir -p "$PROJECT_DIR/logs"

# If repo exists, pull latest. Otherwise clone.
if [ -d "$PROJECT_DIR/.git" ]; then
    cd "$PROJECT_DIR"
    git pull origin main
else
    cd /opt
    git clone https://github.com/YOUR_USERNAME/nexus-overlay-ai.git
    mv nexus-overlay-ai "$PROJECT_DIR" 2>/dev/null || true
    cd "$PROJECT_DIR"
fi

# --- Python Virtual Environment ---
echo "[3/7] Setting up Python virtual environment..."
$PYTHON_VERSION -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

# --- Install Python Dependencies ---
echo "[4/7] Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# --- Configuration ---
echo "[5/7] Setting up configuration..."
if [ ! -f "$PROJECT_DIR/.env" ]; then
    cp "$PROJECT_DIR/config/.env.example" "$PROJECT_DIR/.env"
    echo ">>> Please edit $PROJECT_DIR/.env with your API keys <<<"
fi

# --- Database Initialization ---
echo "[6/7] Initializing database..."
cd "$PROJECT_DIR"
source "$VENV_DIR/bin/activate"
python -c "
import asyncio
from backend.database.db import DatabaseManager
asyncio.run(DatabaseManager.initialize())
print('Database initialized.')
"

# --- Systemd Service ---
echo "[7/7] Setting up systemd service..."
cat > /etc/systemd/system/nexus-overlay.service << 'EOF'
[Unit]
Description=Nexus Overlay AI - Real-Time XAUUSD Trading Backend
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/nexus-overlay-ai
ExecStart=/opt/nexus-overlay-ai/venv/bin/python -m backend.main
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
Environment=LOG_LEVEL=INFO

# Resource limits
MemoryMax=512M
CPUQuota=80%

# Logging
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable nexus-overlay.service

echo ""
echo "============================================"
echo "  Installation Complete!"
echo "============================================"
echo ""
echo "Next steps:"
echo "  1. Edit /opt/nexus-overlay-ai/.env with your API keys"
echo "  2. Start: sudo systemctl start nexus-overlay"
echo "  3. Status: sudo systemctl status nexus-overlay"
echo "  4. Logs: sudo journalctl -u nexus-overlay -f"
echo "  5. WebSocket: ws://YOUR_IP:8765"
echo ""
