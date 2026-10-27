"""公共监控流程：检测、动作、通知、状态提交、失败补跑和告警策略。"""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from notifications.updates import UpdateNotification, notify_update
from workflows.rules import RuleStore
from workflows.versions import DetectionStatus, UpdateInfo, detect_version

logger = logging.getLogger(__name__)
FAILURE_FIELDS = ("consecutive_failures", "next_check_after")
STAGE_LABELS = {
    "rules": "规则读取",
    "validation": "规则校验",
    "check": "版本查询与检测",
    "processing": "业务处理",
    "notification": "更新通知",
    "state": "状态保存",
}


@dataclass(frozen=True)
class FailurePolicy:
    # None 表示持续监控、每轮告警；设置阈值后只在首次失败和禁用时告警。
    disable_after: int | None = None


@dataclass(frozen=True)
class MonitorSpec:
    source: str
    name: str
    rules_file: Path
    version_field: str
    fetch: Callable[[str, dict], UpdateInfo | None]
    notification: UpdateNotification
    validate: Callable[[str, dict], None]
    accepts: Callable[[UpdateInfo, dict], bool]
    process: Callable[[UpdateInfo, dict], None]
    failures: FailurePolicy = FailurePolicy()


class ProcessingError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _failure(
    spec: MonitorSpec,
    stage: str,
    error: Exception,
    key: str | None = None,
    info: UpdateInfo | None = None,
) -> dict:
    record = {
        "source": spec.source,
        "source_name": spec.name,
        "stage": stage,
        "error": error.code if isinstance(error, ProcessingError) else type(error).__name__,
        "error_log": f"{spec.name} {key or '业务线'} {STAGE_LABELS[stage]}失败: {type(error).__name__}: {error}",
    }
    if key is not None:
        record["target"] = key
    if info is not None:
        record["version"] = info.version
    return record


def run_monitor(spec: MonitorSpec, *, targets: set[str] | None = None) -> list[dict]:
    """执行一遍；动作成功且已启用的通知送达后才提交版本。"""
    store = RuleStore(spec.rules_file)
    try:
        rules = store.load()
    except Exception as error:
        logger.exception("%s 规则读取失败", spec.name)
        return [_failure(spec, "rules", error)]

    failures = []
    for key, rule in rules.items():
        if targets is not None and key not in targets:
            continue
        stage = "validation"
        info = None
        try:
            if not isinstance(rule, dict):
                raise ValueError("监控项应为对象")
            disabled = rule.get("disabled", False)
            if not isinstance(disabled, bool):
                raise ValueError("disabled 应为布尔值 true/false")
            if disabled:
                logger.info("%s %s 已禁用，跳过", spec.name, key)
                continue
            previous = rule.get(spec.version_field)
            if previous is not None and (not isinstance(previous, str) or not previous.strip()):
                raise ValueError(f"{spec.version_field} 应为非空字符串或 null")
            spec.validate(key, rule)

            stage = "check"
            info = spec.fetch(key, rule)
            status = detect_version(
                info, previous, accepted=info is not None and spec.accepts(info, rule)
            )
            logger.info(
                "%s %s 检测结果: %s（%s → %s）",
                spec.name, key, status.value, previous, info.version if info else None,
            )
            if status != DetectionStatus.CHANGED:
                stage = "state"
                store.update(key, remove=FAILURE_FIELDS)
                continue

            assert info is not None
            stage = "processing"
            spec.process(info, rule)
            stage = "notification"
            notify_update(info, spec.notification)
            stage = "state"
            store.update(key, {spec.version_field: info.version}, remove=FAILURE_FIELDS)
        except Exception as error:
            logger.exception("%s %s %s失败", spec.name, key, STAGE_LABELS[stage])
            failures.append(_failure(spec, stage, error, key, info))
    return failures


def finalize_failures(records: list[dict], specs: Sequence[MonitorSpec]) -> list[dict]:
    """补跑结束后每项累计一次失败，按业务策略决定告警与禁用。"""
    by_source = {spec.source: spec for spec in specs}
    alerts = []
    for record in records:
        spec = by_source[record["source"]]
        key = record.get("target")
        threshold = spec.failures.disable_after
        if key is None or threshold is None:
            alerts.append(record)
            continue
        try:
            store = RuleStore(spec.rules_file)
            rule = store.load()[key]
            count = int(rule.get("consecutive_failures") or 0) + 1
            if count >= threshold:
                store.update(key, {"disabled": True}, remove=FAILURE_FIELDS)
                record = {
                    **record, "auto_disabled": True,
                    "failure_count": count, "rules_file": spec.rules_file.name,
                }
            else:
                store.update(key, {"consecutive_failures": count}, remove=("next_check_after",))
            logger.warning("%s %s 连续失败 %s 轮", spec.name, key, count)
        except Exception:
            logger.exception("保存 %s %s 的失败状态出错", spec.name, key)
            alerts.append(record)
            continue
        if count == 1 or count >= threshold:
            alerts.append(record)
    return alerts


def run_monitors(specs: Sequence[MonitorSpec]) -> list[dict]:
    """先执行所有业务线，再仅补跑失败项一次，最后应用失败策略。"""
    retry_queue = []
    for spec in specs:
        if not spec.rules_file.exists():
            logger.info("%s 配置文件尚未创建，跳过: %s", spec.name, spec.rules_file.name)
            continue
        records = run_monitor(spec)
        if records:
            retry_queue.append((spec, records))

    failures = []
    for spec, records in retry_queue:
        targets = {record.get("target") for record in records}
        logger.info("补跑 %s 的失败项", spec.name)
        failures.extend(run_monitor(spec, targets=None if None in targets else targets))
    return finalize_failures(failures, specs)
