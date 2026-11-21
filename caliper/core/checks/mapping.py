"""checks_map.yaml：检查块 ↔ 测评项/实施点 的绑定关系。"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError

from core.model.entities import CheckBlock


class CheckMapError(Exception):
    """检查块映射非法。"""


class PointBinding(BaseModel):
    item: int
    level: int = 3
    points: list[int] = Field(default_factory=list)


class CheckBinding(BaseModel):
    os_family: list[str] = Field(default_factory=list)
    section: str = ""
    title: str
    block_index: int
    kind: str = "judge"
    binds: list[PointBinding] = Field(default_factory=list)


def _load_yaml(path: Path) -> object:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


class ChecksMap(BaseModel):
    checks: list[CheckBinding]

    @classmethod
    def load(cls, path: Path) -> "ChecksMap":
        data = _load_yaml(path)
        if not isinstance(data, dict) or "checks" not in data:
            raise CheckMapError(f"{path}：缺少 checks 列表")
        try:
            return cls.model_validate(data)
        except ValidationError as exc:
            raise CheckMapError(f"{path}：检查块映射非法：{exc}") from exc

    def titles(self) -> list[str]:
        seen: list[str] = []
        for check in self.checks:
            if check.title not in seen:
                seen.append(check.title)
        return seen

    def allowed_families(self, title: str) -> set[str]:
        families: set[str] = set()
        for check in self.checks:
            if check.title == title:
                families.update(check.os_family)
        return families

    def points_for_item(self, seq: int, level: int = 3) -> set[int]:
        points: set[int] = set()
        for check in self.checks:
            if check.kind != "judge":
                continue
            for bind in check.binds:
                if bind.item == seq and bind.level == level:
                    points.update(bind.points)
        return points

    def blocks_for_item(self, seq: int, level: int = 3) -> list[str]:
        titles: list[str] = []
        for check in self.checks:
            if check.kind != "judge":
                continue
            if any(bind.item == seq and bind.level == level for bind in check.binds):
                if check.title not in titles:
                    titles.append(check.title)
        return titles

    def mapped_items(self, level: int) -> set[int]:
        return {
            bind.item
            for check in self.checks
            if check.kind == "judge"
            for bind in check.binds
            if bind.level == level
        }

    def binding(self, block: CheckBlock) -> CheckBinding | None:
        candidates = [
            check
            for check in self.checks
            if check.title == block.title and (not check.section or check.section == block.section)
        ]
        if not candidates:
            return None
        if block.os_family:
            for check in candidates:
                if block.os_family in check.os_family:
                    return check
        return candidates[0]


def index_blocks(blocks: list[CheckBlock], checks: ChecksMap, os_family: str | None) -> dict[str, CheckBlock]:
    """按标题归并检查块：优先取与资产系统类型一致的会话。

    os_family 已知时，若该标题只存在于其它系统类型的会话（例如 Ubuntu 资产里的
    SELinux 块），直接不绑定，避免拿错证据。
    """
    index: dict[str, CheckBlock] = {}
    for title in checks.titles():
        candidates = [block for block in blocks if block.title == title]
        if not candidates:
            continue
        if os_family:
            preferred = [block for block in candidates if block.os_family == os_family]
            if not preferred:
                continue
            index[title] = preferred[0]
        else:
            index[title] = candidates[0]
    return index
