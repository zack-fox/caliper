"""结果记录表渲染：母版复制 → 填表头块与数据行 → 另存。"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path

import openpyxl
from openpyxl.worksheet.worksheet import Worksheet

from core.contracts.filenames import RESULT_FILENAME
from core.contracts.layout import (
    COLUMN_WIDTHS,
    DATA_START_ROW,
    LEVEL2_ROW_COUNT,
    LEVEL3_ROW_COUNT,
    SECTION_TITLE,
)
from core.contracts.verdict import Verdict, to_text
from core.model.entities import AssetRun, Item, ItemResult, ProjectConfig, RunResult
from core.traceability import standard_references

SHEET_TEMPLATE_TITLE = "模板"
SECURITY_LAYER = "安全计算环境"
_INVALID_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")
_FALLBACK_WIDTH = 8.43
DEFAULT_ROW_HEIGHT = 15.0
MAX_ROW_HEIGHT = 409.0


class RenderError(Exception):
    """渲染失败。"""


def find_template(pack_dir: Path, filename: str = "result_record.xlsx") -> Path:
    """按 pack 位置与源码位置寻找母版，找不到就报错。"""
    resource_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    candidates = [
        Path(pack_dir).parent.parent / "templates" / filename,
        resource_root / "templates" / filename,
        Path.cwd() / "templates" / filename,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise RenderError(f"未找到母版 {filename}，可用 --template 指定")


def sanitize_sheet_name(raw: str) -> str:
    name = _INVALID_SHEET_CHARS.sub("_", raw).strip() or "未命名"
    return name[:31]


def _display_width(text: str) -> int:
    return sum(2 if ord(char) > 127 else 1 for char in text)


def estimate_height(values: dict[str, str], widths: dict[str, float], line_height: float = 15.0) -> float:
    """按列宽估算换行后的行高，避免 Excel 打开时内容被截断。"""
    max_lines = 1
    for column, text in values.items():
        if not text:
            continue
        width = widths.get(column, _FALLBACK_WIDTH)
        per_line = max(int(width) - 2, 4)
        lines = 0
        for paragraph in str(text).splitlines() or [""]:
            lines += max(1, math.ceil(_display_width(paragraph) / per_line))
        max_lines = max(max_lines, lines)
    return min(MAX_ROW_HEIGHT, max(20.0, max_lines * line_height + 6))


def _fill_header(ws: Worksheet, project: ProjectConfig, run: AssetRun) -> None:
    asset = run.asset
    values = {
        "C2": project.project_code,
        "F2": project.system_name,
        "C3": asset.device_name,
        "F3": SECURITY_LAYER,
        "C4": asset.ip,
        "F4": asset.asset_type.value,
        "C5": project.check_date.isoformat(),
        "F5": asset.guide,
    }
    for address, value in values.items():
        ws[address] = value


def _trim_to_level(ws: Worksheet, level: int) -> None:
    expected = LEVEL3_ROW_COUNT if level == 3 else LEVEL2_ROW_COUNT
    if expected not in {LEVEL3_ROW_COUNT, LEVEL2_ROW_COUNT}:
        raise RenderError(f"不支持的等级：{level}")
    last_row = DATA_START_ROW + expected - 1
    if ws.max_row > last_row:
        ws.delete_rows(last_row + 1, ws.max_row - last_row)
    for row in range(DATA_START_ROW, last_row + 1):
        ws.row_dimensions[row].height = None


def _sorted_items(items: list[Item]) -> list[Item]:
    return sorted(items, key=lambda item: item.seq)


def _record_text(item: Item, result: ItemResult) -> str:
    text = result.result_text
    rule_refs = list(
        dict.fromkeys(
            reference
            for point in result.points
            for reference in point.rule_refs
        )
    )
    if not rule_refs:
        return text
    trace = (
        "机器建议依据（供人工复核）："
        + "；".join(standard_references(item))
        + "\n规则引用："
        + "、".join(rule_refs)
    )
    return f"{text}\n{trace}" if text else trace


def _fill_rows(ws: Worksheet, items: list[Item], run: AssetRun) -> None:
    widths = dict(COLUMN_WIDTHS)
    widths["H"] = ws.column_dimensions["H"].width or _FALLBACK_WIDTH
    widths["I"] = ws.column_dimensions["I"].width or _FALLBACK_WIDTH

    for offset, item in enumerate(_sorted_items(items)):
        row = DATA_START_ROW + offset
        result = run.item_by_seq(item.seq)
        if result is None:
            raise RenderError(f"{run.asset.device_name}：缺少 item {item.seq} 的判定结果")
        verdict_text = to_text(result.verdict) if result.verdict is not Verdict.UNCOLLECTED else None
        note = result.note
        values = {
            "A": str(item.seq),
            "B": item.control_point,
            "C": item.control_item,
            "D": _record_text(item, result) or None,
            "E": verdict_text,
            "F": note or None,
            "G": item.importance,
            "H": item.check_content,
            "I": item.criteria,
        }
        for column, value in values.items():
            ws[f"{column}{row}"] = value
        ws.row_dimensions[row].height = estimate_height(
            {column: str(value) for column, value in values.items() if value}, widths
        )


def render_result_workbook(
    run_result: RunResult,
    items: list[Item],
    template: Path,
    output_dir: Path,
) -> Path:
    if not Path(template).exists():
        raise RenderError(f"缺少结果记录表母版：{template}")
    if not run_result.asset_runs:
        raise RenderError("没有可导出的资产判定结果")

    workbook = openpyxl.load_workbook(template)
    if SHEET_TEMPLATE_TITLE in workbook.sheetnames:
        base_sheet = workbook[SHEET_TEMPLATE_TITLE]
    else:
        base_sheet = workbook.worksheets[0]

    used_names: set[str] = set()
    for index, run in enumerate(run_result.asset_runs):
        sheet_name = sanitize_sheet_name(f"{run.asset.device_name}-{run.asset.guide}")
        unique = sheet_name
        counter = 2
        while unique in used_names:
            suffix = f"~{counter}"
            unique = sheet_name[: 31 - len(suffix)] + suffix
            counter += 1
        used_names.add(unique)

        if index == 0:
            ws = base_sheet
        else:
            ws = workbook.copy_worksheet(base_sheet)
        ws.title = unique
        _fill_header(ws, run_result.project, run)
        _trim_to_level(ws, run_result.project.level)
        _fill_rows(ws, items, run)

    for name in list(workbook.sheetnames):
        if name not in used_names:
            del workbook[name]

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / RESULT_FILENAME
    workbook.save(target)
    return target


def verify_workbook(path: Path, level: int, items: list[Item]) -> list[str]:
    """导出后自检：行数、序号、五值文本、列宽。返回问题列表，空表示通过。"""
    problems: list[str] = []
    workbook = openpyxl.load_workbook(path)
    allowed = {to_text(Verdict.COMPLIANT), to_text(Verdict.PARTIAL), to_text(Verdict.NON_COMPLIANT), "不适用", None, ""}
    expected_rows = LEVEL3_ROW_COUNT if level == 3 else LEVEL2_ROW_COUNT
    for ws in workbook.worksheets:
        if ws.max_row != DATA_START_ROW + expected_rows - 1:
            problems.append(f"{ws.title}：数据行数应为 {expected_rows}，实际 {ws.max_row - DATA_START_ROW + 1}")
        for offset, item in enumerate(_sorted_items(items)):
            row = DATA_START_ROW + offset
            if str(ws[f"A{row}"].value) != str(item.seq):
                problems.append(f"{ws.title}：第 {row} 行序号应为 {item.seq}")
            if ws[f"E{row}"].value not in allowed:
                problems.append(f"{ws.title}：第 {row} 行符合情况非法：{ws[f'E{row}'].value!r}")
        for column, width in COLUMN_WIDTHS.items():
            actual = ws.column_dimensions[column].width
            if actual is None or abs(actual - width) > 0.01:
                problems.append(f"{ws.title}：{column} 列宽被改动")
        if ws["A8"].value != SECTION_TITLE:
            problems.append(f"{ws.title}：A8 文本应为 {SECTION_TITLE}")
    return problems
