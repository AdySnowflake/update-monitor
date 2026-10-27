"""查询 GitHub 最新 Release，不参与版本比较与规则筛选。"""

import logging

from clients.http import get_query_response
from config import get_github_headers
from models import ReleaseInfo

logger = logging.getLogger(__name__)
GITHUB_API = "https://api.github.com"


def fetch_latest_release(
    owner: str,
    repo: str,
) -> ReleaseInfo | None:
    """返回当前最新 Release；404 表示没有可用 Release。"""
    url = f"{GITHUB_API}/repos/{owner}/{repo}/releases/latest"
    logger.info(f"检查仓库: {owner}/{repo}")

    with get_query_response(
        url, headers=get_github_headers(), allowed_statuses=(404,),
    ) as response:
        if response.status_code == 404:
            logger.warning(f"仓库 {owner}/{repo} 无 release")
            return None
        data = response.json()
    if not isinstance(data, dict):
        raise ValueError("GitHub 查询接口返回应为对象")
    tag = data.get("tag_name")
    if not isinstance(tag, str) or not tag.strip():
        raise ValueError("latest release 缺少 tag_name")
    assets = data.get("assets", [])
    if not isinstance(assets, list) or any(not isinstance(asset, dict) for asset in assets):
        raise ValueError("latest release 的 assets 应为对象数组")

    return ReleaseInfo(owner=owner, repo=repo, tag=tag, assets=assets)
