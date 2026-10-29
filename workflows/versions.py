"""来源无关的版本检测，不执行通知或持久化。"""

from datetime import datetime
from enum import StrEnum

from models import ReleaseInfo, VersionInfo

UpdateInfo = ReleaseInfo | VersionInfo


class DetectionStatus(StrEnum):
    CHANGED = "changed"
    UNCHANGED = "unchanged"
    FILTERED = "filtered"
    UNAVAILABLE = "unavailable"
    STALE = "stale"


def detect_version(
    info: UpdateInfo | None,
    previous_version: str | None,
    *,
    accepted: bool = True,
    previous_release_date: datetime | None = None,
) -> DetectionStatus:
    if info is None:
        return DetectionStatus.UNAVAILABLE
    if info.version == previous_version:
        return DetectionStatus.UNCHANGED
    if not accepted:
        return DetectionStatus.FILTERED
    if previous_release_date is not None and isinstance(info, VersionInfo):
        if info.release_date is None:
            raise ValueError("查询结果缺少发布时间")
        if info.release_date <= previous_release_date:
            return DetectionStatus.STALE
    return DetectionStatus.CHANGED
