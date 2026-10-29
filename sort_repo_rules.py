"""排序并统一格式化各来源规则文件。"""

import json
from pathlib import Path

REPO_RULES_FILE = Path(__file__).resolve().parent / "repo_rules.json"
APPLE_RULES_FILE = REPO_RULES_FILE.with_name("apple_rules.json")
RULES_FILE = REPO_RULES_FILE.with_name("rules.json")


def repository_sort_key(full_name: str) -> tuple[str, str, str]:
    """生成按 repo 名称排序的键。"""
    repo = full_name.split("/", 1)[-1]
    return repo.casefold(), full_name.casefold(), full_name


def sort_rules(rules: dict, sort_key=repository_sort_key) -> dict:
    """按指定名称规则排序顶层条目，保留条目内容。"""
    return dict(
        sorted(
            rules.items(),
            key=lambda item: sort_key(item[0]),
        )
    )


def load_rules(path: Path) -> dict:
    """读取规则文件。"""
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def main() -> int:
    for path, sort_key in (
        (REPO_RULES_FILE, repository_sort_key),
        (APPLE_RULES_FILE, lambda name: (name.casefold(), name)),
        (RULES_FILE, lambda name: (name.casefold(), name)),
    ):
        if not path.exists():
            print(f"配置文件尚未创建，跳过: {path}")
            continue
        rules = load_rules(path)
        sorted_rules = sort_rules(rules, sort_key)
        formatted = json.dumps(sorted_rules, ensure_ascii=False, indent=2) + "\n"
        if path.read_bytes() == formatted.encode("utf-8"):
            print(f"规则已经有序且格式规范: {path}")
            continue

        path.write_text(formatted, encoding="utf-8", newline="\n")

        print(f"排序及格式化完成，共 {len(sorted_rules)} 项: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
