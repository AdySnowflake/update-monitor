"""客户端与业务流程之间传递的数据。"""

from dataclasses import dataclass
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
