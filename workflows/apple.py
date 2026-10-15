"""App Store 监控业务线，配置与已通知版本保存在 apple_rules.json。"""

import json
import logging
import os
import tempfile
from pathlib import Path

from clients.app_store import fetch_app_version
from config import BASE_DIR
from notifications import NOTIFIERS
from workflows.versions import process_version

logger = logging.getLogger(__name__)
RULES_FILE = BASE_DIR / "apple_rules.json"


def load_rules(path: Path) -> dict:
    with path.open(encoding="utf-8") as file:
        rules = json.load(file)
    if not isinstance(rules, dict):
        raise ValueError("App Store 监控规则应为 JSON 对象")
    return rules


def save_rules(path: Path, rules: dict) -> None:
    """先完整写入临时文件，再替换规则文件。"""
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as file:
            temporary_path = Path(file.name)
            json.dump(rules, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _validate_rule(rule: dict) -> list[str]:
    version = rule.get("version")
    if version is not None and (
        not isinstance(version, str) or not version.strip()
    ):
        raise ValueError("version 应为非空字符串或 null")
    channels = rule.get("notify")
    if not isinstance(channels, list) or not channels:
        raise ValueError("notify 必填，应为非空渠道数组，例如 [\"feishu\", \"ticktick\"]")
    if any(
        not isinstance(channel, str) or channel not in NOTIFIERS
        for channel in channels
    ):
        raise ValueError(f"notify 中存在未知渠道: {channels!r}")
    return list(dict.fromkeys(channels))


def run_apple_monitor(path: Path | None = None) -> list[dict]:
    """逐项检查版本并投递更新通知，返回本轮失败记录。"""
    path = path if path is not None else RULES_FILE
    rules = load_rules(path)
    failures = []
    for key, rule in rules.items():
        try:
            if not isinstance(rule, dict):
                raise ValueError("监控项应为对象")
            disabled = rule.get("disabled", False)
            if not isinstance(disabled, bool):
                raise ValueError("disabled 应为布尔值 true/false")
            if disabled:
                logger.info("App Store 监控 %s 已禁用，跳过", key)
                continue
            channels = _validate_rule(rule)
            info = fetch_app_version(rule.get("app_id"), rule.get("country", "us"))
            previous_version = rule.get("version")
            version = process_version(
                info, previous_version, channels, content="Update Monitor - App Store"
            )
            if version != previous_version:
                rule["version"] = version
                save_rules(path, rules)
        except Exception as error:
            logger.exception("App Store 监控 %s 失败", key)
            failures.append(
                {
                    "stage": "app_store",
                    "target": key,
                    "error": type(error).__name__,
                    "error_log": f"App Store 监控 {key} 失败: {type(error).__name__}: {error}",
                }
            )
    return failures
