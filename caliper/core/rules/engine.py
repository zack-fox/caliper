"""规则库装载与校验。"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

from core.model.entities import Item
from core.rules.dsl import RuleError, validate_expect


class RulesError(Exception):
    """规则库非法。"""


class Rule(BaseModel):
    rule_id: str = ""
    level: int
    item: int
    point: int
    block: str
    expect: dict
    pass_reason: str
    fail_reason: str
    # 条件证据：中间件/数据库块按组件是否部署才出现，缺失时跳过而不判为未采集。
    optional_block: bool = False

    def reference_id(self, item_id: str = "") -> str:
        """生成内容稳定的规则引用号，规则条件变化时引用号也随之变化。"""
        if self.rule_id:
            return self.rule_id
        identity = json.dumps(
            {"block": self.block, "expect": self.expect},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:8].upper()
        item_key = item_id or f"ITEM{self.item}"
        return f"L{self.level}-{item_key}-P{self.point:02d}-{digest}"


_LEVEL_FILE = re.compile(r"level([234])")


class RuleSet(BaseModel):
    rules: list[Rule]

    @classmethod
    def load(cls, rules_dir: Path, items: dict[int, list[Item]]) -> "RuleSet":
        rules_dir = Path(rules_dir)
        if not rules_dir.is_dir():
            raise RulesError(f"规则目录不存在：{rules_dir}")
        files = sorted(rules_dir.glob("*.yaml"))
        if not files:
            raise RulesError(f"{rules_dir}：没有任何规则文件")

        records: list[dict] = []
        item_ids = {
            (level, item.seq): item.item_id
            for level, level_items in items.items()
            for item in level_items
        }
        for path in files:
            match = _LEVEL_FILE.fullmatch(path.stem)
            if not match:
                raise RulesError(f"{path.name}：规则文件名必须是 level2.yaml / level3.yaml / level4.yaml")
            level = int(match.group(1))
            with path.open(encoding="utf-8") as handle:
                data = yaml.safe_load(handle) or {}
            if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
                raise RulesError(f"{path}：应为 {{rules: [...]}}")
            for record in data["rules"]:
                record = dict(record)
                record["level"] = level
                if not record.get("rule_id"):
                    try:
                        provisional = Rule.model_validate(record)
                    except ValidationError as exc:
                        raise RulesError(f"{path}：规则字段非法：{exc}") from exc
                    record["rule_id"] = provisional.reference_id(
                        item_ids.get((level, int(record["item"])), "")
                    )
                records.append(record)

        try:
            ruleset = cls(rules=[Rule.model_validate(record) for record in records])
        except ValidationError as exc:
            raise RulesError(f"规则字段非法：{exc}") from exc

        ruleset.validate(items)
        return ruleset

    def validate(self, items: dict[int, list[Item]]) -> None:
        seen: set[tuple[int, int, int, str]] = set()
        seen_ids: set[str] = set()
        by_level = {
            (level, item.seq): item for level, level_items in items.items() for item in level_items
        }
        for rule in self.rules:
            if (rule.level, rule.item) not in by_level:
                raise RulesError(f"规则引用了不存在的 item：{rule.level} 级 {rule.item}")
            key = (rule.level, rule.item, rule.point, rule.block)
            if key in seen:
                raise RulesError(
                    f"重复规则：{rule.level} 级 item {rule.item} 实施点 {rule.point} "
                    f"检查块「{rule.block}」"
                )
            seen.add(key)
            if rule.rule_id:
                if rule.rule_id in seen_ids:
                    raise RulesError(f"规则引用号重复：{rule.rule_id}")
                seen_ids.add(rule.rule_id)
            try:
                validate_expect(rule.expect)
            except RuleError as exc:
                raise RulesError(f"item {rule.item} 实施点 {rule.point}：{exc}") from exc
        for (level, seq), item in by_level.items():
            if item.policy.value == "binary":
                item_rules = [
                    rule for rule in self.rules if rule.level == level and rule.item == seq
                ]
                if not item_rules:
                    continue
                if not item.binary:
                    raise RulesError(f"item {seq} 的 policy 为 binary 但 binary 标记为 false")

    def for_item(self, seq: int, level: int) -> list[Rule]:
        return sorted(
            (
                rule
                for rule in self.rules
                if rule.item == seq and rule.level == level
            ),
            key=lambda rule: rule.point,
        )

    def items_with_rules(self, level: int) -> set[int]:
        return {rule.item for rule in self.rules if rule.level == level}

    def points_for_item(self, seq: int, level: int) -> set[int]:
        return {
            rule.point
            for rule in self.rules
            if rule.item == seq and rule.level == level
        }
