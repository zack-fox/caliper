"""重大安全隐患：问题汇总 + 高风险规则 → 人工确认后入表（19 列）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from core.contracts.columns import MAJOR_COLUMNS
from core.contracts.filenames import major_filename
from core.issues.summary import IssueRow
from core.model.entities import ProjectConfig
from core.render.result_record import RenderError, estimate_height

_THIN = Side(style="thin")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


@dataclass(frozen=True)
class MajorRow:
    seq: int
    asset_type: str
    values: dict[str, str]


def triggers_for(seq: int, level: int, high_risk: list[dict]) -> list[dict]:
    """返回该测评项在当前等级会触发的高风险条目（不含四级）。"""
    matched: list[dict] = []
    for entry in high_risk:
        if int(entry.get("level_min", 99)) > level:
            continue
        if seq in entry.get("binds_items", []):
            matched.append(entry)
    return matched


def build_major_rows(
    issue_rows: list[IssueRow],
    high_risk: list[dict],
    level: int,
    confirmed: set[tuple[str, str]],
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
        rows.append(MajorRow(issue.seq, issue.asset_type, values))
    return rows


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
