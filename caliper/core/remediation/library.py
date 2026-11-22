"""整改建议库：装载、校验与命中条件。

每条规则只描述问题、成因、整改动作、优先级与标准条款；
建议文案由本库产出，大模型只能润色语言，不得改变事实与条款。
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from core.model.entities import Item

PRIORITY_ORDER: dict[str, int] = {"高": 0, "中": 1, "低": 2}
FAMILIES = {"server", "database", "network"}
STATUSES = {"active", "scaffold"}


class RemediationError(Exception):
    """整改建议库不可用。"""


def _require_text(value: str, field: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError(f"{field} 不能为空")
    return text


class AppliesTo(BaseModel):
    """命中条件：适用等级、资产族与测评项序号。"""

    model_config = ConfigDict(extra="forbid")

    level: list[int]
    family: list[str]
    # 为空表示不按序号绑定，改由控制点关键字兜底匹配。
    item_seqs: list[int] | None = None

    @field_validator("level")
    @classmethod
    def _check_level(cls, value: list[int]) -> list[int]:
        if not value:
            raise ValueError("applies_to.level 至少填写一个等级")
        bad = sorted({level for level in value if level not in {2, 3, 4}})
        if bad:
            raise ValueError(f"applies_to.level 只支持 2/3/4，实际 {bad}")
        return sorted(set(value))

    @field_validator("family")
    @classmethod
    def _check_family(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("applies_to.family 至少填写一个资产族")
        bad = sorted({family for family in value if family not in FAMILIES})
        if bad:
            raise ValueError(f"applies_to.family 只支持 server/database/network，实际 {bad}")
        return sorted(set(value))

    @field_validator("item_seqs")
    @classmethod
    def _check_item_seqs(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        if not value:
            raise ValueError("applies_to.item_seqs 填写后不能为空；不限定时请留空")
        bad = sorted({seq for seq in value if not isinstance(seq, int) or seq < 1})
        if bad:
            raise ValueError(f"applies_to.item_seqs 必须为正整数，实际 {bad}")
        return sorted(set(value))


class RemediationRule(BaseModel):
    """一条整改建议规则：命中条件 + 问题 + 成因 + 动作 + 优先级 + 条款。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    applies_to: AppliesTo
    priority: str
    problem: str
    cause: str
    action: str
    clause: str

    @field_validator("id", "title", "problem", "cause", "action", "clause")
    @classmethod
    def _check_text(cls, value: str, info) -> str:
        return _require_text(value, info.field_name)

    @field_validator("priority")
    @classmethod
    def _check_priority(cls, value: str) -> str:
        text = value.strip()
        if text not in PRIORITY_ORDER:
            raise ValueError(f"priority 只支持 高/中/低，实际 {value!r}")
        return text


class RemediationLibrary(BaseModel):
    """整改建议库。status=active 时必须有规则；scaffold 允许暂时为空。"""

    version: str
    status: str
    path: Path | None = None
    rules: list[RemediationRule] = Field(default_factory=list)

    @classmethod
    def load(
        cls,
        pack_dir: Path,
        items: list[Item] | dict[int, Item] | None = None,
    ) -> "RemediationLibrary":
        """装载规则文件；传入 items 时额外校验 item_seqs 引用真实测评项。"""
        pack_dir = Path(pack_dir)
        path = pack_dir / "remediation.yaml"
        if not path.is_file():
            raise RemediationError(f"{path}：缺少整改建议库")
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise RemediationError(f"{path}：YAML 无法解析：{exc}") from exc
        if not isinstance(data, dict):
            raise RemediationError(f"{path}：规则文件应为对象")

        version = str(data.get("version", "")).strip()
        if not version:
            raise RemediationError(f"{path}：缺少 version")
        status = str(data.get("status", "")).strip()
        if status not in STATUSES:
            raise RemediationError(f"{path}：status 只支持 active/scaffold，实际 {status!r}")

        raw_rules = data.get("rules")
        if raw_rules is None:
            raw_rules = []
        if not isinstance(raw_rules, list):
            raise RemediationError(f"{path}：rules 应为列表")
        try:
            rules = [RemediationRule.model_validate(record) for record in raw_rules]
        except ValidationError as exc:
            raise RemediationError(f"{path}：规则字段非法：{exc}") from exc

        if status == "active" and not rules:
            raise RemediationError(f"{path}：标记为 active 但没有规则")
        seen: set[str] = set()
        for rule in rules:
            if rule.id in seen:
                raise RemediationError(f"{path}：规则 id 重复：{rule.id}")
            seen.add(rule.id)

        if items is not None:
            item_list = list(items.values()) if isinstance(items, dict) else list(items)
            _check_references(rules, item_list, path)
        return cls(version=version, status=status, path=path, rules=rules)

    def rule_by_id(self, rule_id: str) -> RemediationRule | None:
        return next((rule for rule in self.rules if rule.id == rule_id), None)


def _check_references(rules: list[RemediationRule], items: list[Item], path: Path) -> None:
    """item_seqs 必须能在对应等级的 items 中找到；这里只校验引用形态。"""
    for rule in rules:
        for seq in rule.applies_to.item_seqs or []:
            exists = any(
                item.seq == seq and item.level in rule.applies_to.level for item in items
            )
            if not exists:
                raise RemediationError(
                    f"{path}：{rule.id} 的 item_seqs 引用了不存在的测评项 {seq}"
                )
