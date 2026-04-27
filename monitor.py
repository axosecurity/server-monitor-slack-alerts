#!/usr/bin/env python3
"""
System Monitor Daemon
Sends Slack webhook alerts with system stats.
Normal report: every NORMAL_INTERVAL_HOURS hours
Emergency alert: when CPU or RAM exceeds ALERT_THRESHOLD_PERCENT
"""

import time
import json
import socket
import logging
import requests
import psutil
from datetime import datetime

# ─────────────────────────────────────────────
#  CONFIG — edit these values as needed
# ─────────────────────────────────────────────
SLACK_WEBHOOK_URL       = "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
NORMAL_INTERVAL_HOURS   = 3          # How often to send a normal status report
ALERT_THRESHOLD_PERCENT = 80         # CPU or RAM % that triggers an emergency alert
TOP_PROCESS_COUNT       = 5          # How many top processes to include
POLL_INTERVAL_SECONDS   = 30         # How often to check metrics (keep low to catch spikes)
LOG_FILE                = "/var/log/system_monitor.log"
# ─────────────────────────────────────────────

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

HOSTNAME = socket.gethostname()


# ──────────────────────────────────────────────────────────────
#  METRIC COLLECTION
# ──────────────────────────────────────────────────────────────

def get_cpu():
    return psutil.cpu_percent(interval=1)


def get_ram():
    mem = psutil.virtual_memory()
    return {
        "percent": mem.percent,
        "used_gb": round(mem.used / (1024 ** 3), 2),
        "total_gb": round(mem.total / (1024 ** 3), 2),
    }


def get_disk():
    disk = psutil.disk_usage("/")
    return {
        "percent": disk.percent,
        "used_gb": round(disk.used / (1024 ** 3), 2),
        "total_gb": round(disk.total / (1024 ** 3), 2),
    }


def get_network_speed(interval=1):
    """Returns network bandwidth in MB/s by sampling over `interval` seconds."""
    net1 = psutil.net_io_counters()
    time.sleep(interval)
    net2 = psutil.net_io_counters()
    sent_mbps = round((net2.bytes_sent - net1.bytes_sent) / (1024 ** 2) / interval, 3)
    recv_mbps = round((net2.bytes_recv - net1.bytes_recv) / (1024 ** 2) / interval, 3)
    return {"sent_mbps": sent_mbps, "recv_mbps": recv_mbps}


def get_top_processes(n=TOP_PROCESS_COUNT):
    """Returns top N processes sorted by CPU + memory combined weight."""
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            info = p.info
            info["score"] = (info["cpu_percent"] or 0) + (info["memory_percent"] or 0)
            procs.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    top = sorted(procs, key=lambda x: x["score"], reverse=True)[:n]
    return top


def collect_all_metrics():
    cpu     = get_cpu()
    ram     = get_ram()
    disk    = get_disk()
    net     = get_network_speed(interval=1)
    procs   = get_top_processes()
    return cpu, ram, disk, net, procs


# ──────────────────────────────────────────────────────────────
#  SLACK MESSAGE BUILDER
# ──────────────────────────────────────────────────────────────

def build_process_lines(procs):
    lines = []
    for i, p in enumerate(procs, 1):
        lines.append(
            f"  {i}. `{p['name']}` (PID {p['pid']}) — "
            f"CPU: {p['cpu_percent']:.1f}%  RAM: {p['memory_percent']:.1f}%"
        )
    return "\n".join(lines)


def build_slack_payload(cpu, ram, disk, net, procs, emergency=False):
    now      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    proc_txt = build_process_lines(procs)

    if emergency:
        header  = f":rotating_light: *EMERGENCY ALERT* — `{HOSTNAME}`"
        color   = "#FF0000"
        trigger = []
        if cpu >= ALERT_THRESHOLD_PERCENT:
            trigger.append(f"CPU at *{cpu}%*")
        if ram["percent"] >= ALERT_THRESHOLD_PERCENT:
            trigger.append(f"RAM at *{ram['percent']}%*")
        trigger_txt = " & ".join(trigger) + f" (threshold: {ALERT_THRESHOLD_PERCENT}%)"
        title   = f":warning: {trigger_txt}"
    else:
        header  = f":bar_chart: *Routine Status Report* — `{HOSTNAME}`"
        color   = "#36A64F"
        title   = "All systems operating normally"

    text = (
        f"{header}\n"
        f"*{title}*\n"
        f"_Time: {now}_\n\n"
        f"*System Metrics*\n"
        f"> :cpu: CPU Usage:     *{cpu}%*\n"
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

def send_slack(payload):
    try:
        resp = requests.post(
            SLACK_WEBHOOK_URL,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code != 200:
            log.error(f"Slack returned HTTP {resp.status_code}: {resp.text}")
        else:
            log.info("Slack message sent successfully.")
    except Exception as e:
        log.error(f"Failed to send Slack message: {e}")


# ──────────────────────────────────────────────────────────────
#  MAIN DAEMON LOOP
# ──────────────────────────────────────────────────────────────

def main():
    log.info("=== System Monitor Daemon started ===")
    log.info(f"Host: {HOSTNAME} | Normal interval: {NORMAL_INTERVAL_HOURS}h | "
             f"Alert threshold: {ALERT_THRESHOLD_PERCENT}% | "
             f"Poll interval: {POLL_INTERVAL_SECONDS}s")

    # Warm up CPU percent measurement (first call always returns 0.0)
    psutil.cpu_percent(interval=None)

    last_normal_report  = 0          # Unix timestamp of last routine report
    alert_cooldown_until = 0         # Prevent alert spam: block repeat alerts for 5 min
    ALERT_COOLDOWN_SECS  = 300       # 5 minutes between repeated emergency alerts

    while True:
        try:
            cpu, ram, disk, net, procs = collect_all_metrics()
            now_ts = time.time()

            # ── Emergency check ──────────────────────────────
            is_emergency = (
                cpu >= ALERT_THRESHOLD_PERCENT
                or ram["percent"] >= ALERT_THRESHOLD_PERCENT
            )

            if is_emergency and now_ts >= alert_cooldown_until:
                log.warning(
                    f"EMERGENCY: CPU={cpu}% RAM={ram['percent']}% — sending alert"
                )
                payload = build_slack_payload(cpu, ram, disk, net, procs, emergency=True)
                send_slack(payload)
                alert_cooldown_until = now_ts + ALERT_COOLDOWN_SECS

            # ── Routine report ───────────────────────────────
            normal_interval_secs = NORMAL_INTERVAL_HOURS * 3600
            if now_ts - last_normal_report >= normal_interval_secs:
                log.info(f"Sending routine report — CPU={cpu}% RAM={ram['percent']}%")
                payload = build_slack_payload(cpu, ram, disk, net, procs, emergency=False)
                send_slack(payload)
                last_normal_report = now_ts

        except Exception as e:
            log.error(f"Unexpected error in monitor loop: {e}")

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
