"""checks_map.yaml：检查块 ↔ 测评项/实施点 的绑定关系。"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

from core.model.entities import CheckBlock


class CheckMapError(Exception):
    """检查块映射非法。"""


class PointBinding(BaseModel):
    item: int
    level: int = 3
    points: list[int] = Field(default_factory=list)


class SessionBinding(BaseModel):
    kind: str
    pattern: str
    empty: str = "failed"

    @field_validator("kind")
    @classmethod
    def _check_kind(cls, value: str) -> str:
        if value not in {"shell", "mysql", "network"}:
            raise ValueError("session.kind 只支持 shell/mysql/network")
        return value

    @field_validator("pattern")
    @classmethod
    def _check_pattern(cls, value: str) -> str:
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"session.pattern 正则非法：{exc}") from exc
        return value

    @field_validator("empty")
    @classmethod
    def _check_empty(cls, value: str) -> str:
        if value not in {"success", "failed"}:
            raise ValueError("session.empty 只支持 success/failed")
        return value


class CheckBinding(BaseModel):
    os_family: list[str] = Field(default_factory=list)
    section: str = ""
    title: str
    block_index: int
    kind: str = "judge"
    binds: list[PointBinding] = Field(default_factory=list)
    session: list[SessionBinding] = Field(default_factory=list)
    normalize: str = ""

    @field_validator("os_family")
    @classmethod
    def _check_families(cls, value: list[str]) -> list[str]:
        invalid = set(value) - {"debian", "rhel", "unknown"}
        if invalid:
            raise ValueError(f"os_family 含未知类型：{sorted(invalid)}")
        return value

    @field_validator("normalize")
    @classmethod
    def _check_normalize(cls, value: str) -> str:
        if value:
            from core.evidence.normalize import normalize_names

            if value not in normalize_names():
                raise ValueError(f"未知 normalize 标识：{value}")
        return value


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
            if any(check.os_family for check in candidates):
                return None
        return candidates[0]


def index_blocks(blocks: list[CheckBlock], checks: ChecksMap, os_family: str | None) -> dict[str, CheckBlock]:
    """按标题选择证据，并同时执行会话系统类型和映射白名单约束。"""
    index: dict[str, CheckBlock] = {}
    for title in checks.titles():
        candidates = [block for block in blocks if block.title == title]
        compatible: list[CheckBlock] = []
        for block in candidates:
            allowed = checks.allowed_families(title)
            if allowed and block.os_family and block.os_family not in allowed:
                continue
            if os_family and os_family != "unknown" and block.os_family:
                if block.os_family != os_family and block.os_family != "unknown":
                    continue
                if block.os_family == "unknown" and "unknown" not in allowed:
                    continue
            if os_family == "unknown" and block.os_family not in {None, "unknown"}:
                continue
            compatible.append(block)
        if compatible:
            index[title] = compatible[0]
    return index
