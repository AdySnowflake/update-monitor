"""各业务线共用的规则读取、原子写入与状态更新。"""

import json
import os
import tempfile
from pathlib import Path


class RuleStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict:
        with self.path.open(encoding="utf-8") as file:
            rules = json.load(file)
        if not isinstance(rules, dict):
            raise ValueError("监控规则应为 JSON 对象")
        return rules

    def save(self, rules: dict) -> None:
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent, delete=False
            ) as file:
                temporary_path = Path(file.name)
                json.dump(rules, file, ensure_ascii=False, indent=2)
                file.write("\n")
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def update(self, key: str, values: dict | None = None, *, remove: tuple[str, ...] = ()) -> None:
        rules = self.load()
        rule = rules[key]
        updated = {**rule, **(values or {})}
        for field in remove:
            updated.pop(field, None)
        if updated != rule:
            rules[key] = updated
            self.save(rules)
