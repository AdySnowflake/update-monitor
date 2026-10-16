"""批量转移下载文件，保留失败后的重试能力。"""

import filecmp
import logging
import shutil
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def move_downloaded_files(filepaths: list[Path], target_dir: Path) -> list[Path]:
    """整组复制完成后删除源文件；相同目标文件复用，不同内容拒绝覆盖。"""
    sources = [Path(path) for path in filepaths]
    target = Path(target_dir).expanduser()
    target.mkdir(parents=True, exist_ok=True)
    destinations = [target / source.name for source in sources]

    # 重试时复用上轮已经转移完成的相同文件。
    for source, destination in zip(sources, destinations):
        if destination.exists():
            if source.resolve() != destination.resolve() and not filecmp.cmp(source, destination, shallow=False):
                raise FileExistsError(f"目标文件已存在且内容不同，拒绝覆盖: {destination}")
            logger.info("复用目标文件: %s", destination)
            continue
        with tempfile.NamedTemporaryFile(dir=target, prefix=f".{source.name}.", suffix=".part", delete=False) as file:
            temporary = Path(file.name)
        try:
            shutil.copy2(source, temporary)
            if destination.exists():
                if not filecmp.cmp(temporary, destination, shallow=False):
                    raise FileExistsError(f"目标文件已存在且内容不同，拒绝覆盖: {destination}")
            else:
                temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        logger.info("文件转移完成: %s → %s", source, destination)

    # 整组完成前保留全部源文件，下一轮可以直接复用下载缓存。
    for source, destination in zip(sources, destinations):
        if source.resolve() != destination.resolve():
            source.unlink()
    return destinations
