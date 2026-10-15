import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# 文件目录
BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"

_move_target_dir = os.getenv("MOVE_TARGET_DIR")
MOVE_TARGET_DIR = Path(_move_target_dir).expanduser() if _move_target_dir else None

# HTTP
HTTP_PROXY = os.getenv("HTTP_PROXY")
HTTPS_PROXY = os.getenv("HTTPS_PROXY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# LLM
LLM_PRIMARY_BASE_URL = os.getenv("LLM_PRIMARY_BASE_URL")
LLM_PRIMARY_API_KEY = os.getenv("LLM_PRIMARY_API_KEY")
LLM_PRIMARY_MODEL = os.getenv("LLM_PRIMARY_MODEL")

LLM_FALLBACK_BASE_URL = os.getenv("LLM_FALLBACK_BASE_URL")
LLM_FALLBACK_API_KEY = os.getenv("LLM_FALLBACK_API_KEY")
LLM_FALLBACK_MODEL = os.getenv("LLM_FALLBACK_MODEL")

LLM_REQUEST_TIMEOUT_SECONDS = float(
    os.getenv("LLM_REQUEST_TIMEOUT_SECONDS", "30")
)

# 飞书
FEISHU_ENABLED = os.getenv("FEISHU_ENABLED", "false").lower() == "true"
FEISHU_WEBHOOK_URL = os.getenv("FEISHU_WEBHOOK_URL")
FEISHU_SIGNING_SECRET = os.getenv("FEISHU_SIGNING_SECRET")

# TickTick
TODO_ENABLED = os.getenv("TODO_ENABLED", "false").lower() == "true"
TICKTICK_ACCESS_TOKEN = os.getenv("TICKTICK_ACCESS_TOKEN")
TICKTICK_PROJECT_ID = os.getenv("TICKTICK_PROJECT_ID")


def get_proxies() -> dict | None:
    proxies = {}
    if HTTP_PROXY:
        proxies["http"] = HTTP_PROXY
    if HTTPS_PROXY:
        proxies["https"] = HTTPS_PROXY
    return proxies or None


def get_github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers
