"""公共通知接口。"""

from .dispatcher import NOTIFIERS, Notification, send_notification

__all__ = ["NOTIFIERS", "Notification", "send_notification"]
