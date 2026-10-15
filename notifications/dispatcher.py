"""两条业务线共用的通知消息和渠道入口。"""

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Literal

import config
from notifications.feishu import send_card
from notifications.ticktick import create_todo

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Notification:
    title: str
    content: str
    level: Literal["info", "error"] = "info"


def _send_feishu(message: Notification) -> bool:
    if not config.FEISHU_ENABLED:
        raise ValueError("飞书通知尚未启用，请配置 FEISHU_ENABLED=true")
    if not config.FEISHU_WEBHOOK_URL or not config.FEISHU_SIGNING_SECRET:
        raise ValueError("飞书 Webhook 或签名密钥缺失")
    send_card(
        message.title,
        message.content,
        template="red" if message.level == "error" else "blue",
    )
    return True


def _send_ticktick(message: Notification) -> bool:
    if not config.TODO_ENABLED:
        raise ValueError("TickTick 通知尚未启用，请配置 TODO_ENABLED=true")
    return create_todo(message.title, message.content)


NOTIFIERS: dict[str, Callable[[Notification], bool]] = {
    "feishu": _send_feishu,
    "ticktick": _send_ticktick,
}


def send_notification(
    message: Notification,
    channels: Iterable[str],
) -> dict[str, bool]:
    """独立投递各渠道并返回结果；单渠道失败后继续投递其他渠道。"""
    results = {}
    for channel in dict.fromkeys(channels):
        try:
            if channel not in NOTIFIERS:
                raise ValueError(f"未知通知渠道: {channel}")
            results[channel] = NOTIFIERS[channel](message)
            if results[channel]:
                logger.info("%s 通知发送成功: %s", channel, message.title)
            else:
                logger.error("%s 通知发送失败: %s", channel, message.title)
        except Exception:
            logger.exception("%s 通知发送失败: %s", channel, message.title)
            results[channel] = False
    return results
