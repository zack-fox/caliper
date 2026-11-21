"""pack 装载：items / 检查块映射 / 规则库 / 高风险 / 文案库。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

from core.checks.mapping import ChecksMap
from core.model.entities import Item
from core.rules.engine import RuleSet


class PackError(Exception):
    """pack 内容不可用。"""


class PackMeta(BaseModel):
    name: str
    version: str
    levels: list[int]
    os_family: list[str]
    asset_types: list[str]
    guides: list[str]
    items: dict[str, str]
    rules_dir: str = "rules"
    checks_map: str = "checks_map.yaml"
    high_risk: str = "high_risk.yaml"
    texts: str = "texts/library.yaml"


@dataclass
class Pack:
    root: Path
    meta: PackMeta
    items: dict[int, list[Item]]
    checks: ChecksMap
    rules: RuleSet
    high_risk: list[dict] = field(default_factory=list)
    texts: list[dict] = field(default_factory=list)

    def items_for_level(self, level: int) -> list[Item]:
        try:
            return self.items[level]
        except KeyError as exc:
            raise PackError(f"{self.root}：没有 {level} 级 items") from exc


def _load_yaml(path: Path) -> object:
    if not path.exists():
        raise PackError(f"缺少文件：{path}")
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _load_items(path: Path) -> list[Item]:
    data = _load_yaml(path)
    if not isinstance(data, list) or not data:
        raise PackError(f"{path}：items 应为非空列表")
    try:
        items = [Item.model_validate(record) for record in data]
    except ValidationError as exc:
        raise PackError(f"{path}：items 字段非法：{exc}") from exc
    seqs = [item.seq for item in items]
    if seqs != list(range(1, len(items) + 1)):
        raise PackError(f"{path}：seq 必须从 1 连续编号")
    return items


def load_pack(pack_dir: Path) -> Pack:
    pack_dir = Path(pack_dir)
    meta_data = _load_yaml(pack_dir / "pack.yaml")
    try:
        meta = PackMeta.model_validate(meta_data)
    except ValidationError as exc:
        raise PackError(f"{pack_dir}/pack.yaml：字段非法：{exc}") from exc

    items: dict[int, list[Item]] = {}
    for level_key, filename in meta.items.items():
        level = int(level_key.replace("level_", ""))
        items[level] = _load_items(pack_dir / filename)

    checks = ChecksMap.load(pack_dir / meta.checks_map)
    rules = RuleSet.load(pack_dir / meta.rules_dir, items)

    high_risk = _load_yaml(pack_dir / meta.high_risk)
    texts = _load_yaml(pack_dir / meta.texts)
    return Pack(
        root=pack_dir,
        meta=meta,
        items=items,
        checks=checks,
        rules=rules,
        high_risk=list(high_risk or []),
        texts=list((texts or {}).get("texts", [])),
    )
