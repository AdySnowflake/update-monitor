"""版本查询共用的 HTTP 请求：失败后立即重试，最多尝试三次。"""

import logging

import requests

from config import HTTP_TIMEOUT, get_proxies

logger = logging.getLogger(__name__)
QUERY_MAX_ATTEMPTS = 3


def get_query_response(
    url: str,
    *,
    allowed_statuses: tuple[int, ...] = (),
    **kwargs,
) -> requests.Response:
    """只重试请求异常；调用方负责响应内容校验和关闭响应。"""
    for attempt in range(1, QUERY_MAX_ATTEMPTS + 1):
        response = None
        try:
            response = requests.get(
                url, timeout=HTTP_TIMEOUT, proxies=get_proxies(), **kwargs
            )
            if response.status_code not in allowed_statuses:
                response.raise_for_status()
            return response
        except requests.RequestException as error:
            if response is not None:
                response.close()
            if attempt == QUERY_MAX_ATTEMPTS:
                raise
            logger.warning(
                "查询请求失败（%s/%s），立即重试 %s: %s",
                attempt, QUERY_MAX_ATTEMPTS, url, error,
            )
