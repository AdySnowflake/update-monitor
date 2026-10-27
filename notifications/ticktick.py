import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

import config

logger = logging.getLogger(__name__)

TICKTICK_API_URL = "https://api.ticktick.com/open/v1/task"
TIMEZONE = ZoneInfo("Asia/Shanghai")


def create_todo(title: str, content: str = "") -> bool:
    """创建 TickTick 待办事项。

    Args:
        title: 待办标题，由业务线提供
        content: 待办内容，由业务线提供

    Returns:
        是否创建成功
    """
    start_datetime = datetime.now(TIMEZONE).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    token = config.TICKTICK_ACCESS_TOKEN
    project_id = config.TICKTICK_PROJECT_ID
    if not token or not project_id:
        logger.warning("TickTick 配置缺失，跳过创建待办")
        return False

    task_data = {
        "title": title,
        "content": content,
        "projectId": project_id,
        "startDate": start_datetime.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "isAllDay": True,
        "timeZone": "Asia/Shanghai",
    }
    headers = {
        "Authorization": f"Bearer {token}",
    }

    logger.info(f"创建待办: {title} @ {start_datetime.date().isoformat()}")

    try:
        resp = requests.post(
            TICKTICK_API_URL,
            json=task_data,
            headers=headers,
            proxies=config.get_proxies(),
            timeout=config.HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        logger.info("待办创建成功")
        return True
    except requests.RequestException as e:
        logger.error(f"待办创建失败: {e}")
        return False
