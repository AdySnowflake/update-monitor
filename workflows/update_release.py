"""Update Release Monitor：通用版本文本查询与更新通知。"""

from pathlib import Path

from clients.update_release import fetch_update_release
from config import BASE_DIR
from notifications.updates import UpdateNotification
from workflows.monitor import MonitorSpec, run_monitor
from workflows.versions import UpdateInfo

RULES_FILE = BASE_DIR / "rules.json"


def _validate_rule(key: str, rule: dict) -> None:
    content = rule.get("notification_content")
    if content is not None and not isinstance(content, str):
        raise ValueError("notification_content 应为字符串或 null")


def _notification(info: UpdateInfo, rule: dict) -> UpdateNotification:
    content = rule.get("notification_content")
    return UpdateNotification(
        content=f"Update Release Monitor\n{content if content is not None else info.url}",
        include_url=False,
    )


def update_release_monitor(path: Path | None = None) -> MonitorSpec:
    return MonitorSpec(
        source="update_release",
        name="Update Release Monitor",
        rules_file=path if path is not None else RULES_FILE,
        version_field="version",
        fetch=lambda key, rule: fetch_update_release(rule.get("url"), name=key),
        notification=_notification,
        validate=_validate_rule,
        accepts=lambda info, rule: True,
        process=lambda info, rule: None,
    )


def run_update_release_monitor(path: Path | None = None, *, targets: set[str] | None = None) -> list[dict]:
    return run_monitor(update_release_monitor(path), targets=targets)
