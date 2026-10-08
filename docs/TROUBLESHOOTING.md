# 🩺 Troubleshooting Guide

Common issues, diagnosis steps, and resolutions for **server-monitor-slack-alerts**.

---

## 1. Verifying Webhook Connectivity

If you suspect notifications are not arriving in Slack, test the webhook directly:

```bash
sudo python3 /opt/system_monitor/monitor.py --test
```

### Potential Results & Solutions:

- **`Slack returned HTTP 404: 404 Not Found`**
  - **Cause:** The webhook URL was mistyped, expired, or revoked in Slack.
  - **Resolution:** Generate a new Webhook in Slack Apps → Incoming Webhooks, update `/etc/system_monitor/monitor.env`, and restart `system-monitor`.

- **`Slack returned HTTP 403: action_prohibited`**
  - **Cause:** The webhook was disabled or the integration channel was archived/deleted.
  - **Resolution:** Re-authorize the webhook for an active channel in your Slack workspace.

- **`Connection timed out` or `Network is unreachable`**
  - **Cause:** Server outbound firewall (e.g. `ufw`, `iptables`, AWS Security Group) is blocking HTTPS traffic to `hooks.slack.com:443`.
  - **Resolution:** Test outbound HTTPS connectivity:
    ```bash
    curl -Iv https://hooks.slack.com
    ```

---

## 2. Daemon Status & Log Inspection

### Check systemd service status:
```bash
sudo systemctl status system-monitor -l --no-pager
```

### Inspect daemon log file:
```bash
tail -n 50 /var/log/system_monitor.log
```

### Stream systemd journal logs:
```bash
journalctl -u system-monitor -f
```

---

## 3. Python Dependency Issues

### `ModuleNotFoundError: No module named 'psutil'` or `'requests'`
If Python cannot find the libraries:

1. On Debian/Ubuntu:
   ```bash
   sudo apt-get update && sudo apt-get install -y python3-psutil python3-requests
   ```
2. On RHEL / Alma / Rocky / Fedora:
   ```bash
   sudo dnf install -y python3-psutil python3-requests
   ```
3. Using Pip (with PEP 668 override if required):
   ```bash
   sudo pip3 install psutil requests --break-system-packages
   ```

---

## 4. Resetting or Reinstalling

If the service gets into an inconsistent state:

```bash
# Clean uninstall
curl -sSL https://raw.githubusercontent.com/axosecurity/server-monitor-slack-alerts/master/install.sh | sudo bash -s -- --uninstall

# Reinstall with webhook
curl -sSL https://raw.githubusercontent.com/axosecurity/server-monitor-slack-alerts/master/install.sh | sudo bash -s -- "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
```
