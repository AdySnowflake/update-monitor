"""GitHub 仓库轮询、Release 处理与失败状态管理。"""

import json
import logging

from clients.github import check_latest_release
from models import ReleaseInfo
from workflows.github_rules import (
    MAX_CONSECUTIVE_FAILURES,
    clear_failure_state,
    is_disabled,
    load_rules,
    record_failure,
    update_repo_tag,
)
from workflows.release import run_release

logger = logging.getLogger(__name__)


def check_new_releases() -> tuple[list[ReleaseInfo], list[dict]]:
    """遍历 repo_rules.json，返回新版本和需要告警的失败记录。"""
    rules = load_rules()
    new_releases: list[ReleaseInfo] = []
    failures: list[dict] = []

    for repo_key in rules:
        rule = rules[repo_key]
        if is_disabled(rule):
            logger.info(f"仓库 {repo_key} 已禁用，跳过")
            continue
        try:
            owner, repo = repo_key.split("/")
            release_info = check_latest_release(
                owner,
                repo,
                rule.get("last_tag"),
                tag_contains=rule.get("tag_contains"),
            )
        except Exception as error:
            error_log = (
                f"检查仓库 {repo_key!s} 失败: "
                f"{type(error).__name__}: {error}"
            )
            logger.error(error_log)
            _record_failure(
                {
                    "stage": "release_check",
                    "repository": str(repo_key),
                    "error": type(error).__name__,
                    "error_log": error_log,
                },
                failures,
            )
            continue

        if release_info:
            new_releases.append(release_info)
        else:
            clear_failure_state(owner, repo)

    logger.info(
        "检查完成，发现 %s 个新 release，%s 个仓库需要告警",
        len(new_releases), len(failures),
    )
    return new_releases, failures


def _record_failure(record: dict, failures: list[dict]) -> None:
    """首次失败和自动禁用时进入汇总告警，其余失败只记录本地日志。"""
    try:
        count = record_failure(record["repository"])
    except Exception:
        logger.exception("保存 %s 的失败计数出错", record["repository"])
        failures.append(record)
        return
    if count >= MAX_CONSECUTIVE_FAILURES:
        record["auto_disabled"] = True
        failures.append(record)
    elif count == 1:
        failures.append(record)


def run_github_monitor() -> list[dict]:
    """执行 GitHub Release 业务线，返回需要告警的失败记录。"""
    logger.info("检查 GitHub 仓库的新 release")

    try:
        new_releases, failures = check_new_releases()
    except Exception as error:
        logger.exception("检查 GitHub release 失败")
        return [
            {
                "stage": "release_check",
                "error": type(error).__name__,
                "message": str(error),
            }
        ]

    if not new_releases:
        logger.info("未发现可处理的新 release")
        return failures

    logger.info(f"发现 {len(new_releases)} 个新 release")

    for release in new_releases:
        try:
            logger.info(f"处理: {release.owner}/{release.repo} @ {release.tag}")
            result = run_release(
                release.owner, release.repo, release.tag, release.assets
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))

            if result.get("success") == 1:
                update_repo_tag(release.owner, release.repo, release.tag)
                clear_failure_state(release.owner, release.repo)
            else:
                logger.error(
                    f"处理 {release.owner}/{release.repo} @ {release.tag} 未成功，"
                    "保留 last_tag 以便下次重试"
                )
                _record_failure(
                    {
                        "stage": "release_processing",
                        "repository": f"{release.owner}/{release.repo}",
                        "tag": release.tag,
                        "error": result.get("error", "processing_failed"),
                        "error_log": result.get("error_log"),
                    },
                    failures,
                )
        except Exception as e:
            logger.exception(f"处理 {release.owner}/{release.repo} 失败")
            _record_failure(
                {
                    "stage": "release_processing",
                    "repository": f"{release.owner}/{release.repo}",
                    "tag": release.tag,
                    "error": type(e).__name__,
                    "message": str(e),
                },
                failures,
            )

    return failures
