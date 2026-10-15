import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

import config
from ai.error_analysis import generate_error_report
from notifications.alerts import send_error_notification
from workflows.apple import RULES_FILE as APPLE_RULES_FILE
from workflows.apple import run_apple_monitor
from workflows.github import run_github_monitor
from workflows.github_rules import RULES_FILE as REPO_RULES_FILE

NOISY_LOGGERS = ("httpcore", "httpx", "openai", "urllib3")


def setup_logging():
    log_dir = config.BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s")

    # 文件处理器（UTF-8，DEBUG 级别，带时间戳的文件名）
    timestamp = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d_%H%M%S")
    file_handler = logging.FileHandler(
        log_dir / f"pipeline_{timestamp}.log",
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    # 控制台处理器（INFO 级别）
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    for logger_name in NOISY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


def _notify_failures(error_records: list[dict]) -> None:
    """先尝试生成 AI 报告，再发送不依赖分析成功与否的通知。"""
    if not error_records:
        return
    if not config.FEISHU_ENABLED:
        logger.info("飞书通知未启用")
        return
    if not config.FEISHU_WEBHOOK_URL or not config.FEISHU_SIGNING_SECRET:
        logger.error("飞书配置不完整，跳过错误通知")
        return

    analysis_records = [
        record for record in error_records if not record.get("auto_disabled")
    ]
    llm_failed = any(
        record.get("error") in {"llm_failed", "all_llms_failed"}
        for record in error_records
    )
    ai_report = None
    if analysis_records and not llm_failed:
        ai_report = generate_error_report(analysis_records)
    send_error_notification(error_records, ai_report)


def main():
    """独立运行已配置的业务线，最后汇总本轮错误。"""
    setup_logging()
    failures = []
    workflows = (
        ("GitHub Release", REPO_RULES_FILE, run_github_monitor),
        ("App Store", APPLE_RULES_FILE, run_apple_monitor),
    )
    for name, rules_file, run in workflows:
        if not rules_file.exists():
            logger.info("%s 配置文件尚未创建，跳过: %s", name, rules_file.name)
            continue
        try:
            failures.extend(run())
        except Exception as error:
            logger.exception("%s 业务线执行失败", name)
            failures.append(
                {
                    "stage": name,
                    "error": type(error).__name__,
                    "message": str(error),
                }
            )
    _notify_failures(failures)


if __name__ == "__main__":
    main()
