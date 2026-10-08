#!/usr/bin/env python3
"""
System Monitor Daemon — Slack Alerts
Monitors CPU, RAM, Disk, Network, and Top Processes.
Sends:
- Routine health reports every NORMAL_INTERVAL_HOURS hours
- Emergency alerts immediately when CPU, RAM, or Disk exceed alert thresholds
- Test alerts on demand via `--test`
"""

import os
import sys
import time
import json
import socket
import logging
from datetime import datetime

# ──────────────────────────────────────────────────────────────
#  ENVIRONMENT & CONFIG LOADER
# ──────────────────────────────────────────────────────────────

ENV_CONFIG_FILE = os.getenv("MONITOR_ENV_FILE", "/etc/system_monitor/monitor.env")


def load_env_file(filepath: str) -> None:
    """Loads key=value pairs from environment file if not already set in os.environ."""
    if not os.path.isfile(filepath):
        return
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception:
        # Fall back silently if env file cannot be read
        pass


load_env_file(ENV_CONFIG_FILE)

# ──────────────────────────────────────────────────────────────
#  CONFIG — Defaults overridable via env vars or monitor.env
# ──────────────────────────────────────────────────────────────
SLACK_WEBHOOK_URL            = os.getenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/YOUR/WEBHOOK/URL")
NORMAL_INTERVAL_HOURS        = int(os.getenv("NORMAL_INTERVAL_HOURS", "3"))
ALERT_THRESHOLD_PERCENT      = float(os.getenv("ALERT_THRESHOLD_PERCENT", "80"))
DISK_ALERT_THRESHOLD_PERCENT = float(os.getenv("DISK_ALERT_THRESHOLD_PERCENT", "90"))
TOP_PROCESS_COUNT            = int(os.getenv("TOP_PROCESS_COUNT", "5"))
POLL_INTERVAL_SECONDS        = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))
ALERT_COOLDOWN_SECS          = int(os.getenv("ALERT_COOLDOWN_SECS", "300"))
LOG_FILE                     = os.getenv("LOG_FILE", "/var/log/system_monitor.log")

HOSTNAME = socket.gethostname()

# ──────────────────────────────────────────────────────────────
#  LOGGING SETUP
# ──────────────────────────────────────────────────────────────

handlers = [logging.StreamHandler(sys.stdout)]
try:
    log_dir = os.path.dirname(LOG_FILE)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    file_handler = logging.FileHandler(LOG_FILE)
    handlers.append(file_handler)
except Exception:
    # If file logging fails (e.g. non-root CLI user running --test), stdout handles it
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=handlers,
)
log = logging.getLogger("system-monitor")

# Handle immediate info flags before dependency checks
if len(sys.argv) > 1 and sys.argv[1].lower() in ("--help", "-h", "help"):
    print("System Monitor Daemon — Slack Alerts")
    print("Usage:")
    print("  python3 monitor.py          Run as continuous background daemon")
    print("  python3 monitor.py --test   Send an immediate test alert to Slack")
    print("  python3 monitor.py --once   Sample metrics once and send a report")
    print("  python3 monitor.py --help   Show this help message")
    sys.exit(0)

if len(sys.argv) > 1 and sys.argv[1].lower() in ("--version", "-v"):
    print("server-monitor-slack-alerts v1.1.0")
    sys.exit(0)

# Lazy imports with helpful error messages if missing
try:
    import psutil
    import requests
except ImportError as err:
    log.error(f"Missing required dependency: {err}. Please run: pip3 install psutil requests")
    psutil = None
    requests = None


# ──────────────────────────────────────────────────────────────
#  METRIC COLLECTION
# ──────────────────────────────────────────────────────────────

def get_cpu() -> float:
    if not psutil:
        return 0.0
    return float(psutil.cpu_percent(interval=1))


def get_ram() -> dict:
    if not psutil:
        return {"percent": 0.0, "used_gb": 0.0, "total_gb": 0.0}
    mem = psutil.virtual_memory()
    return {
        "percent": float(mem.percent),
        "used_gb": round(mem.used / (1024 ** 3), 2),
        "total_gb": round(mem.total / (1024 ** 3), 2),
    }


def get_disk() -> dict:
    if not psutil:
        return {"percent": 0.0, "used_gb": 0.0, "total_gb": 0.0}
    disk = psutil.disk_usage("/")
    return {
        "percent": float(disk.percent),
        "used_gb": round(disk.used / (1024 ** 3), 2),
        "total_gb": round(disk.total / (1024 ** 3), 2),
    }


def get_network_speed(interval=1) -> dict:
    """Returns network bandwidth in MB/s by sampling over interval seconds."""
    if not psutil:
        return {"sent_mbps": 0.0, "recv_mbps": 0.0}
    try:
        net1 = psutil.net_io_counters()
        time.sleep(interval)
        net2 = psutil.net_io_counters()
        sent_mbps = round((net2.bytes_sent - net1.bytes_sent) / (1024 ** 2) / interval, 3)
        recv_mbps = round((net2.bytes_recv - net1.bytes_recv) / (1024 ** 2) / interval, 3)
        return {"sent_mbps": sent_mbps, "recv_mbps": recv_mbps}
    except Exception:
        return {"sent_mbps": 0.0, "recv_mbps": 0.0}


