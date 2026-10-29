"""仅保留影响下载、通知、版本推进与故障恢复的业务回归。"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from models import ReleaseInfo, VersionInfo, parse_release_date
from notifications.alerts import send_error_notification
from workflows.apple import apple_monitor
from workflows.github import github_monitor
from workflows.monitor import run_monitors
from workflows.rules import RuleStore


class MonitorTests(unittest.TestCase):
    def setUp(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.github_path = directory / "repo_rules.json"
        self.apple_path = directory / "apple_rules.json"
        self.github_path.write_text(json.dumps({
            "owner/repo": {"filters": [{}], "last_tag": "1"},
        }))
        self.apple_path.write_text(json.dumps({
            "App": {"app_id": "123", "version": "1", "release_date": "2026-10-27T00:00:00Z"},
        }))
        self.specs = [github_monitor(self.github_path), apple_monitor(self.apple_path)]
        self.github = self.enterContext(patch(
            "workflows.github.fetch_latest_release",
            return_value=ReleaseInfo("owner", "repo", "2", []),
        ))
        self.apple = self.enterContext(patch(
            "workflows.apple.fetch_app_version", return_value=VersionInfo(
                "App", "2", release_date=parse_release_date("2026-10-28T00:00:00Z"),
            ),
        ))
        self.process = self.enterContext(patch(
            "workflows.github.run_release", return_value={"success": 1},
        ))
        self.enterContext(patch("config.TODO_ENABLED", True))
        self.send = self.enterContext(patch(
            "notifications.updates.send_notification", return_value={"ticktick": True},
        ))

    def assert_versions(self, expected):
        self.assertEqual(RuleStore(self.github_path).load()["owner/repo"]["last_tag"], expected)
        self.assertEqual(RuleStore(self.apple_path).load()["App"]["version"], expected)

    def test_success_saves_versions_and_does_not_repeat_notifications(self):
        self.assertEqual(run_monitors(self.specs), [])
        self.assert_versions("2")
        self.assertEqual(run_monitors(self.specs), [])
        self.process.assert_called_once()
        self.assertEqual(self.send.call_count, 2)
        self.assertEqual(
            [call.args[0].title for call in self.send.call_args_list],
            ["repo - 2", "App - 2"],
        )
        for call in self.send.call_args_list:
            self.assertEqual(call.args[1], ["ticktick"])

    def test_notification_failure_keeps_both_versions_and_recovers_next_round(self):
        self.send.return_value = {"ticktick": False}
        with self.assertLogs("workflows.monitor", level="ERROR"):
            failures = run_monitors(self.specs)
        self.assert_versions("1")
        self.assertEqual(RuleStore(self.apple_path).load()["App"]["release_date"], "2026-10-27T00:00:00Z")
        self.assertEqual({record["source"] for record in failures}, {"github", "app_store"})
        self.assertTrue(all(record["stage"] == "notification" for record in failures))
        self.assertEqual(self.send.call_count, 4)  # 两个来源各首遍加一次补跑
        with patch("notifications.alerts.send_notification") as alert:
            send_error_notification(failures)
        alert.assert_called_once()
        self.assertEqual(alert.call_args.args[1], ["feishu"])
        self.assertEqual(alert.call_args.args[0].level, "error")

        self.send.return_value = {"ticktick": True}
        self.assertEqual(run_monitors(self.specs), [])
        self.assert_versions("2")
        self.assertEqual(RuleStore(self.apple_path).load()["App"]["release_date"], "2026-10-28T00:00:00+00:00")
        self.assertNotIn("consecutive_failures", RuleStore(self.github_path).load()["owner/repo"])

    def test_network_failure_retries_only_failed_items_after_both_sources_run(self):
        RuleStore(self.github_path).update("owner/repo", {"last_tag": "2"})
        rules = RuleStore(self.github_path).load()
        rules["owner/stable"] = {"last_tag": "2"}
        RuleStore(self.github_path).save(rules)
        rules = RuleStore(self.apple_path).load()
        rules["StableApp"] = {"app_id": "456", "version": "2"}
        RuleStore(self.apple_path).save(rules)
        events = []
        attempts = {"repo": 0, "App": 0}

        def fetch_github(owner, repo):
            events.append(repo)
            if repo == "repo":
                attempts[repo] += 1
                if attempts[repo] == 1:
                    raise requests.ConnectionError("offline")
            return ReleaseInfo(owner, repo, "2", [])

        def fetch_apple(app_id, country, *, name):
            events.append(name)
            if name == "App":
                attempts[name] += 1
                if attempts[name] == 1:
                    raise requests.Timeout("timeout")
            return VersionInfo(name, "2", release_date=parse_release_date("2026-10-28T00:00:00Z"))

        self.github.side_effect = fetch_github
        self.apple.side_effect = fetch_apple
        with self.assertLogs("workflows.monitor", level="ERROR"):
            self.assertEqual(run_monitors(self.specs), [])
        self.assertEqual(events, ["repo", "stable", "App", "StableApp", "repo", "App"])
        self.assert_versions("2")
        self.assertNotIn("consecutive_failures", RuleStore(self.github_path).load()["owner/repo"])

    def test_persistent_network_failure_disables_github_after_three_rounds(self):
        self.github.side_effect = requests.ConnectionError("offline")
        self.apple.side_effect = requests.ConnectionError("offline")
        github_alerts = []
        with self.assertLogs("workflows.monitor", level="ERROR"):
            for _ in range(4):
                failures = run_monitors(self.specs)
                github_alerts.extend(record for record in failures if record["source"] == "github")
                self.assertEqual(sum(record["source"] == "app_store" for record in failures), 1)
        self.assertEqual(self.github.call_count, 6)  # 三轮，每轮两次；第四轮已禁用
        self.assertEqual(self.apple.call_count, 8)  # App Store 不自动禁用
        self.assertEqual([record.get("auto_disabled", False) for record in github_alerts], [False, True])
        self.assertTrue(RuleStore(self.github_path).load()["owner/repo"]["disabled"])
        self.assert_versions("1")
        self.process.assert_not_called()
        self.send.assert_not_called()

    def test_filtered_release_does_not_download_notify_or_advance_tag(self):
        RuleStore(self.github_path).update("owner/repo", {"tag_contains": "phone"})
        self.github.return_value = ReleaseInfo("owner", "repo", "2-tv", [])
        self.assertEqual(run_monitors(self.specs[:1]), [])
        self.assertEqual(RuleStore(self.github_path).load()["owner/repo"]["last_tag"], "1")
        self.process.assert_not_called()
        self.send.assert_not_called()

    def test_apple_version_oscillation_only_notifies_newer_releases(self):
        store = RuleStore(self.apple_path)
        store.update("App", {"version": None, "release_date": None})
        for version, date in (
            ("3.5.11", "2026-10-28T00:10:02Z"),
            ("3.5.12", "2026-10-28T18:48:05Z"),
            ("3.5.11", "2026-10-28T00:10:02Z"),
            ("3.5.12", "2026-10-28T18:48:05Z"),
            ("3.5.13", "2026-10-29T12:00:00+08:00"),
            ("3.5.12", "2026-10-28T18:48:05Z"),
            ("another-version", "2026-10-29T04:00:00Z"),
            ("3.5.13", "2026-10-30T00:00:00Z"),
        ):
            self.apple.return_value = VersionInfo("App", version, release_date=parse_release_date(date))
            self.assertEqual(run_monitors(self.specs[1:]), [])
        self.assertEqual([call.args[0].title for call in self.send.call_args_list], [
            "App - 3.5.11", "App - 3.5.12", "App - 3.5.13",
        ])
        self.assertEqual(store.load()["App"], {
            "app_id": "123", "version": "3.5.13", "release_date": "2026-10-29T04:00:00+00:00",
        })
