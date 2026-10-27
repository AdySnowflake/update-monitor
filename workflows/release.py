import hashlib
import json
import logging

import config
from ai.file_selector import select_files
from files.download import download_file
from files.transfer import move_downloaded_files

logger = logging.getLogger(__name__)


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


def run_release(owner: str, repo: str, tag: str, assets: list[dict], filters: list[dict]) -> dict:
    """按筛选组选择、下载和转移文件；通知与状态提交由公共流程负责。"""
    full_repo = f"{owner}/{repo}"
    total_steps = 4
    logger.info("开始处理 API release: %s @ %s", full_repo, tag)

    with StepLogger(1, total_steps, "获取 Release 资源") as step:
        step.log(f"{full_repo} @ {tag}")
        if not assets:
            error_log = f"{full_repo} @ {tag} 未获取到任何 Release assets"
            step.fail(error_log)
            return {"success": 0, "error": "no_assets", "error_log": error_log}
        for asset in assets:
            step.log(f"{asset['name']} — {asset['browser_download_url']}")

    with StepLogger(2, total_steps, "加载仓库筛选组") as step:
        if not isinstance(filters, list) or not filters or any(
            not isinstance(group, dict) for group in filters
        ):
            raise ValueError("filters 必填，应为非空对象数组；单文件筛选也应放入一组")
        step.log(json.dumps(filters, ensure_ascii=False))

    with StepLogger(3, total_steps, "AI 按组选择文件") as step:
        result = select_files(assets=assets, filters=filters)
        step.log(json.dumps(result, ensure_ascii=False))
        if result.get("success") != 1:
            error_log = result.get("error_log") or f"{full_repo} @ {tag} 的筛选组未全部选出文件"
            step.fail(error_log)
            return {
                "success": 0,
                "error": result.get("error", "file_selection_failed"),
                "error_log": error_log,
            }
        urls = result.get("download_urls")
        asset_urls = {asset["browser_download_url"] for asset in assets}
        if not isinstance(urls, list) or len(urls) != len(filters) or any(
            not isinstance(url, str) or url not in asset_urls for url in urls
        ):
            error_log = f"{full_repo} @ {tag} 每个筛选组应返回一个来自当前 Release assets 的下载地址"
            step.fail(error_log)
            return {"success": 0, "error": "invalid_download_urls", "error_log": error_log}
        download_urls = list(dict.fromkeys(urls))
        if len({url.rsplit("/", 1)[-1] for url in download_urls}) != len(download_urls):
            error_log = f"{full_repo} @ {tag} 选中的不同下载地址包含同名文件"
            step.fail(error_log)
            return {"success": 0, "error": "duplicate_file_names", "error_log": error_log}

    # 按仓库和版本隔离缓存，跨轮重试复用完整下载文件。
    cache_key = hashlib.sha256(f"{full_repo}@{tag}".encode()).hexdigest()
    download_dir = config.DOWNLOAD_DIR / cache_key
    filepaths = []
    with StepLogger(4, total_steps, "下载文件") as step:
        for url in download_urls:
            step.log(url)
            try:
                filepath = download_file(url, download_dir=download_dir)
            except Exception as error:
                error_log = f"{full_repo} @ {tag} 文件下载失败 ({url}): {type(error).__name__}: {error}"
                step.fail(error_log)
                return {"success": 0, "error": "download_failed", "error_log": error_log}
            filepaths.append(filepath)
            step.log(f"→ {filepath}")

    final_filepaths = filepaths
    if config.MOVE_TARGET_DIR:
        try:
            final_filepaths = move_downloaded_files(filepaths, config.MOVE_TARGET_DIR)
        except Exception as error:
            error_log = f"{full_repo} @ {tag} 文件转移失败: {type(error).__name__}: {error}"
            logger.error(error_log)
            return {"success": 0, "error": "file_transfer_failed", "error_log": error_log}

    logger.info("流程完成: %s @ %s，共 %s 个文件", full_repo, tag, len(final_filepaths))
    return {
        "success": 1,
        "download_urls": download_urls,
        "files": [str(filepath) for filepath in final_filepaths],
    }
