import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workflows import github, github_rules


class GitHubMonitorTests(unittest.TestCase):
    def test_repeated_failure_alerts_twice_then_disables_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "repo_rules.json"
            path.write_text(json.dumps({"owner/repo": {"last_tag": "v1"}}))
            with (
                patch.object(github_rules, "RULES_FILE", path),
                patch("workflows.github.check_latest_release", side_effect=RuntimeError("offline")) as check,
            ):
                alerts = []
                for expected in (1, 0, 1, 0):
                    with self.assertLogs("workflows", level="INFO"):
                        failures = github.run_github_monitor()
                    self.assertEqual(len(failures), expected)
                    alerts.extend(failures)
                self.assertEqual(check.call_count, 3)
                self.assertEqual([record.get("auto_disabled", False) for record in alerts], [False, True])
                self.assertEqual(github_rules.load_rules(), {
                    "owner/repo": {"last_tag": "v1", "disabled": True},
                })
