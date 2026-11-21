"""金标准逐格回归（P12）。

用例目录结构：

```
fixtures/golden/<用例>/
    project.yaml      项目配置，证据路径按该文件所在目录解析
    assets.xlsx       可选：人工资产记录表原表
    expected/         期望表，文件名固定为 result/asset/issue/major.xlsx
```

期望表含项目与资产信息，按红线不入库；首次在新的现场机器上运行前，
先用 ``caliper golden --update`` 以当前输出生成期望表。
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from openpyxl import load_workbook

from core.issues.summary import TextLibrary, build_issue_rows, render_issue_workbook
from core.items.loader import PackError, load_pack
from core.judge.runner import RunError, run_project
from core.major.risk import build_major_rows, render_major_workbook
from core.render.asset_record import AssetRecordError, fill_asset_workbook
from core.render.result_record import RenderError, find_template, render_result_workbook
from core.rules.dsl import RuleError
from core.rules.engine import RulesError
from core.store.project import ProjectStoreError, load_project

TABLES = ("result", "asset", "issue", "major")

TABLE_PATTERNS = {
    "result": "*结果记录表*.xlsx",
    "asset": "*资产记录表*.xlsx",
    "issue": "*安全问题汇总*.xlsx",
    "major": "*重大安全隐患*.xlsx",
}


class GoldenError(Exception):
    """用例无法执行或工作簿无法读取。"""


@dataclass(frozen=True)
class GoldenCase:
    name: str
    project: Path
    assets: Path | None
    expected_dir: Path


def discover_cases(root: Path) -> list[GoldenCase]:
    """扫描用例目录；没有 project.yaml 的子目录跳过。"""
    root = Path(root)
    if not root.is_dir():
        return []
    cases: list[GoldenCase] = []
    for case_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        project = case_dir / "project.yaml"
        if not project.is_file():
            continue
        assets = case_dir / "assets.xlsx"
        cases.append(
            GoldenCase(
                name=case_dir.name,
                project=project,
                assets=assets if assets.is_file() else None,
                expected_dir=case_dir / "expected",
            )
        )
    return cases


def compare_workbooks(actual: Path, expected: Path, limit: int = 50) -> list[str]:
    """逐单元格比对两个工作簿，返回差异描述；空列表表示一致。"""
    try:
        actual_book = load_workbook(actual)
        expected_book = load_workbook(expected)
    except Exception as exc:  # openpyxl 抛出的异常类型较多，统一包装
        raise GoldenError(f"无法读取工作簿：{exc}") from exc

    diffs: list[str] = []
    if actual_book.sheetnames != expected_book.sheetnames:
        diffs.append(
            f"工作表：期望 {expected_book.sheetnames}，实际 {actual_book.sheetnames}"
        )

    for title in expected_book.sheetnames:
        if title not in actual_book.sheetnames:
            continue
        actual_sheet = actual_book[title]
        expected_sheet = expected_book[title]
        if (actual_sheet.max_row, actual_sheet.max_column) != (
            expected_sheet.max_row,
            expected_sheet.max_column,
        ):
            diffs.append(
                f"{title}：尺寸 期望 {expected_sheet.max_row}×{expected_sheet.max_column}，"
                f"实际 {actual_sheet.max_row}×{actual_sheet.max_column}"
            )
        rows = max(actual_sheet.max_row, expected_sheet.max_row)
        cols = max(actual_sheet.max_column, expected_sheet.max_column)
        for row in range(1, rows + 1):
            for column in range(1, cols + 1):
                actual_value = _normalize(actual_sheet.cell(row, column).value)
                expected_value = _normalize(expected_sheet.cell(row, column).value)
                if actual_value == expected_value:
                    continue
                coordinate = expected_sheet.cell(row, column).coordinate
                diffs.append(
                    f"{title}!{coordinate}：期望 {expected_value!r}，实际 {actual_value!r}"
                )
                if len(diffs) >= limit:
                    diffs.append(f"……差异超过 {limit} 处，已截断")
                    return diffs
    return diffs


def _normalize(value):
    """空字符串与空单元格视为同一状态。"""
    return None if value == "" else value


def run_case(case: GoldenCase, output_dir: Path) -> dict[str, Path]:
    """跑一个用例并把四张表渲染到 output_dir，返回表 → 文件路径。"""
    try:
        project, base = load_project(case.project)
    except ProjectStoreError as exc:
        raise GoldenError(f"{case.name}：{exc}") from exc
    pack_dir = project.pack_dir
    if pack_dir is None:
        raise GoldenError(f"{case.name}：项目未配置 pack_dir")
    if not pack_dir.is_absolute():
        pack_dir = base / pack_dir
    try:
        pack = load_pack(pack_dir)
    except (PackError, RulesError, RuleError) as exc:
        raise GoldenError(f"{case.name}：规则包装载失败：{exc}") from exc
    try:
        result = run_project(project, pack, base_dir=base)
    except RunError as exc:
        raise GoldenError(f"{case.name}：{exc}") from exc

    items = pack.items_for_level(project.level)
    generated: dict[str, Path] = {}
    try:
        generated["result"] = render_result_workbook(
            result, items, find_template(pack.root), output_dir
        )
        if case.assets is not None:
            report = fill_asset_workbook(
                case.assets, project.assets, pack.meta.guides, output_dir
            )
            if report.path is not None:
                generated["asset"] = report.path
        # 金标准只比对规则输出：人工备注与重大确认不参与，保证结果可复现
        issue_rows = build_issue_rows(result, items, TextLibrary(pack.texts))
        generated["issue"] = render_issue_workbook(
            issue_rows, project, find_template(pack.root, "issue_summary.xlsx"), output_dir
        )
        major_rows = build_major_rows(issue_rows, pack.high_risk, project.level, set())
        generated["major"] = render_major_workbook(
            major_rows, project, find_template(pack.root, "major_risk.xlsx"), output_dir
        )
    except (RenderError, AssetRecordError, OSError) as exc:
        raise GoldenError(f"{case.name}：渲染失败：{exc}") from exc
    return generated


def update_expected(case: GoldenCase, generated: dict[str, Path]) -> list[Path]:
    """用当前输出覆盖期望表；返回写入的文件。"""
    case.expected_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for table in TABLES:
        source = generated.get(table)
        if source is None:
            continue
        target = case.expected_dir / f"{table}.xlsx"
        shutil.copyfile(source, target)
        written.append(target)
    return written


def check_case(case: GoldenCase) -> list[str]:
    """跑用例并逐表比对；返回问题列表。"""
    problems: list[str] = []
    with TemporaryDirectory(prefix="caliper-golden-") as temp:
        generated = run_case(case, Path(temp))
        for table in TABLES:
            expected = case.expected_dir / f"{table}.xlsx"
            actual = generated.get(table)
            if not expected.is_file():
                problems.append(f"{case.name}/{table}：缺少期望表 {expected}")
                continue
            if actual is None:
                problems.append(f"{case.name}/{table}：本次未生成该表")
                continue
            problems.extend(
                f"{case.name}/{table}：{diff}"
                for diff in compare_workbooks(actual, expected)
            )
    return problems
