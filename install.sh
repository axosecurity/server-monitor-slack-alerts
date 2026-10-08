#!/bin/bash
# ─────────────────────────────────────────────────────────────────
#  System Monitor Daemon — Automated Installer
#
#  Usage:
#    # One-line install with webhook parameter:
#    curl -sSL https://raw.githubusercontent.com/axosecurity/server-monitor-slack-alerts/master/install.sh | sudo bash -s -- "https://hooks.slack.com/services/..."
#
#    # Interactive install (prompts for webhook):
#    curl -sSL https://raw.githubusercontent.com/axosecurity/server-monitor-slack-alerts/master/install.sh | sudo bash
#
#    # Uninstall:
#    curl -sSL https://raw.githubusercontent.com/axosecurity/server-monitor-slack-alerts/master/install.sh | sudo bash -s -- --uninstall
# ─────────────────────────────────────────────────────────────────

set -e

# Terminal colors
BOLD='\033[1m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
RESET='\033[0m'

INSTALL_DIR="/opt/system_monitor"
CONFIG_DIR="/etc/system_monitor"
ENV_FILE="${CONFIG_DIR}/monitor.env"
SERVICE_NAME="system-monitor"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
LOG_FILE="/var/log/system_monitor.log"
RAW_REPO_BASE="https://raw.githubusercontent.com/axosecurity/server-monitor-slack-alerts/master"

# ── Help / Usage ──────────────────────────────────────────────────
show_help() {
    echo -e "${BOLD}System Monitor Daemon — Installer${RESET}"
    echo ""
    echo "Usage:"
    echo "  sudo bash install.sh [OPTIONS] [WEBHOOK_URL]"
    echo ""
    echo "Options:"
    echo "  -w, --webhook <URL>    Slack incoming webhook URL"
    echo "  -u, --uninstall        Completely remove the daemon and configuration"
    echo "  -h, --help             Show this help message"
    echo ""
    echo "Examples:"
    echo "  sudo bash install.sh \"https://hooks.slack.com/services/...\""
    echo "  sudo bash install.sh --webhook \"https://hooks.slack.com/services/...\""
    echo "  sudo bash install.sh --uninstall"
    exit 0
}

# ── Uninstall routine ─────────────────────────────────────────────
do_uninstall() {
    echo ""
    echo -e "${BOLD}${RED}╔══════════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}${RED}║     System Monitor Daemon — Uninstaller      ║${RESET}"
    echo -e "${BOLD}${RED}╚══════════════════════════════════════════════╝${RESET}"
    echo ""

    if [[ $EUID -ne 0 ]]; then
        echo -e "${RED}❌ Please run uninstall as root: sudo bash install.sh --uninstall${RESET}"
        exit 1
    fi

    echo -e "${YELLOW}🛑 Stopping and disabling systemd service...${RESET}"
    if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
        systemctl stop "$SERVICE_NAME" || true
    fi
    if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
        systemctl disable "$SERVICE_NAME" || true
    fi

    echo -e "${YELLOW}🗑️  Removing service file...${RESET}"
    if [ -f "$SERVICE_FILE" ]; then
        rm -f "$SERVICE_FILE"
        systemctl daemon-reload
    fi

    echo -e "${YELLOW}🗑️  Removing installation directory (${INSTALL_DIR})...${RESET}"
    rm -rf "$INSTALL_DIR"

    echo -e "${YELLOW}🗑️  Removing configuration (${CONFIG_DIR})...${RESET}"
    rm -rf "$CONFIG_DIR"

    echo ""
    echo -e "${GREEN}✅ System Monitor daemon successfully uninstalled!${RESET}"
    echo -e "   Log file retained at: ${LOG_FILE} (remove manually if desired)"
    echo ""
    exit 0
}

# ── Argument Parsing ──────────────────────────────────────────────
CLI_WEBHOOK=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            show_help
            ;;
        -u|--uninstall)
            do_uninstall
            ;;
        -w|--webhook)
            if [ -n "$2" ] && [[ "$2" != -* ]]; then
                CLI_WEBHOOK="$2"
                shift 2
            else
                echo -e "${RED}❌ Error: --webhook requires a URL argument.${RESET}"
                exit 1
            fi
            ;;
        --webhook=*)
            CLI_WEBHOOK="${1#*=}"
            shift
            ;;
        http://*|https://*)
            CLI_WEBHOOK="$1"
            shift
            ;;
        *)
            # If positional argument looks like a URL or string
            if [ -z "$CLI_WEBHOOK" ]; then
                CLI_WEBHOOK="$1"
            fi
            shift
            ;;
    esac
done

echo ""
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${CYAN}║      System Monitor Daemon — Installer       ║${RESET}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════════╝${RESET}"
echo ""