def get_top_processes(n=TOP_PROCESS_COUNT) -> list:
    """Returns top N processes sorted by CPU + RAM combined weight."""
    if not psutil:
        return []
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            info = p.info
            cpu_val = float(info.get("cpu_percent") or 0.0)
            mem_val = float(info.get("memory_percent") or 0.0)
            name_val = info.get("name") or f"proc-{info.get('pid', 'unknown')}"
            info["score"] = cpu_val + mem_val
            info["cpu_percent"] = cpu_val
            info["memory_percent"] = mem_val
            info["name"] = name_val
            procs.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        except Exception:
            continue
    top = sorted(procs, key=lambda x: x["score"], reverse=True)[:n]
    return top


def collect_all_metrics():
    cpu = get_cpu()
    ram = get_ram()
    disk = get_disk()
    net = get_network_speed(interval=1)
    procs = get_top_processes()
    return cpu, ram, disk, net, procs


# ──────────────────────────────────────────────────────────────
#  SLACK MESSAGE BUILDER
# ──────────────────────────────────────────────────────────────

def build_process_lines(procs: list) -> str:
    if not procs:
        return "  _No process data available_"
    lines = []
    for i, p in enumerate(procs, 1):
        lines.append(
            f"  {i}. `{p.get('name', 'unknown')}` (PID {p.get('pid', '-')}) — "
            f"CPU: {p.get('cpu_percent', 0.0):.1f}%  RAM: {p.get('memory_percent', 0.0):.1f}%"
        )
    return "\n".join(lines)


def build_slack_payload(cpu, ram, disk, net, procs, emergency=False, test=False) -> dict:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    proc_txt = build_process_lines(procs)

    if test:
        header = f":white_check_mark: *System Monitor Verification Test* — `{HOSTNAME}`"
        color = "#4A154B"
        title = ":tada: Installation & Webhook test successful!"
    elif emergency:
        header = f":rotating_light: *EMERGENCY ALERT* — `{HOSTNAME}`"
        color = "#FF0000"
        trigger = []
        if cpu >= ALERT_THRESHOLD_PERCENT:
            trigger.append(f"CPU at *{cpu}%* (threshold: {ALERT_THRESHOLD_PERCENT}%)")
        if ram["percent"] >= ALERT_THRESHOLD_PERCENT:
            trigger.append(f"RAM at *{ram['percent']}%* (threshold: {ALERT_THRESHOLD_PERCENT}%)")
        if disk["percent"] >= DISK_ALERT_THRESHOLD_PERCENT:
            trigger.append(f"Disk at *{disk['percent']}%* (threshold: {DISK_ALERT_THRESHOLD_PERCENT}%)")
        trigger_txt = " & ".join(trigger) if trigger else "Resource threshold exceeded"
        title = f":warning: {trigger_txt}"
    else:
        header = f":bar_chart: *Routine Status Report* — `{HOSTNAME}`"
        color = "#36A64F"
        title = "All systems operating normally"

    text = (
        f"{header}\n"
        f"*{title}*\n"
        f"_Time: {now}_\n\n"
        f"*System Metrics*\n"
        f"> :desktop_computer: CPU Usage:     *{cpu}%*\n"
        f"> :ram: RAM Usage:     *{ram['percent']}%*  "
        f"({ram['used_gb']} GB / {ram['total_gb']} GB)\n"
        f"> :floppy_disk: Disk Usage:    *{disk['percent']}%*  "
        f"({disk['used_gb']} GB / {disk['total_gb']} GB)\n"
        f"> :satellite: Network:        "
        f"↑ {net['sent_mbps']} MB/s  ↓ {net['recv_mbps']} MB/s\n\n"
        f"*Top {TOP_PROCESS_COUNT} Processes (by CPU + RAM)*\n"
        f"{proc_txt}"
    )

    return {
        "attachments": [
            {
                "color": color,
                "text": text,
                "mrkdwn_in": ["text"],
            }
        ]
    }


# ──────────────────────────────────────────────────────────────
#  SLACK SENDER
# ──────────────────────────────────────────────────────────────

