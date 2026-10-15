"""将下载完成的文件移动到用户配置的目标目录。"""

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


def move_downloaded_file(
    filepath: Path,
    target_dir: Path,
) -> Path:
    """移动文件到目标目录。"""
    source = Path(filepath)
    target = Path(target_dir).expanduser()

    target.mkdir(parents=True, exist_ok=True)
    destination = target / source.name

    if destination.exists() and destination.resolve() != source.resolve():
        raise FileExistsError(f"目标文件已存在，拒绝覆盖: {destination}")

    moved_path = Path(shutil.move(str(source), str(destination)))

    logger.info(f"文件转移完成: {source} → {moved_path}")
    return moved_path
