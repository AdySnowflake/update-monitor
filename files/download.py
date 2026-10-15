import logging
from pathlib import Path

import requests

from config import DOWNLOAD_DIR, get_proxies

logger = logging.getLogger(__name__)


def download_file(url: str, download_dir: Path | None = None) -> Path:
    """下载文件到指定目录。

    Args:
        url: 下载链接
        download_dir: 下载目录，默认 ./downloads/

    Returns:
        Path: 下载后的文件路径；失败时抛出请求或文件系统异常
    """
    download_dir = download_dir or DOWNLOAD_DIR
    download_dir.mkdir(parents=True, exist_ok=True)

    filename = url.split("/")[-1]
    filepath = download_dir / filename

    # 重复文件检查
    if filepath.exists():
        logger.info(f"文件已存在: {filepath}")
        return filepath

    temp_filepath = filepath.with_name(f"{filepath.name}.part")
    logger.info(f"开始下载: {url}")
    try:
        with requests.get(
            url,
            stream=True,
            proxies=get_proxies(),
            timeout=(10, 60),
        ) as resp:
            resp.raise_for_status()

            with open(temp_filepath, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

        temp_filepath.replace(filepath)
    except Exception:
        temp_filepath.unlink(missing_ok=True)
        raise

    logger.info(f"下载完成: {filepath}")
    return filepath
