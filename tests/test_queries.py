"""查询层恢复能力，以及与业务层补跑叠加后的请求上限。"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

from clients.app_store import fetch_app_version
from clients.github import fetch_latest_release
from workflows.apple import apple_monitor
from workflows.github import github_monitor
from workflows.monitor import run_monitors
from workflows.rules import RuleStore


class QueryRetryTests(unittest.TestCase):
    def test_both_queries_recover_on_third_attempt_with_three_second_timeouts(self):
        for fetch, payload in (
            (lambda: fetch_latest_release("owner", "repo"), {"tag_name": "2", "assets": []}),
            (lambda: fetch_app_version("123", name="App"), {"results": [{
                "trackId": 123, "version": "2", "currentVersionReleaseDate": "2026-10-28T00:00:00Z",
            }]}),
        ):
            with self.subTest(payload=payload):
                response = MagicMock(status_code=200)
                response.__enter__.return_value = response
                response.json.return_value = payload
                unavailable = MagicMock(status_code=503)
                unavailable.raise_for_status.side_effect = requests.HTTPError("503")
                with (
                    patch("clients.http.requests.get", side_effect=[
                        requests.Timeout("timeout"), unavailable, response,
                    ]) as get,
                    self.assertLogs("clients.http", level="WARNING"),
                ):
                    self.assertEqual(fetch().version, "2")
                self.assertEqual(get.call_count, 3)
                self.assertTrue(all(call.kwargs["timeout"] == (3, 3) for call in get.call_args_list))

        # 没有 Release 是正常跳过，不应消耗三次请求。
        response = MagicMock(status_code=404)
        response.__enter__.return_value = response
        with patch("clients.http.requests.get", return_value=response) as get:
            with self.assertLogs("clients.github", level="WARNING"):
                self.assertIsNone(fetch_latest_release("owner", "repo"))
        get.assert_called_once()

    def test_persistent_failure_is_capped_at_six_requests_per_source_per_round(self):
        with tempfile.TemporaryDirectory() as directory:
            github_path = Path(directory) / "repo_rules.json"
            apple_path = Path(directory) / "apple_rules.json"
            github_path.write_text(json.dumps({"owner/repo": {"last_tag": "1"}}))
            apple_path.write_text(json.dumps({"App": {"app_id": "123", "version": "1"}}))
            with (
                patch("clients.http.requests.get", side_effect=requests.ConnectionError("offline")) as get,
                self.assertLogs(level="WARNING"),
            ):
                failures = run_monitors([github_monitor(github_path), apple_monitor(apple_path)])
            self.assertEqual(len(failures), 2)
            urls = [call.args[0] for call in get.call_args_list]
            self.assertEqual(sum("api.github.com" in url for url in urls), 6)
            self.assertEqual(sum("itunes.apple.com" in url for url in urls), 6)
            github_rule = RuleStore(github_path).load()["owner/repo"]
            self.assertEqual(github_rule["last_tag"], "1")
            self.assertEqual(github_rule["consecutive_failures"], 1)
            self.assertEqual(RuleStore(apple_path).load()["App"]["version"], "1")

    def test_invalid_apple_release_dates_preserve_state_and_report_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "apple_rules.json"
            original = {"App": {
                "app_id": "123", "version": "1", "release_date": "2026-10-27T00:00:00Z",
            }}
            for date in (None, "invalid", "2026-10-28T00:00:00"):
                with self.subTest(date=date):
                    path.write_text(json.dumps(original))
                    response = MagicMock(status_code=200)
                    response.__enter__.return_value = response
                    response.json.return_value = {"results": [{
                        "trackId": 123, "version": "2", "currentVersionReleaseDate": date,
                    }]}
                    with (
                        patch("clients.http.requests.get", return_value=response) as get,
                        patch("workflows.monitor.notify_update") as notify,
                        self.assertLogs("workflows.monitor", level="ERROR"),
                    ):
                        failures = run_monitors([apple_monitor(path)])
                    self.assertEqual(len(failures), 1)
                    self.assertEqual(failures[0]["stage"], "check")
                    self.assertEqual(get.call_count, 2)  # 内容校验失败仅走业务补跑。
                    self.assertEqual(RuleStore(path).load(), original)
                    notify.assert_not_called()
