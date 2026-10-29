"""客户端与业务流程之间传递的数据。"""

from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote


@dataclass(frozen=True)
class ReleaseInfo:
    owner: str
    repo: str
    tag: str
    assets: list[dict]

    @property
    def name(self) -> str:
        return self.repo

    @property
    def version(self) -> str:
        return self.tag

    @property
    def url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}/releases/tag/{quote(self.tag, safe='')}"


@dataclass(frozen=True)
class VersionInfo:
    name: str
    version: str
    url: str = ""
    release_date: datetime | None = None


def parse_release_date(value: str) -> datetime:
    """校验包含时区的 ISO 8601 发布时间，统一为 UTC。"""
    if not isinstance(value, str):
        raise ValueError("发布时间应为包含时区的 ISO 8601 字符串")
    try:
        release_date = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("发布时间应为包含时区的 ISO 8601 字符串") from error
    if release_date.tzinfo is None:
        raise ValueError("发布时间应包含时区，例如 2026-10-28T18:48:05Z")
    return release_date.astimezone(UTC)
