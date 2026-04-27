#!/bin/bash
# ─────────────────────────────────────────────────────────────────
#  System Monitor Daemon — Installer
#  Run as root:  sudo bash install.sh
# ─────────────────────────────────────────────────────────────────

set -e

INSTALL_DIR="/opt/system_monitor"
SERVICE_NAME="system-monitor"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
LOG_FILE="/var/log/system_monitor.log"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║      System Monitor Daemon — Installer       ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ── 1. Root check ─────────────────────────────────
if [[ $EUID -ne 0 ]]; then
  echo "❌  Please run as root:  sudo bash install.sh"
  exit 1
fi

# ── 2. Install Python deps ─────────────────────────
echo "📦  Installing Python dependencies..."
pip3 install psutil requests --quiet

# ── 3. Copy files ──────────────────────────────────
echo "📂  Copying files to ${INSTALL_DIR}..."
mkdir -p "$INSTALL_DIR"
cp monitor.py "$INSTALL_DIR/monitor.py"
chmod 750 "$INSTALL_DIR/monitor.py"

# ── 4. Touch log file ─────────────────────────────
touch "$LOG_FILE"
chmod 640 "$LOG_FILE"
echo "📝  Log file: ${LOG_FILE}"

# ── 5. Install systemd service ────────────────────
echo "⚙️   Installing systemd service..."
cp system-monitor.service "$SERVICE_FILE"
chmod 644 "$SERVICE_FILE"

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

# ── 6. Status check ───────────────────────────────
echo ""
echo "✅  Installation complete!"
echo ""
systemctl status "$SERVICE_NAME" --no-pager -l
echo ""
echo "─────────────────────────────────────────────"
echo "  Useful commands:"
echo "  View live logs  →  tail -f ${LOG_FILE}"
echo "  Stop daemon     →  sudo systemctl stop ${SERVICE_NAME}"
echo "  Start daemon    →  sudo systemctl start ${SERVICE_NAME}"
echo "  Check status    →  sudo systemctl status ${SERVICE_NAME}"
echo "  Uninstall       →  sudo systemctl disable --now ${SERVICE_NAME} && rm ${SERVICE_FILE}"
echo "─────────────────────────────────────────────"
echo ""
