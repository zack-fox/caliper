"""安全问题汇总：不符合 / 部分符合 → 25 列行 → 母版渲染。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from core.contracts.columns import ISSUE_COLUMNS
from core.contracts.filenames import issue_filename
from core.contracts.verdict import Verdict
from core.model.entities import Item, ProjectConfig, RunResult
from core.render.result_record import RenderError, estimate_height, find_template

SECURITY_REQUIREMENT = "安全通用要求"
SECURITY_LAYER = "安全计算环境"
_THIN = Side(style="thin")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


@dataclass(frozen=True)
class IssueRow:
    seq: int
    item_id: str
    asset_type: str
    issue_no: str
    values: dict[str, str]


class TextLibrary:
    """控制项文案库：只做精确/归一化匹配，匹配不到留空。"""

    def __init__(self, entries: list[dict]) -> None:
        self._index: dict[str, dict] = {}
        for entry in entries:
            text = _normalize(str(entry.get("control_item", "")))
            if text and text not in self._index:
                self._index[text] = entry

    def lookup(self, control_item: str) -> dict:
        return self._index.get(_normalize(control_item), {})


def _normalize(text: str) -> str:
    return (
        text.replace("；", ";")
        .replace("，", ",")
        .replace("（", "(")
        .replace("）", ")")
        .replace(" ", "")
        .replace("\u3000", "")
        .strip()
        .rstrip(";")
    )


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def build_issue_rows(
    run_result: RunResult,
    items: list[Item],
    library: TextLibrary,
    major_confirmed: set[tuple[str, str]] | None = None,
) -> list[IssueRow]:
    confirmed = major_confirmed or set()
    buckets: dict[tuple[int, str], dict] = {}
    order: list[tuple[int, str]] = []
    numbers: dict[int, str] = {}

    for item in sorted(items, key=lambda entry: entry.seq):
        for run in run_result.asset_runs:
            result = run.item_by_seq(item.seq)
            if result is None or result.verdict not in {
                Verdict.PARTIAL,
                Verdict.NON_COMPLIANT,
            }:
                continue
            asset_type = run.asset.asset_type.value
            key = (item.seq, asset_type)
            if key not in buckets:
                buckets[key] = {"assets": [], "zones": [], "reasons": []}
                order.append(key)
                numbers.setdefault(
                    item.seq, f"T{len(numbers) + 1:03d}"
                )
            bucket = buckets[key]
            bucket["assets"].append(run.asset.device_name)
            if run.asset.zone:
                bucket["zones"].append(run.asset.zone)
            bucket["reasons"].extend(
                point.reason for point in result.points if not point.passed
            )

    by_seq = {item.seq: item for item in items}
    rows: list[IssueRow] = []
    for key in order:
        item = by_seq[key[0]]
        bucket = buckets[key]
        text = library.lookup(item.control_item)
        reasons = _unique(bucket["reasons"])
        detail = str(text.get("issue_detail", "")).strip()
        if detail.startswith("="):
            detail = ""
        summary = str(text.get("issue_summary", "")).strip() or (reasons[0] if reasons else "")

        values = {column: "" for column in ISSUE_COLUMNS}
        values.update(
            {
                "问题编号": numbers[item.seq],
                "安全要求": SECURITY_REQUIREMENT,
                "安全层面": SECURITY_LAYER,
                "安全控制点": item.control_point,
                "测评项": item.control_item,
                "资产类型": key[1],
                "关联资产": "、".join(_unique(bucket["assets"])),
                "问题概述": summary,
                "问题详述": detail or "；".join(reasons),
                "危害分析": str(text.get("hazard", "")).strip(),
                "整改建议": str(text.get("remediation", "")).strip(),
                "关联威胁": str(text.get("threat", "")).strip(),
                "原始风险": str(text.get("inherent_risk", "")).strip(),
                "整改状态": "未整改",
                "影响的网络区域": "、".join(_unique(bucket["zones"])),
                "是否符合重大判定原则": (
                    "符合" if (item.item_id, key[1]) in confirmed else ""
                ),
            }
        )
        rows.append(IssueRow(item.seq, item.item_id, key[1], numbers[item.seq], values))
    return rows


def _style(cell) -> None:
    cell.font = Font(size=11)
    cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    cell.border = _BORDER


def _header(ws: Worksheet) -> tuple[str, ...]:
    return tuple(str(cell.value).strip() if cell.value is not None else "" for cell in ws[1])


def render_issue_workbook(
    rows: list[IssueRow],
    project: ProjectConfig,
    template: Path,
    output_dir: Path,
    moment: datetime | None = None,
) -> Path:
    workbook = openpyxl.load_workbook(template)
    ws = workbook.worksheets[0]
    if _header(ws) != ISSUE_COLUMNS:
        raise RenderError("问题汇总母版表头与 25 列契约不一致")

    widths = {get_column_letter(index): 20 for index in range(1, len(ISSUE_COLUMNS) + 1)}
    for offset, row in enumerate(rows, start=2):
        letters: dict[str, str] = {}
        for index, column in enumerate(ISSUE_COLUMNS, start=1):
            letter = get_column_letter(index)
            value = row.values[column]
            cell = ws.cell(row=offset, column=index, value=value or None)
            _style(cell)
            letters[letter] = value
        ws.row_dimensions[offset].height = estimate_height(letters, widths)

    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / issue_filename(
        project.project_code, project.system_name, moment or datetime.now()
    )
    workbook.save(target)
    return target


def verify_issue_workbook(path: Path, expected: int) -> list[str]:
    workbook = openpyxl.load_workbook(path)
    ws = workbook.worksheets[0]
    problems: list[str] = []
    if _header(ws) != ISSUE_COLUMNS:
        problems.append("表头与 25 列契约不一致")
    count = sum(
        1 for row in range(2, ws.max_row + 1) if any(_cell_text(ws, row, column) for column in range(1, 26))
    )
    if count != expected:
        problems.append(f"数据行应为 {expected}，实际 {count}")
    for offset in range(expected):
        value = _cell_text(ws, 2 + offset, 1)
        if value != f"T{offset + 1:03d}":
            problems.append(f"第 {offset + 1} 行问题编号应为 T{offset + 1:03d}，实际 {value!r}")
            break
    return problems


def _cell_text(ws: Worksheet, row: int, column: int) -> str:
    value = ws.cell(row=row, column=column).value
    return "" if value is None else str(value).strip()
