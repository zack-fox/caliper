"""结果记录表渲染：行数、表头块、自检。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import openpyxl

from core.contracts.policy import Policy
from core.contracts.verdict import Verdict
from core.items.loader import load_pack
from core.model.entities import (
    Asset,
    AssetRun,
    ItemResult,
    ProjectConfig,
    RunResult,
)
from core.render.result_record import render_result_workbook, verify_workbook

REPO = Path(__file__).resolve().parents[1]
PACK_DIR = REPO / "packs" / "linux_os"
TEMPLATE = REPO / "templates" / "result_record.xlsx"


def _run(level: int, output: Path) -> tuple[RunResult, list, Path]:
    pack = load_pack(PACK_DIR)
    items = pack.items_for_level(level)
    asset = Asset(
        device_name="示例服务器",
        ip="192.0.2.11",
        importance="一般",
        guide="三级-安全通用要求",
    )
    project = ProjectConfig(
        project_code="示例-001",
        system_name="示例系统A",
        level=level,
        check_date=date(2026, 11, 21),
        assets=[asset],
    )
    results = []
    for item in items:
        if item.policy is Policy.NA:
            results.append(
                ItemResult(
                    item_id=item.item_id,
                    seq=item.seq,
                    control_point=item.control_point,
                    importance=item.importance,
                    verdict=Verdict.NOT_APPLICABLE,
                    result_text="默认不适用",
                )
            )
        else:
            results.append(
                ItemResult(
                    item_id=item.item_id,
                    seq=item.seq,
                    control_point=item.control_point,
                    importance=item.importance,
                    verdict=Verdict.UNCOLLECTED,
                    note="未采集：测试",
                )
            )
    run = AssetRun(asset=asset, package_id="pkg-test", items=results)
    result = RunResult(project=project, asset_runs=[run])
    target = render_result_workbook(result, items, TEMPLATE, output)
    return result, items, target


def test_render_level3_rows_and_header(tmp_path: Path) -> None:
    _result, items, target = _run(3, tmp_path)
    assert verify_workbook(target, 3, items) == []
    ws = openpyxl.load_workbook(target).worksheets[0]
    assert ws.title == "示例服务器-三级-安全通用要求"
    assert ws["C2"].value == "示例-001"
    assert ws["F3"].value == "安全计算环境"
    assert ws["C4"].value == "192.0.2.11"
    assert ws.max_row == 42
    assert ws["A9"].value == "1"
    assert ws["E9"].value is None
    assert ws["E27"].value == "不适用"


def test_render_level2_has_23_rows(tmp_path: Path) -> None:
    _result, items, target = _run(2, tmp_path)
    assert verify_workbook(target, 2, items) == []
    ws = openpyxl.load_workbook(target).worksheets[0]
    assert ws.max_row == 31
    assert ws["A31"].value == "23"
