"""通用 HTTP 版本监控、状态提交与故障恢复的业务回归。"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

from clients.update_release import fetch_update_release
from workflows.monitor import run_monitors
from workflows.rules import RuleStore
from workflows.update_release import update_release_monitor


VERSION_URL = "https://example.com/version"
VERSION = "1.2.3"


class UpdateReleaseTests(unittest.TestCase):
    def setUp(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.path = directory / "rules.json"
        self.path.write_text(json.dumps({"Example App": {"url": VERSION_URL, "version": "1.2.2"}}))
        self.spec = update_release_monitor(self.path)
        self.response = MagicMock(status_code=200)
        self.response.__enter__.return_value = self.response
        self.response.text = VERSION + "\n"
        self.get = self.enterContext(patch(
            "clients.http.requests.get", return_value=self.response,
        ))
        self.enterContext(patch("config.TODO_ENABLED", True))
        self.send = self.enterContext(patch(
            "notifications.updates.send_notification", return_value={"ticktick": True},
        ))

    def version(self):
        return RuleStore(self.path).load()["Example App"]["version"]

    def test_success_saves_full_response_and_skips_unchanged_version(self):
        self.assertEqual(run_monitors([self.spec]), [])
        self.assertEqual(self.version(), VERSION)
        self.send.assert_called_once()
        notification, channels = self.send.call_args.args
        self.assertEqual(notification.title, f"Example App - {VERSION}")
        self.assertEqual(notification.content, f"Update Release Monitor\n{VERSION_URL}")
        self.assertEqual(channels, ["ticktick"])

        self.response.text = "  " + VERSION + "\n\n"
        self.assertEqual(run_monitors([self.spec]), [])
        self.send.assert_called_once()

    def test_notification_failure_keeps_version_until_recovery(self):
        self.send.return_value = {"ticktick": False}
        with self.assertLogs("workflows.monitor", level="ERROR"):
            failures = run_monitors([self.spec])
        self.assertEqual(self.version(), "1.2.2")
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["stage"], "notification")
        self.assertEqual(self.send.call_count, 2)

        self.send.return_value = {"ticktick": True}
        self.assertEqual(run_monitors([self.spec]), [])
        self.assertEqual(self.version(), VERSION)

    def test_notification_content_is_separate_from_version_query(self):
        notification_content = "https://example.com/download"
        RuleStore(self.path).update("Example App", {"notification_content": notification_content})
        self.assertEqual(run_monitors([self.spec]), [])
        self.get.assert_called_once()
        self.assertEqual(self.get.call_args.args[0], VERSION_URL)
        self.assertEqual(
            self.send.call_args.args[0].content,
            f"Update Release Monitor\n{notification_content}",
        )
        self.assertEqual(self.version(), VERSION)

    def test_invalid_notification_content_preserves_version_before_request(self):
        for content in (123, [], {}):
            with self.subTest(content=content):
                RuleStore(self.path).update("Example App", {"notification_content": content})
                with self.assertLogs("workflows.monitor", level="ERROR"):
                    failures = run_monitors([self.spec])
                self.assertEqual(len(failures), 1)
                self.assertEqual(self.version(), "1.2.2")
        self.get.assert_not_called()
        self.send.assert_not_called()

    def test_notification_content_accepts_multiline_text(self):
        content = "Example App 有新版本，请查看：\nhttps://example.com/download"
        RuleStore(self.path).update("Example App", {"notification_content": content})
        self.assertEqual(run_monitors([self.spec]), [])
        self.assertEqual(self.send.call_args.args[0].content, f"Update Release Monitor\n{content}")
        self.assertEqual(self.get.call_args.args[0], VERSION_URL)

    def test_multiple_urls_use_their_own_response_text(self):
        other_url = "https://example.com/version.txt"
        RuleStore(self.path).save({
            "Example App": {"url": VERSION_URL},
            "Other App": {"url": other_url},
        })
        other_response = MagicMock(status_code=200)
        other_response.__enter__.return_value = other_response
        other_response.text = "  release-2026.10\n"
        self.get.side_effect = [self.response, other_response]
        self.assertEqual(run_monitors([self.spec]), [])
        self.assertEqual([call.args[0] for call in self.get.call_args_list], [VERSION_URL, other_url])
        rules = RuleStore(self.path).load()
        self.assertEqual(rules["Example App"]["version"], VERSION)
        self.assertEqual(rules["Other App"]["version"], "release-2026.10")
        self.assertEqual(
            [call.args[0].title for call in self.send.call_args_list],
            [f"Example App - {VERSION}", "Other App - release-2026.10"],
        )

    def test_invalid_url_fails_before_request(self):
        for url in (None, "", "file:///tmp/version", "https://"):
            with self.subTest(url=url):
                RuleStore(self.path).update("Example App", {"url": url})
                with self.assertLogs("workflows.monitor", level="ERROR"):
                    failures = run_monitors([self.spec])
                self.assertEqual(len(failures), 1)
                self.assertEqual(self.version(), "1.2.2")
        self.get.assert_not_called()
        self.send.assert_not_called()

    def test_empty_responses_preserve_version_and_skip_notifications(self):
        for text in ("", " \n\t"):
            with self.subTest(text=text):
                self.response.text = text
                with self.assertLogs("workflows.monitor", level="ERROR"):
                    failures = run_monitors([self.spec])
                self.assertEqual(len(failures), 1)
                self.assertEqual(failures[0]["stage"], "check")
                self.assertEqual(self.version(), "1.2.2")
        self.send.assert_not_called()

    def test_query_recovers_with_shared_timeouts_and_retry_policy(self):
        self.get.side_effect = [requests.Timeout("timeout"), self.response]
        with self.assertLogs("clients.http", level="WARNING"):
            info = fetch_update_release(VERSION_URL, name="Example App")
        self.assertEqual(info.version, VERSION)
        self.assertEqual(info.url, VERSION_URL)
        self.assertEqual(self.get.call_count, 2)
        self.assertTrue(all(call.kwargs["timeout"] == (3, 3) for call in self.get.call_args_list))

    def test_persistent_network_failure_has_six_requests_without_auto_disable(self):
        self.get.side_effect = requests.ConnectionError("offline")
        with self.assertLogs(level="WARNING"):
            for _ in range(3):
                failures = run_monitors([self.spec])
                self.assertEqual(len(failures), 1)
                self.assertEqual(failures[0]["source"], "update_release")
        self.assertEqual(self.get.call_count, 18)
        self.assertEqual(self.version(), "1.2.2")
        self.assertNotIn("disabled", RuleStore(self.path).load()["Example App"])
        self.send.assert_not_called()

    def test_disabled_missing_and_notifications_off(self):
        RuleStore(self.path).update("Example App", {"disabled": True})
        self.assertEqual(run_monitors([self.spec]), [])
        self.get.assert_not_called()
        self.path.unlink()
        self.assertEqual(run_monitors([self.spec]), [])
        self.get.assert_not_called()

        self.path.write_text(json.dumps({"Example App": {"url": VERSION_URL}}))
        with patch("config.TODO_ENABLED", False):
            self.assertEqual(run_monitors([self.spec]), [])
        self.assertEqual(self.version(), VERSION)
        self.send.assert_not_called()
