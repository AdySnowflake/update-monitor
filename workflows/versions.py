"""拿到版本信息后的公共处理：比较版本并发送更新通知。"""

import logging

from models import VersionInfo
from notifications import Notification, send_notification

logger = logging.getLogger(__name__)


def process_version(
    info: VersionInfo,
    previous_version: str | None,
    channels: list[str],
    *,
    content: str = "Update Monitor",
) -> str:
    """版本变化时通知；全部渠道送达后返回可保存的版本。"""
    if info.version == previous_version:
        logger.info("%s 当前版本 %s，版本保持一致", info.name, info.version)
        return info.version

    logger.info("发现版本变化: %s %s → %s", info.name, previous_version, info.version)
    if info.url:
        content += f"\n{info.url}"
    message = Notification(title=f"{info.name} - {info.version}", content=content)
    results = send_notification(message, channels)
    failed = [channel for channel in channels if not results.get(channel)]
    if failed:
        raise RuntimeError(f"版本 {info.version} 通知投递失败: {', '.join(failed)}")
    return info.version
