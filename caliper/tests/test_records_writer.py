"""公司格式记录表写出：版式、字段、行数与多资产拆分。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import openpyxl

from core.contracts.enums import AssetType, Importance
from core.contracts.policy import Policy
from core.contracts.verdict import Verdict
from core.model.entities import Asset, AssetRun, Item, ItemResult, ProjectConfig, RunResult
from core.records import COLUMNS, write_record_book

PROFILE_TEXT = """\
version: 0.2.0
rules:
  - id: REC-01
    match: 符合
    text: 符合(1分)
  - id: REC-02
    match: 部分符合
    text: 不符合(0分)
  - id: REC-03
    match: 不符合
    text: 不符合(0分)
  - id: REC-04
    match: 不适用
    text: 不适用
  - id: REC-05
    match: 未采集
    text: ""
"""

HEADER_LABELS = {
    "B2": ("项目编号：", "示例-2026-001"),
    "E2": ("系统名称：", "示例系统A"),
    "B3": ("核查对象：", "示例服务器1"),
    "E3": ("安全层面/安全类：", "安全计算环境"),
    "B4": ("IP地址：", "192.0.2.10"),
    "E4": ("资产类别：", "服务器"),
    "B5": ("核查时间：", "2026-11-21"),
    "E5": ("测评作业指导书：", "三级服务器_存储设备"),
}


def _pack(tmp_path: Path) -> Path:
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "record.yaml").write_text(PROFILE_TEXT, encoding="utf-8")
    return pack


def _item(seq: int) -> Item:
    return Item(
        item_id=f"L3-CES-{seq:03d}",
        level=3,
        seq=seq,
        unit_no=1,
        control_point="身份鉴别",
        control_item="应对登录的用户进行身份标识和鉴别",
        importance="一般",
        check_content="检查是否存在空口令账户",
        criteria="不存在空口令账户",
        policy=Policy.ALL_POSITIVE,
        mode="auto",
        binary=False,
    )


def _result(seq: int, verdict: Verdict, **kwargs) -> ItemResult:
    return ItemResult(
        item_id=f"L3-CES-{seq:03d}",
        seq=seq,
        control_point="身份鉴别",
        importance="一般",
        verdict=verdict,
        **kwargs,
    )


def _asset(name: str = "示例服务器1", ip: str = "192.0.2.10") -> Asset:
    return Asset(
        device_name=name,
        ip=ip,
        importance=Importance.NORMAL,
        guide="三级服务器_存储设备",
        asset_type=AssetType.SERVER,
    )


def _results() -> list[ItemResult]:
    return [
        _result(1, Verdict.COMPLIANT, result_text="1) 口令复杂度满足要求"),
        _result(2, Verdict.PARTIAL, result_text="2) 部分配置缺失"),
        _result(3, Verdict.NON_COMPLIANT, result_text="3) 未启用登录失败处理"),
        _result(4, Verdict.NOT_APPLICABLE, note="采用堡垒机代理，不适用"),
        _result(5, Verdict.UNCOLLECTED, note="未采集：未找到可核查证据块「A」"),
    ]


def _project(pack: Path, assets: list[Asset]) -> ProjectConfig:
    return ProjectConfig(
        project_code="示例-2026-001",
        system_name="示例系统A",
        level=3,
        check_date=date(2026, 11, 21),
        pack_dir=pack,
        output_dir=Path("out"),
        assets=assets,
    )


def _write(tmp_path: Path, assets: list[Asset]) -> tuple[Path, ProjectConfig]:
    pack = _pack(tmp_path)
    project = _project(pack, assets)
    items = [_item(seq) for seq in range(1, 6)]
    run_result = RunResult(
        project=project,
        asset_runs=[AssetRun(asset=asset, items=_results()) for asset in assets],
    )
    target = write_record_book(project, run_result, {3: items}, tmp_path / "out")
    return target, project


def test_workbook_layout_and_fields(tmp_path: Path) -> None:
    target, project = _write(tmp_path, [_asset()])

    assert target.name == "示例-2026-001_结果记录表.xlsx"
    workbook = openpyxl.load_workbook(target)
    assert workbook.sheetnames == ["示例服务器1"]
    ws = workbook["示例服务器1"]

    # 8 个表头字段：标签与取值均在固定单元格
    for address, (label, value) in HEADER_LABELS.items():
        assert ws[address].value == label
    assert ws["C2"].value == "示例-2026-001"
    assert ws["F2"].value == "示例系统A"
    assert ws["C3"].value == "示例服务器1"
    assert ws["F3"].value == "安全计算环境"
    assert ws["C4"].value == "192.0.2.10"
    assert ws["F4"].value == "服务器"
    assert ws["C5"].value == "2026-11-21"
    assert ws["F5"].value == "三级服务器_存储设备"

    # 9 个列头逐字一致，安全层面小标题在数据区上方
    assert tuple(ws.cell(7, index).value for index in range(1, 10)) == COLUMNS
    assert ws["A8"].value == "安全通用要求"

    # 标题行 + 表头区 + 列头 + 小标题 + 5 条数据
    assert ws.max_row == 8 + len(_results())
    assert len(ws.merged_cells.ranges) > 0
    for column in "ABCDEFGHI":
        assert ws.column_dimensions[column].width is not None

    allowed = {"符合(1分)", "不符合(0分)", "不适用", ""}
    for row in range(9, ws.max_row + 1):
        assert (ws[f"E{row}"].value or "") in allowed
        assert str(ws[f"D{row}"].value).startswith("经核查：")

    assert len(project.assets) == 1


def test_one_sheet_per_asset(tmp_path: Path) -> None:
    assets = [_asset("示例服务器1"), _asset("示例服务器2", "192.0.2.11")]
    target, project = _write(tmp_path, assets)

    workbook = openpyxl.load_workbook(target)
    assert len(workbook.sheetnames) == len(project.assets) == 2
    assert workbook.sheetnames == ["示例服务器1", "示例服务器2"]


def test_sheet_name_is_sanitized_and_deduplicated(tmp_path: Path) -> None:
    assets = [_asset("示例/服务器1"), _asset("示例/服务器1", "192.0.2.11")]
    target, _project_config = _write(tmp_path, assets)

    workbook = openpyxl.load_workbook(target)
    assert workbook.sheetnames == ["示例_服务器1", "示例_服务器1~2"]
