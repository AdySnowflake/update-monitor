"""统一构造版本更新消息，投递失败时保留版本等待重试。"""

from dataclasses import dataclass

import config
from models import ReleaseInfo, VersionInfo
from notifications.dispatcher import Notification, send_notification


@dataclass(frozen=True)
class UpdateNotification:
    content: str


def notify_update(info: ReleaseInfo | VersionInfo, policy: UpdateNotification) -> dict[str, bool]:
    """成功更新固定走 TickTick；是否启用仍由全局 TODO_ENABLED 控制。"""
    if not config.TODO_ENABLED:
        return {}
    content = policy.content
    if info.url:
        content += f"\n{info.url}"
    results = send_notification(
        Notification(title=f"{info.name} - {info.version}", content=content),
        ["ticktick"],
    )
    if not results.get("ticktick"):
        raise RuntimeError(f"版本 {info.version} 通知投递失败: ticktick")
    return results
