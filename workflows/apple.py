"""App Store 适配：查询参数与更新通知策略。"""

from pathlib import Path

from clients.app_store import fetch_app_version
from config import BASE_DIR
from notifications.updates import UpdateNotification
from workflows.monitor import MonitorSpec, run_monitor

RULES_FILE = BASE_DIR / "apple_rules.json"


def apple_monitor(path: Path | None = None) -> MonitorSpec:
    return MonitorSpec(
        source="app_store",
        name="App Store",
        rules_file=path if path is not None else RULES_FILE,
        version_field="version",
        release_date_field="release_date",
        fetch=lambda key, rule: fetch_app_version(
            rule.get("app_id"), rule.get("country", "us"), name=key
        ),
        notification=UpdateNotification(content="Update Monitor - App Store"),
        validate=lambda key, rule: None,
        accepts=lambda info, rule: True,
        process=lambda info, rule: None,
    )


def run_apple_monitor(path: Path | None = None, *, targets: set[str] | None = None) -> list[dict]:
    return run_monitor(apple_monitor(path), targets=targets)