def send_slack(payload: dict) -> bool:
    if not requests:
        log.error("requests library is missing. Cannot send Slack alert.")
        return False

    if not SLACK_WEBHOOK_URL or "YOUR/WEBHOOK/URL" in SLACK_WEBHOOK_URL:
        log.error("SLACK_WEBHOOK_URL is not configured or still has placeholder value.")
        return False

    try:
        resp = requests.post(
            SLACK_WEBHOOK_URL,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code != 200:
            log.error(f"Slack returned HTTP {resp.status_code}: {resp.text}")
            return False
        log.info("Slack notification delivered successfully.")
        return True
    except Exception as e:
        log.error(f"Failed to send Slack alert: {e}")
        return False


# ──────────────────────────────────────────────────────────────
#  CLI COMMANDS
# ──────────────────────────────────────────────────────────────

def run_test() -> int:
    """Send an immediate test alert to Slack and exit."""
    print("=" * 60)
    print(f" System Monitor — Webhook Verification Test")
    print(f" Host: {HOSTNAME}")
    print(f" Webhook: {SLACK_WEBHOOK_URL[:32]}... [hidden]")
    print("=" * 60)

    if not requests or not psutil:
        print("❌ Error: Missing required python libraries (psutil, requests).")
        return 1

    if not SLACK_WEBHOOK_URL or "YOUR/WEBHOOK/URL" in SLACK_WEBHOOK_URL:
        print("❌ Error: SLACK_WEBHOOK_URL is not set or still has the placeholder value.")
        print("   Set it in /etc/system_monitor/monitor.env or pass SLACK_WEBHOOK_URL.")
        return 1

    print("[*] Collecting system metrics...")
    cpu, ram, disk, net, procs = collect_all_metrics()
    print(f"    CPU: {cpu}% | RAM: {ram['percent']}% | Disk: {disk['percent']}%")
    print("[*] Dispatching verification message to Slack...")

    payload = build_slack_payload(cpu, ram, disk, net, procs, test=True)
    success = send_slack(payload)
    if success:
        print("✅ SUCCESS! Test alert received by Slack.")
        return 0
    else:
        print("❌ FAILED! Could not deliver message to Slack.")
        print("   Please verify your webhook URL and server network connectivity.")
        return 1


def run_once() -> int:
    """Collects metrics once, prints summary, sends routine report, and exits."""
    print(f"Collecting metrics for host: {HOSTNAME}...")
    cpu, ram, disk, net, procs = collect_all_metrics()
    print(f"CPU: {cpu}%")
    print(f"RAM: {ram['percent']}% ({ram['used_gb']}G / {ram['total_gb']}G)")
    print(f"Disk: {disk['percent']}% ({disk['used_gb']}G / {disk['total_gb']}G)")
    print(f"Net: up {net['sent_mbps']} MB/s, down {net['recv_mbps']} MB/s")
    print(f"Top {len(procs)} processes:")
    for p in procs:
        print(f"  - {p['name']} (PID {p['pid']}): CPU {p['cpu_percent']:.1f}%, RAM {p['memory_percent']:.1f}%")

    payload = build_slack_payload(cpu, ram, disk, net, procs, emergency=False)
    send_slack(payload)
    return 0


# ──────────────────────────────────────────────────────────────
#  MAIN DAEMON LOOP
# ──────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ("--test", "-t", "test"):
            sys.exit(run_test())
        elif arg in ("--once", "-1", "once"):
            sys.exit(run_once())
        elif arg in ("--version", "-v"):
            print("server-monitor-slack-alerts v1.1.0")
            sys.exit(0)
        elif arg in ("--help", "-h", "help"):
            print("System Monitor Daemon — Slack Alerts")
            print("Usage:")
            print("  python3 monitor.py          Run as continuous background daemon")
            print("  python3 monitor.py --test   Send an immediate test alert to Slack")
            print("  python3 monitor.py --once   Sample metrics once and send a report")
            print("  python3 monitor.py --help   Show this help message")
            sys.exit(0)

    log.info("=== System Monitor Daemon started ===")
    log.info(
        f"Host: {HOSTNAME} | Normal interval: {NORMAL_INTERVAL_HOURS}h | "
        f"Alert threshold: {ALERT_THRESHOLD_PERCENT}% (Disk: {DISK_ALERT_THRESHOLD_PERCENT}%) | "
        f"Poll interval: {POLL_INTERVAL_SECONDS}s"
    )

    if not psutil or not requests:
        log.critical("Missing required libraries: psutil and requests. Exiting.")
        sys.exit(1)

    # Warm up CPU measurement
    psutil.cpu_percent(interval=None)

    last_normal_report = 0
    alert_cooldown_until = 0

    while True:
        try:
            cpu, ram, disk, net, procs = collect_all_metrics()
            now_ts = time.time()

            # ── Emergency check ──────────────────────────────
            is_emergency = (
                cpu >= ALERT_THRESHOLD_PERCENT
                or ram["percent"] >= ALERT_THRESHOLD_PERCENT
                or disk["percent"] >= DISK_ALERT_THRESHOLD_PERCENT
            )

            if is_emergency and now_ts >= alert_cooldown_until:
                log.warning(
                    f"EMERGENCY: CPU={cpu}% RAM={ram['percent']}% Disk={disk['percent']}% — sending alert"
                )
                payload = build_slack_payload(cpu, ram, disk, net, procs, emergency=True)
                send_slack(payload)
                alert_cooldown_until = now_ts + ALERT_COOLDOWN_SECS

            # ── Routine report ───────────────────────────────
            normal_interval_secs = NORMAL_INTERVAL_HOURS * 3600
            if now_ts - last_normal_report >= normal_interval_secs:
                log.info(f"Sending routine report — CPU={cpu}% RAM={ram['percent']}% Disk={disk['percent']}%")
                payload = build_slack_payload(cpu, ram, disk, net, procs, emergency=False)
                send_slack(payload)
                last_normal_report = now_ts

        except Exception as e:
            log.error(f"Unexpected error in monitor loop: {e}")

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
