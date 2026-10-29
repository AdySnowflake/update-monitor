"""通过 HTTP GET 查询公开版本文本。"""

from urllib.parse import urlsplit

from clients.http import get_query_response
from models import VersionInfo


def fetch_update_release(url: str, *, name: str) -> VersionInfo:
    """将去除首尾空白的完整响应文本作为版本值。"""
    if not isinstance(url, str):
        raise ValueError("url 应为 HTTP 或 HTTPS 地址")
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("url 应为 HTTP 或 HTTPS 地址")
    with get_query_response(url) as response:
        version = response.text.strip()
    if not version:
        raise ValueError("版本接口返回了空文本")
    return VersionInfo(name=name, version=version, url=url)