# ── 1. Root check ─────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}❌ Error: This script must be run as root.${RESET}"
    echo -e "   Please rerun with sudo:"
    echo -e "   ${BOLD}curl -sSL ${RAW_REPO_BASE}/install.sh | sudo bash -s -- \"<SLACK_WEBHOOK_URL>\"${RESET}"
    exit 1
fi

# ── 2. Determine Webhook URL ──────────────────────────────────────
WEBHOOK_URL="${CLI_WEBHOOK:-$SLACK_WEBHOOK_URL}"

# If not provided via flag/positional or env, prompt interactively
if [ -z "$WEBHOOK_URL" ]; then
    echo -e "${YELLOW}🔔 No Slack Webhook URL provided as an argument.${RESET}"
    echo -e "   Alerts and status reports will be sent to your Slack channel."
    echo -e "   (Need a webhook? Create one at: ${BLUE}https://api.slack.com/apps${RESET})\n"

    INPUT_URL=""
    if [ -t 0 ]; then
        read -r -p "👉 Please enter your Slack Webhook URL: " INPUT_URL
    elif [ -e /dev/tty ]; then
        read -r -p "👉 Please enter your Slack Webhook URL: " INPUT_URL < /dev/tty
    else
        echo -e "${RED}❌ Non-interactive shell detected and no webhook parameter was provided.${RESET}"
        echo -e "   Please provide the webhook URL as a parameter:"
        echo -e "   ${BOLD}curl -sSL ${RAW_REPO_BASE}/install.sh | sudo bash -s -- \"https://hooks.slack.com/...\"${RESET}"
        exit 1
    fi

    WEBHOOK_URL="${INPUT_URL}"
fi

# Sanitize input (strip surrounding whitespace and quotes)
WEBHOOK_URL="$(echo "$WEBHOOK_URL" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")"

# Validate Webhook URL
if [ -z "$WEBHOOK_URL" ]; then
    echo -e "${RED}❌ Error: Slack Webhook URL cannot be empty.${RESET}"
    exit 1
fi

if [[ "$WEBHOOK_URL" == *"YOUR/WEBHOOK/URL"* ]] || [[ "$WEBHOOK_URL" == *"YOUR_WEBHOOK"* ]]; then
    echo -e "${RED}❌ Error: Please provide your actual Slack webhook URL, not the placeholder value.${RESET}"
    exit 1
fi

if [[ "$WEBHOOK_URL" != https://* ]]; then
    echo -e "${RED}❌ Error: Webhook URL must start with https://${RESET}"
    exit 1
fi

echo -e "${GREEN}✓ Slack Webhook configured:${RESET} ${WEBHOOK_URL:0:35}... (validated)"

# ── 3. Install System & Python Dependencies ───────────────────────
echo ""
echo -e "${BOLD}[1/6] 📦 Installing dependencies...${RESET}"

# Install python3 and curl if missing
if ! command -v python3 &>/dev/null || ! command -v curl &>/dev/null; then
    echo "  Installing core system tools..."
    if command -v apt-get &>/dev/null; then
        apt-get update -qq && apt-get install -y -qq python3 python3-pip curl
    elif command -v dnf &>/dev/null; then
        dnf install -y -q python3 python3-pip curl
    elif command -v yum &>/dev/null; then
        yum install -y -q python3 python3-pip curl
    elif command -v pacman &>/dev/null; then
        pacman -Sy --noconfirm python python-pip curl
    fi
fi

# Ensure psutil and requests are installed
NEED_DEPS=0
if ! python3 -c "import psutil, requests" &>/dev/null; then
    NEED_DEPS=1
fi

if [ "$NEED_DEPS" -eq 1 ]; then
    echo "  Installing Python modules (psutil, requests)..."
    # Try distro packages first
    INSTALLED_VIA_PKG=0
    if command -v apt-get &>/dev/null; then
        if apt-get install -y -qq python3-psutil python3-requests 2>/dev/null; then
            INSTALLED_VIA_PKG=1
        fi
    elif command -v dnf &>/dev/null; then
        if dnf install -y -q python3-psutil python3-requests 2>/dev/null; then
            INSTALLED_VIA_PKG=1
        fi
    fi

    # Fallback to pip if package manager didn't install both
    if ! python3 -c "import psutil, requests" &>/dev/null; then
        if pip3 install psutil requests --quiet 2>/dev/null; then
            :
        elif pip3 install psutil requests --break-system-packages --quiet 2>/dev/null; then
            :
        else
            echo -e "${RED}❌ Failed to install psutil or requests via pip.${RESET}"
            echo -e "   Please install python3-psutil and python3-requests manually."
            exit 1
        fi
    fi
fi
echo -e "  ${GREEN}✓ Dependencies verified.${RESET}"

# ── 4. Retrieve & Install Files ───────────────────────────────────
echo ""
echo -e "${BOLD}[2/6] 📂 Setting up files in ${INSTALL_DIR}...${RESET}"
mkdir -p "$INSTALL_DIR"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"

# Locate monitor.py
if [ -f "${SCRIPT_DIR}/monitor.py" ]; then
    cp "${SCRIPT_DIR}/monitor.py" "$INSTALL_DIR/monitor.py"
elif [ -f "./monitor.py" ]; then
    cp "./monitor.py" "$INSTALL_DIR/monitor.py"
else
    echo "  Downloading monitor.py from repository..."
    curl -fsSL "${RAW_REPO_BASE}/monitor.py" -o "$INSTALL_DIR/monitor.py"
fi
chmod 750 "$INSTALL_DIR/monitor.py"

# Locate system-monitor.service
if [ -f "${SCRIPT_DIR}/system-monitor.service" ]; then
    cp "${SCRIPT_DIR}/system-monitor.service" "$SERVICE_FILE"
elif [ -f "./system-monitor.service" ]; then
    cp "./system-monitor.service" "$SERVICE_FILE"
else
    echo "  Downloading system-monitor.service from repository..."
    curl -fsSL "${RAW_REPO_BASE}/system-monitor.service" -o "$SERVICE_FILE"
fi
chmod 644 "$SERVICE_FILE"

# ── 5. Secure Configuration File ──────────────────────────────────
echo ""
echo -e "${BOLD}[3/6] 🔒 Creating secure environment config...${RESET}"
mkdir -p "$CONFIG_DIR"
cat > "$ENV_FILE" <<EOF
# System Monitor Daemon Configuration
# Generated on $(date)

SLACK_WEBHOOK_URL="${WEBHOOK_URL}"
NORMAL_INTERVAL_HOURS=3
ALERT_THRESHOLD_PERCENT=80
DISK_ALERT_THRESHOLD_PERCENT=90
TOP_PROCESS_COUNT=5
POLL_INTERVAL_SECONDS=30
ALERT_COOLDOWN_SECS=300
LOG_FILE="${LOG_FILE}"
EOF

chmod 600 "$ENV_FILE"
echo -e "  ${GREEN}✓ Config saved to ${ENV_FILE} (permissions: 0600 root only).${RESET}"

# ── 6. Log File Initialization ────────────────────────────────────
echo ""
echo -e "${BOLD}[4/6] 📝 Initializing log file...${RESET}"
touch "$LOG_FILE"
chmod 640 "$LOG_FILE"
echo -e "  ${GREEN}✓ Log file ready at ${LOG_FILE}.${RESET}"

# ── 7. Verification Test ──────────────────────────────────────────
echo ""
echo -e "${BOLD}[5/6] 📡 Verifying Slack Webhook with a test alert...${RESET}"
set +e
MONITOR_ENV_FILE="$ENV_FILE" python3 "$INSTALL_DIR/monitor.py" --test
TEST_STATUS=$?
set -e

if [ $TEST_STATUS -eq 0 ]; then
    echo -e "  ${GREEN}✓ Webhook verified! Test alert was delivered to Slack.${RESET}"
else
    echo -e "  ${YELLOW}⚠️  Warning: Test alert could not be verified by Slack.${RESET}"
    echo -e "  The daemon will still be installed, but please verify your webhook in ${ENV_FILE}."
fi

# ── 8. Systemd Service Activation ─────────────────────────────────
echo ""
echo -e "${BOLD}[6/6] ⚙️  Enabling and starting systemd service...${RESET}"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME" --quiet
systemctl restart "$SERVICE_NAME"

echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${GREEN}║     ✅ Installation Successfully Completed!   ║${RESET}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════╝${RESET}"
echo ""

systemctl status "$SERVICE_NAME" --no-pager -l || true

echo ""
echo -e "${CYAN}─────────────────────────────────────────────────────────────────${RESET}"
echo -e "${BOLD}Useful Management Commands:${RESET}"
echo -e "  View live logs      →  ${BOLD}tail -f ${LOG_FILE}${RESET}"
echo -e "  Check service       →  ${BOLD}sudo systemctl status ${SERVICE_NAME}${RESET}"
echo -e "  Restart service     →  ${BOLD}sudo systemctl restart ${SERVICE_NAME}${RESET}"
echo -e "  Stop service        →  ${BOLD}sudo systemctl stop ${SERVICE_NAME}${RESET}"
echo -e "  Edit configuration  →  ${BOLD}sudo nano ${ENV_FILE}${RESET}"
echo -e "  Send test alert     →  ${BOLD}sudo python3 ${INSTALL_DIR}/monitor.py --test${RESET}"
echo -e "  Uninstall           →  ${BOLD}sudo bash ${INSTALL_DIR}/install.sh --uninstall${RESET}"
echo -e "                         or: ${BOLD}curl -sSL ${RAW_REPO_BASE}/install.sh | sudo bash -s -- --uninstall${RESET}"
echo -e "${CYAN}─────────────────────────────────────────────────────────────────${RESET}"
echo ""
