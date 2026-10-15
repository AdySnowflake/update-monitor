"""按用途惰性创建 OpenAI 兼容的 LLM 客户端。"""

from functools import lru_cache

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

import config

LLM_CONFIGS = {
    "primary": (
        config.LLM_PRIMARY_BASE_URL,
        config.LLM_PRIMARY_API_KEY,
        config.LLM_PRIMARY_MODEL,
    ),
    "fallback": (
        config.LLM_FALLBACK_BASE_URL,
        config.LLM_FALLBACK_API_KEY,
        config.LLM_FALLBACK_MODEL,
    ),
}


def has_llm_config(role: str) -> bool:
    """指定角色具备 API Key 和模型名时返回 True。"""
    _, api_key, model = LLM_CONFIGS[role]
    return bool(api_key and model)


@lru_cache(maxsize=None)
def get_llm_client(role: str) -> ChatOpenAI:
    """使用 config.py 中的配置按角色创建并缓存 LLM 客户端。"""
    base_url, api_key, model = LLM_CONFIGS[role]

    if not api_key or not model:
        raise ValueError(f"LLM {role!r} 配置不完整")

    return ChatOpenAI(
        model=model,
        base_url=base_url,
        api_key=SecretStr(api_key),
        temperature=0,
        max_retries=0,
        timeout=config.LLM_REQUEST_TIMEOUT_SECONDS,
    )
