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


def check_new_releases(targets: set[str] | None = None) -> tuple[list[ReleaseInfo], list[dict]]:
    """检查全部或指定仓库，返回新版本和全部失败记录。"""
    rules = load_rules()
    new_releases: list[ReleaseInfo] = []
    failures: list[dict] = []

    for repo_key in rules:
        if targets is not None and repo_key not in targets:
            continue
        rule = rules[repo_key]
        try:
            if is_disabled(rule):
                logger.info(f"仓库 {repo_key} 已禁用，跳过")
                continue
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
            failures.append(
                {
                    "stage": "release_check",
                    "repository": str(repo_key),
                    "error": type(error).__name__,
                    "error_log": error_log,
                }
            )
            continue

        if release_info:
            new_releases.append(release_info)
        else:
            clear_failure_state(owner, repo)

    logger.info(
        "检查完成，发现 %s 个新 release，%s 个仓库检查失败",
        len(new_releases), len(failures),
    )
    return new_releases, failures


def finalize_github_failures(records: list[dict]) -> list[dict]:
    """两遍执行后累计一次仓库失败，保留首次失败和自动禁用告警。"""
    alerts = []
    for record in records:
        repository = record.get("repository")
        if not repository:
            alerts.append(record)
            continue
        try:
            count = record_failure(repository)
        except Exception:
            logger.exception("保存 %s 的失败计数出错", repository)
            alerts.append(record)
            continue
        if count >= MAX_CONSECUTIVE_FAILURES:
            record["auto_disabled"] = True
            alerts.append(record)
        elif count == 1:
            alerts.append(record)
    return alerts


def run_github_monitor(*, targets: set[str] | None = None) -> list[dict]:
    """执行全部或指定仓库，返回本遍失败记录，供入口补跑和汇总。"""
    logger.info("检查 GitHub 仓库的新 release")

    try:
        new_releases, failures = check_new_releases(targets)
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
                failures.append(
                    {
                        "stage": "release_processing",
                        "repository": f"{release.owner}/{release.repo}",
                        "tag": release.tag,
                        "error": result.get("error", "processing_failed"),
                        "error_log": result.get("error_log"),
                    }
                )
        except Exception as e:
            logger.exception(f"处理 {release.owner}/{release.repo} 失败")
            failures.append(
                {
                    "stage": "release_processing",
                    "repository": f"{release.owner}/{release.repo}",
                    "tag": release.tag,
                    "error": type(e).__name__,
                    "message": str(e),
                }
            )

    return failures
