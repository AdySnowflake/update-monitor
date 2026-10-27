"""GitHub 适配：Tag 条件、文件处理与通知、失败策略。"""

from pathlib import Path

from clients.github import fetch_latest_release
from config import BASE_DIR
from models import ReleaseInfo
from notifications.updates import UpdateNotification
from workflows.monitor import FailurePolicy, MonitorSpec, ProcessingError, run_monitor
from workflows.release import run_release
from workflows.versions import UpdateInfo

RULES_FILE = BASE_DIR / "repo_rules.json"


def _validate_rule(key: str, rule: dict) -> None:
    parts = key.split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError("仓库名称应为 owner/repo")
    tag_contains = rule.get("tag_contains")
    if tag_contains is not None and not isinstance(tag_contains, str):
        raise ValueError("tag_contains 字段应为字符串或 null")


def _process_release(info: UpdateInfo, rule: dict) -> None:
    if not isinstance(info, ReleaseInfo):
        raise TypeError("GitHub 文件处理需要 ReleaseInfo")
    result = run_release(info.owner, info.repo, info.tag, info.assets, rule.get("filters"))
    if result.get("success") != 1:
        raise ProcessingError(
            result.get("error", "processing_failed"),
            result.get("error_log") or "Release 文件处理失败",
        )


def github_monitor(path: Path | None = None) -> MonitorSpec:
    return MonitorSpec(
        source="github",
        name="GitHub Release",
        rules_file=path if path is not None else RULES_FILE,
        version_field="last_tag",
        fetch=lambda key, rule: fetch_latest_release(*key.split("/")),
        notification=UpdateNotification(content="GitHub release monitor"),
        validate=_validate_rule,
        accepts=lambda info, rule: not rule.get("tag_contains") or rule["tag_contains"] in info.version,
        process=_process_release,
        failures=FailurePolicy(disable_after=3),
    )


def run_github_monitor(*, targets: set[str] | None = None) -> list[dict]:
    return run_monitor(github_monitor(), targets=targets)
