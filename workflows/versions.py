"""来源无关的版本检测，不执行通知或持久化。"""

from enum import StrEnum

from models import ReleaseInfo, VersionInfo

UpdateInfo = ReleaseInfo | VersionInfo


class DetectionStatus(StrEnum):
    CHANGED = "changed"
    UNCHANGED = "unchanged"
    FILTERED = "filtered"
    UNAVAILABLE = "unavailable"


def detect_version(
    info: UpdateInfo | None,
    previous_version: str | None,
    *,
    accepted: bool = True,
) -> DetectionStatus:
    if info is None:
        return DetectionStatus.UNAVAILABLE
    if info.version == previous_version:
        return DetectionStatus.UNCHANGED
    if not accepted:
        return DetectionStatus.FILTERED
    return DetectionStatus.CHANGED
