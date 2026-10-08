#!/usr/bin/env python3
"""
Unit tests for monitor.py
"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import monitor


class TestMonitor(unittest.TestCase):
    def test_load_env_file(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write("TEST_ENV_VAR=foo\n# comment\nANOTHER_VAR=\"bar baz\"\n")
            temp_path = f.name

        try:
            monitor.load_env_file(temp_path)
            self.assertEqual(os.environ.get("TEST_ENV_VAR"), "foo")
            self.assertEqual(os.environ.get("ANOTHER_VAR"), "bar baz")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_build_process_lines(self):
        procs = [
            {"name": "nginx", "pid": 101, "cpu_percent": 12.4, "memory_percent": 3.1},
            {"name": "postgres", "pid": 102, "cpu_percent": 8.0, "memory_percent": 15.2},
        ]
        text = monitor.build_process_lines(procs)
        self.assertIn("nginx", text)
        self.assertIn("PID 101", text)
        self.assertIn("postgres", text)

    def test_build_slack_payload_routine(self):
        ram = {"percent": 40.0, "used_gb": 3.2, "total_gb": 8.0}
        disk = {"percent": 55.0, "used_gb": 55.0, "total_gb": 100.0}
        net = {"sent_mbps": 0.5, "recv_mbps": 1.2}
        procs = [{"name": "python", "pid": 500, "cpu_percent": 5.0, "memory_percent": 2.0}]

        payload = monitor.build_slack_payload(15.0, ram, disk, net, procs, emergency=False)
        self.assertIn("attachments", payload)
        self.assertEqual(payload["attachments"][0]["color"], "#36A64F")
        self.assertIn("Routine Status Report", payload["attachments"][0]["text"])

    def test_build_slack_payload_emergency(self):
        ram = {"percent": 92.0, "used_gb": 7.5, "total_gb": 8.0}
        disk = {"percent": 96.0, "used_gb": 96.0, "total_gb": 100.0}
        net = {"sent_mbps": 2.5, "recv_mbps": 5.2}
        procs = [{"name": "stress", "pid": 600, "cpu_percent": 95.0, "memory_percent": 10.0}]

        payload = monitor.build_slack_payload(95.0, ram, disk, net, procs, emergency=True)
        self.assertEqual(payload["attachments"][0]["color"], "#FF0000")
        self.assertIn("EMERGENCY ALERT", payload["attachments"][0]["text"])
        self.assertIn("CPU at *95.0%*", payload["attachments"][0]["text"])
        self.assertIn("RAM at *92.0%*", payload["attachments"][0]["text"])
        self.assertIn("Disk at *96.0%*", payload["attachments"][0]["text"])

    def test_build_slack_payload_test(self):
        ram = {"percent": 40.0, "used_gb": 3.2, "total_gb": 8.0}
        disk = {"percent": 50.0, "used_gb": 50.0, "total_gb": 100.0}
        net = {"sent_mbps": 0.1, "recv_mbps": 0.2}
        procs = []

        payload = monitor.build_slack_payload(10.0, ram, disk, net, procs, test=True)
        self.assertEqual(payload["attachments"][0]["color"], "#4A154B")
        self.assertIn("Verification Test", payload["attachments"][0]["text"])


if __name__ == "__main__":
    unittest.main()
