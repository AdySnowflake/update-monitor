"""客户端与业务流程之间传递的数据。"""

from dataclasses import dataclass


@dataclass
class ReleaseInfo:
    owner: str
    repo: str
    tag: str
    assets: list[dict]


@dataclass(frozen=True)
class VersionInfo:
    name: str
    version: str
    url: str = ""
