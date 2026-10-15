import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from clients.llm import get_llm_client, has_llm_config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是 Update Monitor 的故障分析助手。
根据错误记录，用简体中文输出一段简洁的分析结论。
说明最可能的故障原因和直接影响；证据不足时明确说明。
不要提供处置建议，不要复述原始记录，不要使用标题、列表或 Markdown。"""


def generate_error_report(error_records: list[dict]) -> str | None:
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=json.dumps(
                error_records,
                ensure_ascii=False,
                indent=2,
            )
        ),
    ]

    roles = ["primary"]
    if has_llm_config("fallback"):
        roles.append("fallback")

    for role in roles:
        try:
            response = get_llm_client(role).invoke(messages)
            report = str(response.content).strip()
            if report:
                return report
        except Exception as error:  # noqa: BLE001
            logger.warning(f"{role} LLM 错误分析失败: {error}")

    return None
