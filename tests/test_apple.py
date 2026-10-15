import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from models import VersionInfo
from workflows import apple


class AppleMonitorTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(directory) / "apple_rules.json"
        self.rules = {"App": {"app_id": "123", "version": "1", "notify": ["feishu", "ticktick"]}}
        self.path.write_text(json.dumps(self.rules))
        self.fetch = self.enterContext(patch(
            "workflows.apple.fetch_app_version", return_value=VersionInfo("App", "2"),
        ))
        self.send = self.enterContext(patch(
            "workflows.versions.send_notification", return_value={"feishu": True, "ticktick": True},
        ))

    def test_delivered_version_is_saved_and_not_notified_again(self):
        self.assertEqual(apple.run_apple_monitor(self.path), [])
        self.assertEqual(apple.load_rules(self.path)["App"]["version"], "2")
        self.assertEqual(apple.run_apple_monitor(self.path), [])
        self.send.assert_called_once()

    def test_partial_delivery_keeps_version_for_next_round(self):
        self.send.return_value = {"feishu": True, "ticktick": False}
        with self.assertLogs("workflows.apple", level="ERROR"):
            self.assertEqual(len(apple.run_apple_monitor(self.path)), 1)
        self.assertEqual(apple.load_rules(self.path)["App"]["version"], "1")
        self.send.return_value = {"feishu": True, "ticktick": True}
        self.assertEqual(apple.run_apple_monitor(self.path), [])
        self.assertEqual(apple.load_rules(self.path)["App"]["version"], "2")
        self.assertEqual(self.send.call_count, 2)

    def test_disabled_app_skips_query_notification_and_version_update(self):
        self.rules["App"]["disabled"] = True
        self.path.write_text(json.dumps(self.rules))
        self.assertEqual(apple.run_apple_monitor(self.path), [])
        self.fetch.assert_not_called()
        self.send.assert_not_called()
        self.assertEqual(apple.load_rules(self.path), self.rules)
