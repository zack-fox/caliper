"""公司格式记录表写出：一个资产一张 sheet，版式对齐历史记录表样例。

数据只来自 RecordSheet，不在此处重新判定；符合情况文案由 pack 的
record.yaml 决定。写入规则：标题行 → 表头区 → 列头 → 安全层面小标题 → 数据行。
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.worksheet.worksheet import Worksheet

from core.contracts.layout import (
    HEADER_CELLS,
    HEADER_ROW,
    MERGED_RANGES,
    SECTION_ROW,
    SECTION_TITLE,
    DATA_START_ROW,
)
from core.model.entities import Item, ProjectConfig, RunResult
from core.records.model import COLUMNS, RecordSheet, build_sheet
from core.records.profile import RecordError, load_profile

# 标题行与表头区在样例中的落位；数据从第 9 行开始。
TITLE_ROW = 1
TITLE_TEXT = "网络安全等级保护现场核查结果记录表"
TITLE_MERGED = "A1:I1"
TITLE_HEIGHT = 28.0
HEADER_HEIGHT = 16.0
DEFAULT_ROW_HEIGHT = 15.0
MIN_DATA_HEIGHT = 24.0
MAX_ROW_HEIGHT = 409.0

# A-G 与结果记录表母版一致；H/I 取数据库样例中的窄列宽。
COLUMN_WIDTHS: dict[str, float] = {
    "A": 9.5,
    "B": 28.5,
    "C": 38.0,
    "D": 33.1640625,
    "E": 28.5,
    "F": 33.1640625,
    "G": 14.1640625,
    "H": 14.234375,
    "I": 14.234375,
}

_INVALID_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

_THIN = Side(style="thin", color="000000")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
_LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)


def write_record_book(
    project: ProjectConfig,
    run_result: RunResult,
    items_by_level: dict[int, list[Item]],
    out_dir: Path | None = None,
) -> Path:
    """把一次跑批结果写成公司格式记录表，返回生成文件路径。"""
    if not run_result.asset_runs:
        raise RecordError("没有可导出的资产判定结果")
    if project.pack_dir is None:
        raise RecordError("项目未配置 pack_dir，无法加载记录表规则库")

    items = items_by_level.get(project.level)
    if items is None:
        raise RecordError(f"缺少 {project.level} 级测评项，无法生成记录表")
    profile = load_profile(Path(project.pack_dir))

    workbook = openpyxl.Workbook()
    base = workbook.active
    used_names: set[str] = set()
    for index, run in enumerate(run_result.asset_runs):
        sheet = build_sheet(project, run, items, profile=profile)
        name = _unique_sheet_name(run.asset.device_name, used_names)
        ws = base if index == 0 else workbook.create_sheet()
        ws.title = name
        _write_sheet(ws, sheet)

    output_dir = Path(out_dir) if out_dir is not None else Path(project.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / _filename(project.project_code)
    workbook.save(target)
    return target


def _filename(project_code: str) -> str:
    code = _INVALID_FILENAME_CHARS.sub("_", project_code).strip()
    return f"{code or '记录表'}_结果记录表.xlsx"


def _unique_sheet_name(raw: str, used: set[str]) -> str:
    name = _INVALID_SHEET_CHARS.sub("_", raw).strip() or "未命名"
    name = name[:31]
    unique = name
    counter = 2
    while unique.casefold() in used:
        suffix = f"~{counter}"
        unique = name[: 31 - len(suffix)] + suffix
        counter += 1
    used.add(unique.casefold())
    return unique


def _write_sheet(ws: Worksheet, sheet: RecordSheet) -> None:
    ws.merge_cells(TITLE_MERGED)
    ws["A1"] = TITLE_TEXT
    ws["A1"].font = Font(name="Calibri", size=16, bold=True)
    ws["A1"].alignment = _CENTER
    ws.row_dimensions[TITLE_ROW].height = TITLE_HEIGHT

    for column, width in COLUMN_WIDTHS.items():
        ws.column_dimensions[column].width = width

    _write_header(ws, sheet)
    _write_column_heads(ws)
    _write_section(ws)
    _write_rows(ws, sheet)


def _write_header(ws: Worksheet, sheet: RecordSheet) -> None:
    header = sheet.header
    values = {
        "C2": header.project_code,
        "F2": header.system_name,
        "C3": header.asset_name,
        "F3": header.domain,
        "C4": header.ip,
        "F4": header.asset_type,
        "C5": header.check_date,
        "F5": header.guide,
    }
    for address, label in HEADER_CELLS:
        ws[address] = label
        ws[address].font = Font(name="Calibri", size=11, bold=True)
        ws[address].alignment = _CENTER
    for address, value in values.items():
        ws[address] = value
        ws[address].font = Font(name="Calibri", size=11)
        ws[address].alignment = _LEFT
    for row in range(2, 6):
        for column in "BCDEFG":
            cell = ws[f"{column}{row}"]
            cell.border = _BORDER
            if cell.alignment.horizontal is None:
                cell.alignment = _LEFT
        ws.row_dimensions[row].height = HEADER_HEIGHT
    for merged in MERGED_RANGES:
        if merged != "A8:I8":
            ws.merge_cells(merged)


def _write_column_heads(ws: Worksheet) -> None:
    for index, title in enumerate(COLUMNS, start=1):
        cell = ws.cell(HEADER_ROW, index, title)
        cell.font = Font(name="Calibri", size=11, bold=True)
        cell.alignment = _CENTER
        cell.border = _BORDER
    ws.row_dimensions[HEADER_ROW].height = HEADER_HEIGHT


def _write_section(ws: Worksheet) -> None:
    ws.merge_cells("A8:I8")
    cell = ws[f"A{SECTION_ROW}"]
    cell.value = SECTION_TITLE
    cell.font = Font(name="Calibri", size=11, bold=True)
    cell.alignment = _CENTER
    for column in "ABCDEFGHI":
        ws[f"{column}{SECTION_ROW}"].border = _BORDER


def _write_rows(ws: Worksheet, sheet: RecordSheet) -> None:
    for offset, row in enumerate(sheet.rows):
        row_index = DATA_START_ROW + offset
        values = row.values()
        for index, value in enumerate(values, start=1):
            cell = ws.cell(row_index, index, value)
            cell.font = Font(name="Calibri", size=11)
            cell.alignment = _CENTER if index in {1, 5, 7} else _LEFT
            cell.border = _BORDER
        widths = {column: COLUMN_WIDTHS[column] for column in COLUMN_WIDTHS}
        ws.row_dimensions[row_index].height = _estimate_height(
            dict(zip(COLUMN_WIDTHS, (str(value) for value in values), strict=False)),
            widths,
        )


def _display_width(text: str) -> int:
    return sum(2 if ord(char) > 127 else 1 for char in text)


def _estimate_height(values: dict[str, str], widths: dict[str, float]) -> float:
    """按列宽估算换行后的行高，避免记录内容被 Excel 截断。"""
    max_lines = 1
    for column, text in values.items():
        if not text:
            continue
        per_line = max(int(widths[column]) - 2, 4)
        lines = 0
        for paragraph in text.splitlines() or [""]:
            lines += max(1, math.ceil(_display_width(paragraph) / per_line))
        max_lines = max(max_lines, lines)
    return min(
        MAX_ROW_HEIGHT,
        max(MIN_DATA_HEIGHT, max_lines * DEFAULT_ROW_HEIGHT + 6),
    )
