import json
import logging

import config
from ai.file_selector import select_file
from files.download import download_file
from files.transfer import move_downloaded_file
from notifications import Notification, send_notification
from workflows.github_rules import get_repo_rules

logger = logging.getLogger(__name__)

# 传给 AI 选择器时剔除 Tag 筛选与运维字段，提示词只关心文件筛选规则
BOOKKEEPING_RULE_KEYS = frozenset(
    {"last_tag", "disabled", "consecutive_failures", "next_check_after", "tag_contains"}
)


class StepLogger:
    """流水线步骤日志器。"""

    def __init__(self, step_num: int, total: int, name: str):
        self.step_num = step_num
        self.total = total
        self.name = name
        self.lines: list[str] = []
        self.failed = False
        self.failure_reason: str | None = None

    def __enter__(self):
        logger.info(f"━━━ [{self.step_num}/{self.total}] {self.name} ━━━")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        for line in self.lines:
            logger.info(f"  {line}")
        if exc_type or self.failed:
            reason = str(exc_val) if exc_val else self.failure_reason or "未知错误"
            logger.error(f"  ✗ 失败 — {reason}")
        else:
            logger.info("  ✓ 完成")
        return False

    def log(self, text: str):
        self.lines.append(text)

    def fail(self, text: str) -> None:
        self.failed = True
        self.failure_reason = text


def _process_release_assets(
    owner: str,
    repo: str,
    tag: str,
    assets: list[dict],
) -> dict:
    """选择并下载 release asset。

    Args:
        owner: 仓库所有者
        repo: 仓库名称
        tag: 版本标签
        assets: GitHub release 的 assets 列表

    Returns:
        处理结果字典
    """
    full_repo = f"{owner}/{repo}"
    total_steps = 4

    # [1/4] 获取 Release 资源
    with StepLogger(1, total_steps, "获取 Release 资源") as step:
        step.log(f"{full_repo} @ {tag}")
        if not assets:
            error_log = f"{full_repo} @ {tag} 未获取到任何 Release assets"
            step.fail(error_log)
            return {
                "success": 0,
                "error": "no_assets",
                "error_log": error_log,
            }
        assets_display = "\n".join(
            f"    - {a['name']} ({a['size'] / 1024 / 1024:.1f}MB, {a['content_type']})\n"
            f"      {a['browser_download_url']}"
            for a in assets
        )
        step.log(f"{len(assets)} 个 assets:\n{assets_display}")

    # [2/4] 加载仓库规则
    with StepLogger(2, total_steps, "加载仓库规则") as step:
        step.log(f"{owner}/{repo}")
        rules = get_repo_rules(f"{owner}/{repo}")
        step.log(json.dumps(rules, ensure_ascii=False) if rules else "无匹配规则")

    # [3/4] AI 选择文件
    with StepLogger(3, total_steps, "AI 选择文件") as step:
        file_result = select_file(
            assets=assets,
            rules={
                key: value
                for key, value in rules.items()
                if key not in BOOKKEEPING_RULE_KEYS
            },
        )
        step.log(json.dumps(file_result, ensure_ascii=False, indent=2))
        if file_result.get("success") != 1:
            error_log = file_result.get("error_log") or (
                f"{full_repo} @ {tag} 的 AI 文件选择未返回可用结果"
            )
            step.fail(error_log)
            return {
                "success": 0,
                "error": file_result.get("error", "file_selection_failed"),
                "error_log": error_log,
            }

        download_url = file_result.get("download_url")
        asset_urls = {
            asset["browser_download_url"]
            for asset in assets
        }
        if download_url not in asset_urls:
            error_log = (
                f"{full_repo} @ {tag} 的 AI 下载地址不在 Release assets 中: "
                f"{download_url!r}"
            )
            step.fail(error_log)
            return {
                "success": 0,
                "error": "invalid_download_url",
                "error_log": error_log,
            }

    # [4/4] 下载文件
    with StepLogger(4, total_steps, "下载文件") as step:
        step.log(download_url)
        try:
            filepath = download_file(download_url)
        except Exception as error:
            error_log = (
                f"{full_repo} @ {tag} 文件下载失败: "
                f"{type(error).__name__}: {error}"
            )
            step.fail(error_log)
            return {
                "success": 0,
                "error": "download_failed",
                "error_log": error_log,
            }
        step.log(f"→ {filepath}")

    # 转移下载文件（可选）
    final_filepath = filepath
    if config.MOVE_TARGET_DIR:
        try:
            moved_path = move_downloaded_file(filepath, config.MOVE_TARGET_DIR)
        except Exception as error:
            error_log = (
                f"{full_repo} @ {tag} 文件转移失败: "
                f"{type(error).__name__}: {error}"
            )
            logger.error(error_log)
            return {
                "success": 0,
                "error": "file_transfer_failed",
                "error_log": error_log,
                "file": str(filepath),
            }
        final_filepath = moved_path

    # 全部文件操作完成后，统一通过通知层创建待办。
    if config.TODO_ENABLED:
        send_notification(
            Notification(
                title=f"{repo} - {tag}",
                content=f"Update Monitor - GitHub Release\n{full_repo}\n文件：{final_filepath}",
            ),
            ["ticktick"],
        )

    logger.info(f"流程完成: {total_steps}/{total_steps} 步骤成功")
    return {"success": 1, "download_url": download_url, "file": str(final_filepath)}


def run_release(
    owner: str, repo: str, tag: str, assets: list[dict]
) -> dict:
    """处理 GitHub release assets。

    Args:
        owner: 仓库所有者
        repo: 仓库名称
        tag: 版本标签
        assets: GitHub release 的 assets 列表

    Returns:
        处理结果字典
    """
    logger.info(f"开始处理 API release: {owner}/{repo} @ {tag}")

    return _process_release_assets(owner, repo, tag, assets=assets)
