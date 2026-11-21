"""领域模型：项目、资产、检查块、判定结果。

跨模块传递的数据结构只在这里定义；渲染与界面不得自造字段。
"""

from __future__ import annotations

import ipaddress
from datetime import date, datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.contracts.enums import AssetType, Importance
from core.contracts.policy import Policy
from core.contracts.verdict import Verdict


class CheckStatus(str, Enum):
    """检查块状态。failed/skipped 一律按未采集处理。"""

    COLLECTED = "collected"
    EMPTY = "empty"
    FAILED = "failed"
    SKIPPED = "skipped"


class OutputLine(BaseModel):
    line: int
    text: str


class EvidenceAnchor(BaseModel):
    """证据锚点：文件 + 行号 + 原文片段。没有锚点的取值不得进入判定。"""

    file: str
    line: int
    snippet: str


class EvidenceFile(BaseModel):
    """证据包中的原始文件登记；附件也要可定位、可校验，但不自动参与判定。"""

    path: str
    kind: str
    size: int
    sha256: str
    analyzed: bool = False


class CheckBlock(BaseModel):
    session: int
    block_index: int
    section: str
    title: str
    os_family: str | None = None
    status: CheckStatus = CheckStatus.COLLECTED
    commands: list[str] = Field(default_factory=list)
    file_refs: list[str] = Field(default_factory=list)
    output: list[OutputLine] = Field(default_factory=list)
    source: str = ""

    @property
    def key(self) -> tuple[int, int]:
        return (self.session, self.block_index)

    @property
    def text_lines(self) -> list[str]:
        return [line.text for line in self.output]

    @property
    def text(self) -> str:
        return "\n".join(self.text_lines)

    def contains(self, needle: str) -> bool:
        return any(needle in line for line in self.text_lines)

    def anchors(self, limit: int = 3) -> list[EvidenceAnchor]:
        anchors = [
            EvidenceAnchor(file=self.source, line=line.line, snippet=line.text.strip())
            for line in self.output
        ]
        return anchors[:limit]

    def first_anchor(self, needle: str) -> EvidenceAnchor | None:
        for line in self.output:
            if needle in line.text:
                return EvidenceAnchor(file=self.source, line=line.line, snippet=line.text.strip())
        return None


class PackageManifest(BaseModel):
    package_id: str
    asset_id: str
    collected_at: datetime
    collector: str
    host: str
    os_family: str
    level: int
    files: dict[str, str] = Field(default_factory=dict)
    status: str = "ok"
    note: str = ""

    @field_validator("os_family")
    @classmethod
    def _check_os_family(cls, value: str) -> str:
        if value not in {"debian", "rhel"}:
            raise ValueError(f"os_family 只支持 debian/rhel，实际 {value!r}")
        return value

    @field_validator("level")
    @classmethod
    def _check_level(cls, value: int) -> int:
        if value not in {2, 3}:
            raise ValueError(f"level 只支持 2/3，实际 {value}")
        return value


class EvidencePackage(BaseModel):
    root: Path
    manifest: PackageManifest
    blocks: list[CheckBlock] = Field(default_factory=list)
    evidence_files: list[EvidenceFile] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)

    def block_by_title(self, title: str) -> CheckBlock | None:
        for block in self.blocks:
            if block.title == title:
                return block
        return None


class Asset(BaseModel):
    """资产记录表的一行（18 列口径）。"""

    model_config = ConfigDict(populate_by_name=True)

    device_name: str
    ip: str
    importance: Importance
    guide: str
    asset_type: AssetType = AssetType.SERVER
    is_virtual: str = ""
    business_system: str = ""
    os_version: str = ""
    db_version: str = ""
    middleware_version: str = ""
    count: str = ""
    hot_standby: str = ""
    zone: str = ""
    test_object: str = ""
    note: str = ""
    scan_object_type: str = ""
    row_color: str = ""
    scan_address: str = ""
    is_test_env: str = ""
    # 对应 fixtures/evidence 下的证据包目录名；为空表示该资产暂无采集证据
    evidence_package: str | None = None

    @field_validator("ip")
    @classmethod
    def _check_ip(cls, value: str) -> str:
        try:
            ipaddress.ip_address(value)
        except ValueError as exc:
            raise ValueError(f"IP 地址非法：{value!r}") from exc
        return value

    @field_validator("device_name", "guide")
    @classmethod
    def _check_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("设备名称与作业指导书必填")
        return value.strip()


class ProjectConfig(BaseModel):
    """项目配置。相对路径按项目文件所在目录解析。"""

    project_code: str = ""
    system_name: str = ""
    level: int = 3
    check_date: date
    evidence_root: Path = Path("fixtures/evidence")
    output_dir: Path = Path("out")
    # 由项目文件或命令行指定；core 不硬编码任何 pack 路径
    pack_dir: Path | None = None
    assets: list[Asset] = Field(default_factory=list)

    @field_validator("level")
    @classmethod
    def _check_level(cls, value: int) -> int:
        if value not in {2, 3}:
            raise ValueError(f"level 只支持 2/3，实际 {value}")
        return value

    def asset_by_device(self, device_name: str) -> Asset | None:
        for asset in self.assets:
            if asset.device_name == device_name:
                return asset
        return None


class Item(BaseModel):
    """pack 里的测评项，字段名与 items_*.yaml 的中文键对应。"""

    model_config = ConfigDict(populate_by_name=True)

    item_id: str
    level: int
    seq: int
    unit_no: int
    control_point: str = Field(alias="控制点")
    control_item: str = Field(alias="控制项")
    importance: str = Field(alias="重要程度")
    check_content: str = Field(alias="检查内容")
    criteria: str = Field(alias="判断标准")
    policy: Policy
    mode: str
    binary: bool
    optional_clause: bool = False

    @field_validator("mode")
    @classmethod
    def _check_mode(cls, value: str) -> str:
        if value not in {"auto", "manual", "na"}:
            raise ValueError(f"mode 只支持 auto/manual/na，实际 {value!r}")
        return value

    @field_validator("binary")
    @classmethod
    def _check_binary(cls, value: bool) -> bool:
        return value


class PointResult(BaseModel):
    point: int
    passed: bool | None
    reason: str
    block_title: str = ""
    anchors: list[EvidenceAnchor] = Field(default_factory=list)
    rule_refs: list[str] = Field(default_factory=list)


class ItemResult(BaseModel):
    item_id: str
    seq: int
    control_point: str
    importance: str
    verdict: Verdict
    note: str = ""
    result_text: str = ""
    points: list[PointResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    # Rules output is retained separately so a reviewer can restore it after an edit.
    auto_verdict: Verdict | None = None
    auto_result_text: str | None = None
    auto_note: str | None = None
    manual_override: bool = False
    override_reason: str = ""
    reviewed: bool = False
    reviewed_at: str = ""

    @property
    def verdict_text(self) -> str:
        from core.contracts.verdict import to_text

        return to_text(self.verdict)


class AssetRun(BaseModel):
    asset: Asset
    package_id: str | None = None
    os_family: str | None = None
    items: list[ItemResult] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)

    def item_by_seq(self, seq: int) -> ItemResult | None:
        for item in self.items:
            if item.seq == seq:
                return item
        return None


class RunResult(BaseModel):
    project: ProjectConfig
    asset_runs: list[AssetRun] = Field(default_factory=list)

    def verdict_counts(self) -> dict[str, int]:
        from core.contracts.verdict import to_text

        counts: dict[str, int] = {}
        for run in self.asset_runs:
            for item in run.items:
                label = to_text(item.verdict) or "空"
                counts[label] = counts.get(label, 0) + 1
        return counts
