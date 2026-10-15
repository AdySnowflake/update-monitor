import json
import logging

from config import BASE_DIR

logger = logging.getLogger(__name__)

RULES_FILE = BASE_DIR / "repo_rules.json"

MAX_CONSECUTIVE_FAILURES = 3


def load_rules() -> dict:
    """加载规则文件。"""
    with open(RULES_FILE, encoding="utf-8") as file:
        return json.load(file)


def save_rules(rules: dict) -> None:
    """保存规则文件。"""
    with open(RULES_FILE, "w", encoding="utf-8") as file:
        json.dump(rules, file, ensure_ascii=False, indent=2)
        file.write("\n")
    logger.info(f"规则已保存到 {RULES_FILE}")


def get_repo_rules(full_name: str) -> dict:
    """获取指定仓库的规则。

    Args:
        full_name: 仓库全名，格式为 owner/repo

    Returns:
        规则字典
    """
    rule = load_rules()[full_name]
    logger.info(f"找到 {full_name} 的规则: {rule}")
    return rule


def update_repo_tag(owner: str, repo: str, tag: str) -> None:
    """更新仓库的 last_tag 字段并保存。

    Args:
        owner: 仓库所有者
        repo: 仓库名称
        tag: 新的版本标签
    """
    rules = load_rules()
    full_name = f"{owner}/{repo}"
    rules[full_name]["last_tag"] = tag
    logger.info(f"更新 {full_name} 的 last_tag 为 {tag}")
    save_rules(rules)


def is_disabled(rule: dict) -> bool:
    """判断仓库是否被禁用，仅接受布尔值 true，其他取值视为非法配置。"""
    value = rule.get("disabled")
    if value is None or isinstance(value, bool):
        return value is True
    raise ValueError(
        f"disabled 字段应为布尔值 true/false，当前为 {value!r}"
    )


def clear_failure_state(owner: str, repo: str) -> None:
    """清除连续失败计数及旧版退避字段，字段不存在时不写盘。"""
    full_name = f"{owner}/{repo}"
    try:
        rules = load_rules()
        rule = rules.get(full_name)
        if rule is None:
            return
        if "consecutive_failures" not in rule and "next_check_after" not in rule:
            return
        rule.pop("consecutive_failures", None)
        rule.pop("next_check_after", None)
        save_rules(rules)
        logger.info(f"已清除 {full_name} 的连续失败状态")
    except Exception:
        logger.exception(f"清除 {full_name} 的失败状态出错")


def record_failure(full_name: str) -> int:
    """累计一次失败，第三轮失败后禁用仓库并清除计数。"""
    rules = load_rules()
    rule = rules[full_name]
    count = int(rule.get("consecutive_failures") or 0) + 1
    rule.pop("next_check_after", None)  # 清理旧版字段，重试间隔由 cron 控制
    if count >= MAX_CONSECUTIVE_FAILURES:
        rule.pop("consecutive_failures", None)
        rule["disabled"] = True
        logger.error("%s 连续失败 %s 轮，已自动禁用", full_name, count)
    else:
        rule["consecutive_failures"] = count
        logger.warning("%s 连续失败 %s 轮，下轮继续检查", full_name, count)
    save_rules(rules)
    return count
