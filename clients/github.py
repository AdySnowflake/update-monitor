"""GitHub 最新 Release 查询与 Tag 条件匹配。"""

import logging

import requests

from config import get_github_headers, get_proxies
from models import ReleaseInfo

logger = logging.getLogger(__name__)
GITHUB_API = "https://api.github.com"


def check_latest_release(
    owner: str,
    repo: str,
    last_tag: str | None,
    tag_contains: str | None = None,
) -> ReleaseInfo | None:
    """检查单个仓库是否有符合 Tag 关键词条件的新 release。"""
    if tag_contains is not None and not isinstance(tag_contains, str):
        raise ValueError("tag_contains 字段应为字符串或 null")

    url = f"{GITHUB_API}/repos/{owner}/{repo}/releases/latest"
    logger.info(f"检查仓库: {owner}/{repo}")

    resp = requests.get(
        url,
        headers=get_github_headers(),
        timeout=10,
        proxies=get_proxies(),
    )
    if resp.status_code == 404:
        logger.warning(f"仓库 {owner}/{repo} 无 release")
        return None
    resp.raise_for_status()

    data = resp.json()
    tag = data.get("tag_name")
    if not tag:
        raise ValueError("latest release 缺少 tag_name")

    if tag == last_tag:
        logger.info(f"仓库 {owner}/{repo} 无新版本（当前: {tag}）")
        return None

    if tag_contains and tag_contains not in tag:
        logger.info(
            "仓库 %s/%s 的 Tag %r 未包含关键词 %r，跳过",
            owner, repo, tag, tag_contains,
        )
        return None

    assets = data.get("assets", [])
    logger.info(f"发现新版本: {owner}/{repo} @ {tag}（{len(assets)} 个 assets）")

    return ReleaseInfo(owner=owner, repo=repo, tag=tag, assets=assets)
