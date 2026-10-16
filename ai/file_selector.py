import json
import logging
import time

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from clients.llm import get_llm_client, has_llm_config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个 GitHub Release 文件选择器。根据 assets 列表和 filters 筛选组，为每组选择一个最合适的下载文件。

filters 是非空数组，每组可以包含：
- extension: 文件后缀名（如 .apk、.ipa、.exe）
- include: 文件名必须包含的关键词
- exclude: 文件名不能包含的关键词

各组独立筛选，include 中的关键词应全部满足，exclude 中的关键词应全部排除。
download_urls 必须按 filters 的顺序逐组返回，每组恰好一个 URL。多组可以选中同一文件，仍按组保留对应 URL。
URL 必须直接复制 assets 列表中的 browser_download_url 字段，不要自己拼接或修改，也不要使用 url 字段。
任意一组没有符合条件的文件，整体选择失败。

输出：
- success: 1 表示全部筛选组选择成功，0 表示失败
- download_urls: 成功时为与 filters 等长的 URL 数组，失败时为空数组

{format_instructions}"""

USER_PROMPT = """Assets 列表:
{assets}

筛选组:
{filters}"""


def build_chain(llm: BaseChatModel):
    parser = JsonOutputParser()

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            ("user", USER_PROMPT),
        ]
    ).partial(format_instructions=parser.get_format_instructions())

    return prompt | llm | parser


def _invoke_with_retry(role: str, input_data: dict, max_retries: int = 2) -> dict:
    """创建指定用途的客户端并带退避重试调用。"""
    total_attempts = max_retries + 1
    chain = build_chain(get_llm_client(role))

    for attempt in range(1, total_attempts + 1):
        try:
            return chain.invoke(input_data)
        except Exception as error:
            if attempt == total_attempts:
                raise
            wait = 2 ** (attempt - 1)
            logger.warning(
                f"LLM {role!r} 调用失败，{wait}s 后重试 "
                f"({attempt}/{total_attempts}): {error}"
            )
            time.sleep(wait)


def select_files(assets: list[dict], filters: list[dict]) -> dict:
    """一次模型调用处理全部筛选组，按组返回文件 URL。"""
    input_data = {
        "assets": json.dumps(assets, ensure_ascii=False),
        "filters": json.dumps(filters, ensure_ascii=False),
    }

    try:
        result = _invoke_with_retry("primary", input_data)
    except Exception as error:
        if not has_llm_config("fallback"):
            error_log = f"主 LLM 调用失败: {type(error).__name__}: {error}"
            logger.error(error_log)
            return {
                "success": 0,
                "error": "llm_failed",
                "error_log": error_log,
            }

        logger.warning(f"主 LLM 调用失败，切换备用 LLM: {error}")
        try:
            result = _invoke_with_retry("fallback", input_data)
        except Exception as fallback_error:
            error_log = (
                "备用 LLM 调用失败: "
                f"{type(fallback_error).__name__}: {fallback_error}"
            )
            logger.error(error_log)
            return {
                "success": 0,
                "error": "all_llms_failed",
                "error_log": error_log,
            }

    if not isinstance(result, dict):
        return {"success": 0, "error": "invalid_file_selection", "error_log": "AI 文件选择结果应为对象"}
    if result.get("success") != 1:
        error_log = "AI 文件选择失败：至少一个筛选组没有选出文件"
        logger.warning(error_log)
        result.setdefault("error_log", error_log)
    return result
