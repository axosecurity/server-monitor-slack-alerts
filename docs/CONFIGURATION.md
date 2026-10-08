# ⚙️ Configuration Guide

This document describes all configuration options available for **server-monitor-slack-alerts**, where they are located, and how to tune them for your environment.

---

## 📍 Configuration Location

When installed via `install.sh`, all runtime settings are stored in:

```bash
/etc/system_monitor/monitor.env
```

This file is created with file permissions `0600` (read/write by root only), ensuring that your Slack Webhook URL and server secrets are never exposed to non-privileged users or world-readable files.

`systemd` automatically injects these key-value pairs into the daemon environment via:
```ini
EnvironmentFile=-/etc/system_monitor/monitor.env
```

---

## 🛠️ Configuration Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `SLACK_WEBHOOK_URL` | String | *Required* | The full incoming Slack webhook URL. |
| `NORMAL_INTERVAL_HOURS` | Integer | `3` | Hours between routine status report messages. Set to `1` for hourly reports, or `6` / `12` for lower frequency. |
| `ALERT_THRESHOLD_PERCENT` | Float / Int | `80` | Percentage threshold for CPU and RAM that triggers an immediate Emergency Alert. |
| `DISK_ALERT_THRESHOLD_PERCENT` | Float / Int | `90` | Percentage threshold for primary disk (`/`) usage that triggers an Emergency Alert. |
| `TOP_PROCESS_COUNT` | Integer | `5` | The number of top resource-consuming processes listed in report messages. |
| `POLL_INTERVAL_SECONDS` | Integer | `30` | Interval in seconds between background metrics sampling. Lower values detect spikes faster. |
| `ALERT_COOLDOWN_SECS` | Integer | `300` | Minimum seconds between repeated emergency alerts (5 minutes by default) to prevent alert flooding during prolonged high load. |
| `LOG_FILE` | String | `/var/log/system_monitor.log` | Path where execution and alert logs are written. |

---

## 🔄 Applying Configuration Changes

Whenever you modify `/etc/system_monitor/monitor.env`, restart the daemon to apply the new settings:

```bash
sudo systemctl restart system-monitor
```

To verify the daemon reloaded the configuration cleanly:

```bash
sudo systemctl status system-monitor
```

---

## 🚀 Running Without systemd (Standalone Mode)

If you are running the script manually (e.g. inside a Docker container, Kubernetes pod, or for testing), you can pass environment variables directly:

```bash
SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL" \
NORMAL_INTERVAL_HOURS=1 \
ALERT_THRESHOLD_PERCENT=75 \
python3 monitor.py
```

`monitor.py` automatically checks:
1. Environment variables (`os.environ`)
2. `/etc/system_monitor/monitor.env` (if present)
3. Internal default fallback values
