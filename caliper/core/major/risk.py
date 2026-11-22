"""重大安全隐患：问题汇总 + 高风险规则 → 人工确认后入表（19 列）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import openpyxl
import yaml
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from core.contracts.columns import MAJOR_COLUMNS
from core.contracts.filenames import major_filename
from core.issues.summary import IssueRow
from core.model.entities import ProjectConfig
from core.render.result_record import RenderError, estimate_height

if TYPE_CHECKING:
    from core.major.major import MajorLibrary

_THIN = Side(style="thin")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


class HighRiskError(Exception):
    """高风险判例库不可用。"""


class HighRiskEntry(BaseModel):
    """高风险判例；可降风险与降风险前提只从原文提炼。"""

    model_config = ConfigDict(populate_by_name=True)

    hr_id: str
    level_min: int
    control_point: str = ""
    summary: str = Field(alias="问题简述")
    requirement: str = Field(alias="标准要求")
    scope: str = Field(alias="适用范围")
    description: str = Field(alias="问题描述")
    mitigation: str = Field(alias="缓解措施")
    risk: str = Field(alias="风险评价")
    remediation: str = Field(alias="整改建议")
    binds_items: list[int] = Field(default_factory=list)
    # 测评项 seq 随等级变化时，按等级精确绑定，避免跨等级串项。
    binds: dict[int, list[int]] = Field(default_factory=dict)
    reducible: bool = Field(alias="可降风险")
    reduction_basis: str = Field(default="", alias="降风险前提")

    @model_validator(mode="after")
    def _reduction_basis_required(self) -> "HighRiskEntry":
        if self.reducible and not self.reduction_basis.strip():
            raise ValueError("可降风险为 true 时必须给出降风险前提")
        return self

    @property
    def data(self) -> dict:
        return self.model_dump(by_alias=True)


def load_high_risk(path: Path) -> list[dict]:
    """读取并校验高风险判例库，返回保持中文字段的字典列表。"""
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise HighRiskError(f"{path}：无法读取高风险判例库：{exc}") from exc
    if not isinstance(raw, list) or not raw:
        raise HighRiskError(f"{path}：高风险判例应为非空列表")
    try:
        entries = [HighRiskEntry.model_validate(row) for row in raw]
    except ValidationError as exc:
        raise HighRiskError(f"{path}：高风险判例字段非法：{exc}") from exc
    return [entry.data for entry in entries]


def as_entry_dict(entry: dict | HighRiskEntry) -> dict:
    """兼容字典与模型两种高风险条目。"""
    if isinstance(entry, HighRiskEntry):
        return entry.data
    return dict(entry)


@dataclass(frozen=True)
class MajorRow:
    seq: int
    asset_type: str
    values: dict[str, str]


def triggers_for(
    seq: int, level: int, high_risk: list[dict] | list[HighRiskEntry]
) -> list[dict]:
    """返回该测评项在当前等级会触发的高风险条目（不含四级）。"""
    matched: list[dict] = []
    for raw in high_risk:
        entry = as_entry_dict(raw)
        if entry.get("binds"):
            bounds = entry["binds"].get(level, entry["binds"].get(str(level), []))
            if seq in bounds:
                matched.append(entry)
            continue
        if int(entry.get("level_min", 99)) > level:
            continue
        if seq in entry.get("binds_items", []):
            matched.append(entry)
    return matched


def build_major_rows(
    issue_rows: list[IssueRow],
    high_risk: list[dict] | list[HighRiskEntry],
    level: int,
    confirmed: set[tuple[str, str]],
    library: "MajorLibrary | None" = None,
) -> list[MajorRow]:
    rows: list[MajorRow] = []
    for issue in issue_rows:
        if (issue.item_id, issue.asset_type) not in confirmed:
            continue
        entries = triggers_for(issue.seq, level, high_risk)
        if not entries:
            continue
        trigger = "；".join(str(entry.get("问题简述", "")).strip() for entry in entries)
        remediation = "；".join(
            str(entry.get("整改建议", "")).strip() for entry in entries
        )
        values = {column: "" for column in MAJOR_COLUMNS}
        values.update(
            {
                "序号": str(len(rows) + 1),
                "安全要求": issue.values["安全要求"],
                "安全层面": issue.values["安全层面"],
                "安全控制点": issue.values["安全控制点"],
                "测评项": issue.values["测评项"],
                "资产类型": issue.values["资产类型"],
                "关联资产": issue.values["关联资产"],
                "问题概述": issue.values["问题概述"],
                "重大风险隐患触发项": trigger,
                "整改建议": remediation or issue.values["整改建议"],
                "是否整改": "未整改",
                "安全问题属性": "安全技术",
                "影响的网络区域": issue.values["影响的网络区域"],
            }
        )
        if library is not None:
            _fill_dimensions(values, entries, library)
        rows.append(MajorRow(issue.seq, issue.asset_type, values))
    return rows


def _fill_dimensions(values: dict[str, str], entries: list[dict], library) -> None:
    """把三维评分写入重大隐患表的维度列，理由保留原文提炼口径。"""
    from core.major.major import assess_major

    candidates = assess_major(entries, library)
    if not candidates:
        return
    best = max(candidates, key=lambda item: (item.is_candidate, item.total))
    for score in best.scores:
        values[score.name] = f"{score.score}（{score.reason}）"
    severity = next((item for item in best.scores if item.name == "严重性"), None)
    if severity is not None:
        values["后果分析"] = severity.reason
    verdict = "达到阈值，列为重大隐患候选" if best.is_candidate else "未达阈值，经人工确认后纳入"
    values["综合分析"] = (
        f"规则 {best.rule_id}（{'、'.join(best.hr_ids)}）加权总分 "
        f"{best.total:.2f}，阈值 {best.threshold:.2f}；{verdict}。"
    )
    if best.reducible and best.reduction_basis:
        values["综合分析"] += "可降风险前提：" + "；".join(best.reduction_basis)


def _header(ws: Worksheet) -> tuple[str, ...]:
    return tuple(str(cell.value).strip() if cell.value is not None else "" for cell in ws[1])


def _style(cell) -> None:
    cell.font = Font(size=11)
    cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    cell.border = _BORDER


def render_major_workbook(
    rows: list[MajorRow],
    project: ProjectConfig,
    template: Path,
    output_dir: Path,
    moment: datetime | None = None,
) -> Path:
    workbook = openpyxl.load_workbook(template)
    ws = workbook.worksheets[0]
    if _header(ws) != MAJOR_COLUMNS:
        raise RenderError("重大安全隐患母版表头与 19 列契约不一致")

    widths = {
        get_column_letter(index): (9.49 if index == 1 else 18.98)
        for index in range(1, len(MAJOR_COLUMNS) + 1)
    }
    for offset, row in enumerate(rows, start=2):
        letters: dict[str, str] = {}
        for index, column in enumerate(MAJOR_COLUMNS, start=1):
            letter = get_column_letter(index)
            value = row.values[column]
            _style(ws.cell(row=offset, column=index, value=value or None))
            letters[letter] = value
        ws.row_dimensions[offset].height = estimate_height(letters, widths)

    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / major_filename(
        project.project_code, project.system_name, moment or datetime.now()
    )
    workbook.save(target)
    return target


def verify_major_workbook(path: Path) -> list[str]:
    workbook = openpyxl.load_workbook(path)
    ws = workbook.worksheets[0]
    problems: list[str] = []
    if _header(ws) != MAJOR_COLUMNS:
        problems.append("表头与 19 列契约不一致")
    for row in range(2, ws.max_row + 1):
        if not any(ws.cell(row=row, column=column).value for column in range(1, 20)):
            continue
        if not ws.cell(row=row, column=9).value:
            problems.append(f"第 {row} 行缺少重大风险隐患触发项")
            break
    return problems
