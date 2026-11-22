"""pack 装载：items / 检查块映射 / 规则库 / 高风险 / 文案库。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

from core.checks.mapping import ChecksMap
from core.major.major import MajorError, MajorLibrary, load_major_library
from core.major.risk import HighRiskError, load_high_risk
from core.model.entities import Item, ManualPoint
from core.remediation import RemediationError, RemediationLibrary
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
    major: str = "major.yaml"
    texts: str = "texts/library.yaml"
    # 设备规则域：同一套测评项下按厂商拆分的采集适配器；空表示不使用适配器。
    adapters: dict[str, str] = Field(default_factory=dict)
    default_adapter: str = ""


class AdapterMeta(BaseModel):
    """一个设备厂商适配器：只描述自己的采集命令、判定规则与文案，不共享厂商命令。"""

    name: str
    vendor: str = ""
    aliases: list[str] = Field(default_factory=list)
    levels: list[int] = Field(default_factory=list)
    asset_types: list[str] = Field(default_factory=list)
    # 无自动采集方案时整包转人工核查，例如尚无厂商指导书的通用安全设备。
    manual_all: bool = False
    checks_map: str = "checks_map.yaml"
    rules_dir: str = "rules"
    high_risk: str = "high_risk.yaml"
    major: str = "major.yaml"
    texts: str = "texts/library.yaml"
    capture: str = "capture.yaml"
    # 厂商特有的人工核查点：同一测评项在不同厂商下可验证的证据不同。
    manual_points: dict[int, list[ManualPoint]] = Field(default_factory=dict)
    # 测评项 seq 在不同等级会漂移时，按等级声明厂商特有人工核查点。
    manual_points_by_level: dict[int, dict[int, list[ManualPoint]]] = Field(
        default_factory=dict
    )

    @field_validator("levels")
    @classmethod
    def _check_levels(cls, value: list[int]) -> list[int]:
        invalid = sorted({level for level in value if level not in {2, 3, 4}})
        if invalid:
            raise ValueError(f"levels 只支持 2/3/4，实际 {invalid}")
        return sorted(set(value))


@dataclass
class Adapter:
    key: str
    root: Path
    meta: AdapterMeta
    checks: ChecksMap
    rules: RuleSet
    high_risk: list[dict] = field(default_factory=list)
    major: MajorLibrary | None = None
    texts: list[dict] = field(default_factory=list)
    remediation: RemediationLibrary | None = None

    @property
    def names(self) -> set[str]:
        values = {
            self.key,
            self.meta.name,
            self.meta.vendor,
            *self.meta.aliases,
        }
        return {value.strip().lower() for value in values if value and value.strip()}


@dataclass
class Pack:
    root: Path
    meta: PackMeta
    items: dict[int, list[Item]]
    checks: ChecksMap
    rules: RuleSet
    high_risk: list[dict] = field(default_factory=list)
    major: MajorLibrary | None = None
    texts: list[dict] = field(default_factory=list)
    adapters: dict[str, Adapter] = field(default_factory=dict)

    def items_for_level(self, level: int) -> list[Item]:
        try:
            return self.items[level]
        except KeyError as exc:
            raise PackError(f"{self.root}：没有 {level} 级 items") from exc

    def resolve_adapter(self, vendor: str) -> tuple[Adapter | None, bool]:
        """按资产厂商选择适配器；未匹配时回退默认适配器并返回 matched=False。"""
        if not self.adapters:
            return None, False
        text = (vendor or "").strip().lower()
        if text:
            for adapter in self.adapters.values():
                if text in adapter.names:
                    return adapter, True
        return self.adapters.get(self.meta.default_adapter), False

    def all_texts(self) -> list[dict]:
        """设备规则域内各适配器的文案；测评项文案与厂商无关时允许重复。"""
        entries: list[dict] = []
        for adapter in self.adapters.values():
            entries.extend(adapter.texts)
        return entries or self.texts

    def all_high_risk(self) -> list[dict]:
        """各适配器共享同一组风险规则，按 hr_id 去重，避免重复评估。"""
        records: list[dict] = []
        seen: set[str] = set()
        for adapter in self.adapters.values():
            for record in adapter.high_risk:
                key = str(record.get("hr_id") or record.get("id") or "")
                if key and key in seen:
                    continue
                if key:
                    seen.add(key)
                records.append(record)
        return records or self.high_risk

    def remediation_library(self, adapter_key: str = "") -> RemediationLibrary | None:
        """优先使用资产实际适配器的整改建议，避免把其他厂商命令带进报告。"""
        adapter = self.adapters.get(adapter_key)
        if adapter is not None and adapter.remediation is not None:
            return adapter.remediation
        return None

    def major_library(self) -> MajorLibrary | None:
        if self.major is not None:
            return self.major
        for adapter in self.adapters.values():
            if adapter.major is not None:
                return adapter.major
        return None

    def rule_files(self) -> list[Path]:
        """高风险/重大隐患规则文件清单，用于计算规则版本。"""
        if not self.adapters:
            return [self.root / self.meta.high_risk, self.root / self.meta.major]
        files: list[Path] = []
        for adapter in self.adapters.values():
            if adapter.meta.manual_all:
                continue
            files.extend(
                [adapter.root / adapter.meta.high_risk, adapter.root / adapter.meta.major]
            )
        return files


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


def _load_texts(path: Path) -> list[dict]:
    data = _load_yaml(path)
    if not isinstance(data, dict):
        raise PackError(f"{path}：文案库应为对象")
    return list(data.get("texts", []))


def _load_remediation(
    root: Path, items: dict[int, list[Item]]
) -> RemediationLibrary | None:
    if not (root / "remediation.yaml").is_file():
        return None
    all_items = [item for level_items in items.values() for item in level_items]
    try:
        return RemediationLibrary.load(root, all_items)
    except RemediationError as exc:
        raise PackError(str(exc)) from exc


def _load_adapter(
    pack_dir: Path,
    key: str,
    relative: str,
    items: dict[int, list[Item]],
    pack_levels: set[int],
) -> Adapter:
    root = pack_dir / relative
    try:
        meta = AdapterMeta.model_validate(_load_yaml(root / "adapter.yaml"))
    except ValidationError as exc:
        raise PackError(f"{root}/adapter.yaml：字段非法：{exc}") from exc
    levels = set(meta.levels) or pack_levels
    unknown = sorted(levels - pack_levels)
    if unknown:
        raise PackError(f"{root}/adapter.yaml：规则包没有 {unknown} 级 items")
    if meta.manual_all:
        return Adapter(
            key=key,
            root=root,
            meta=meta,
            checks=ChecksMap(checks=[]),
            rules=RuleSet(rules=[]),
            texts=_load_texts(root / meta.texts)
            if (root / meta.texts).is_file()
            else [],
            remediation=_load_remediation(root, items),
        )

    checks = ChecksMap.load(root / meta.checks_map)
    rules = RuleSet.load(root / meta.rules_dir, items)
    try:
        high_risk = load_high_risk(root / meta.high_risk)
        major = load_major_library(root / meta.major)
    except (HighRiskError, MajorError) as exc:
        raise PackError(str(exc)) from exc
    remediation = _load_remediation(root, items)
    return Adapter(
        key=key,
        root=root,
        meta=meta,
        checks=checks,
        rules=rules,
        high_risk=high_risk,
        major=major,
        texts=_load_texts(root / meta.texts),
        remediation=remediation,
    )


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

    adapters: dict[str, Adapter] = {}
    for key, relative in meta.adapters.items():
        if key in adapters:
            raise PackError(f"{pack_dir}/pack.yaml：适配器 {key} 重复")
        adapters[key] = _load_adapter(
            pack_dir, key, relative, items, set(items)
        )

    if adapters:
        if not meta.default_adapter or meta.default_adapter not in adapters:
            raise PackError(
                f"{pack_dir}/pack.yaml：使用适配器时必须指定 default_adapter，"
                f"且必须是 {sorted(adapters)} 之一"
            )
        default = adapters[meta.default_adapter]
        return Pack(
            root=pack_dir,
            meta=meta,
            items=items,
            checks=default.checks,
            rules=default.rules,
            high_risk=default.high_risk,
            major=default.major,
            texts=default.texts,
            adapters=adapters,
        )

    checks = ChecksMap.load(pack_dir / meta.checks_map)
    rules = RuleSet.load(pack_dir / meta.rules_dir, items)
    try:
        high_risk_records = load_high_risk(pack_dir / meta.high_risk)
        major = load_major_library(pack_dir / meta.major)
    except (HighRiskError, MajorError) as exc:
        raise PackError(str(exc)) from exc
    return Pack(
        root=pack_dir,
        meta=meta,
        items=items,
        checks=checks,
        rules=rules,
        high_risk=high_risk_records,
        major=major,
        texts=_load_texts(pack_dir / meta.texts),
    )
