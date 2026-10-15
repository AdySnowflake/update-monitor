from datetime import datetime
from zoneinfo import ZoneInfo

from notifications import Notification, send_notification

TIMEZONE = ZoneInfo("Asia/Shanghai")


def send_error_notification(
    error_records: list[dict],
    ai_report: str | None = None,
) -> None:
    occurred_at = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S %Z")
    sections = [f"**发生时间**：{occurred_at}"]

    for index, record in enumerate(error_records, start=1):
        repository = (
            record.get("repository")
            or record.get("target")
            or record.get("stage")
            or "未知目标"
        )
        tag = f" @ {record['tag']}" if record.get("tag") else ""
        label = "故障对象" if len(error_records) == 1 else f"故障 {index}"
        error_text = str(
            record.get("error_log")
            or record.get("message")
            or record.get("error")
            or "unknown_error"
        )
        section = (
            f"**{label}**：{repository}{tag}\n\n"
            f"**错误日志**\n```text\n{error_text}\n```"
        )

        if record.get("auto_disabled"):
            section += (
                "\n\n**自动禁用**：连续失败 3 轮，已暂停该仓库。\n\n"
                "**恢复方法**：修复问题后，将 repo_rules.json 中该仓库的 "
                "`disabled` 改为 `false` 或删除该字段。"
            )
        sections.append(section)

    if ai_report:
        sections.append(f"**AI 分析**\n\n{ai_report}")

    send_notification(
        Notification("Update Monitor 告警", "\n\n---\n\n".join(sections), level="error"),
        ["feishu"],
    )
