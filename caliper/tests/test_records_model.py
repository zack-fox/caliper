"""记录表模型、规则库口径与构建器。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from core.contracts.enums import AssetType, Importance
from core.contracts.policy import Policy
from core.contracts.verdict import Verdict
from core.model.entities import Asset, AssetRun, Item, ItemResult, ProjectConfig
from core.records import COLUMNS, RecordError, build_sheet, load_profile

PACK_DIR = Path(__file__).resolve().parents[1] / "packs" / "linux_os"

VALID_TEXT = """\
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


def _config(pack_dir: Path | None = PACK_DIR) -> ProjectConfig:
    return ProjectConfig(
        project_code="示例-2026-001",
        system_name="示例系统A",
        level=3,
        check_date=date(2026, 11, 21),
        pack_dir=pack_dir,
    )


def _asset(asset_type: AssetType = AssetType.SERVER) -> Asset:
    return Asset(
        device_name="示例服务器1",
        ip="192.0.2.10",
        importance=Importance.NORMAL,
        guide="三级服务器_存储设备",
        asset_type=asset_type,
    )


def _run(results: list[ItemResult], asset_type: AssetType = AssetType.SERVER) -> AssetRun:
    return AssetRun(asset=_asset(asset_type), items=results)


def _write_profile(tmp_path: Path, text: str) -> Path:
    (tmp_path / "record.yaml").write_text(text, encoding="utf-8")
    return tmp_path


def test_sheet_matches_company_columns() -> None:
    sheet = build_sheet(_config(), _run([_result(2, Verdict.COMPLIANT)]), [_item(1), _item(2)])
    assert COLUMNS == (
        "序号",
        "控制点",
        "控制项",
        "结果记录",
        "符合情况",
        "备注",
        "重要程度",
        "检查内容",
        "判断标准",
    )
    assert len(sheet.rows[0].values()) == len(COLUMNS)


def test_header_and_rows_follow_results() -> None:
    run = _run(
        [
            _result(3, Verdict.NON_COMPLIANT, note="需整改"),
            _result(1, Verdict.COMPLIANT, result_text="1) 口令复杂度满足要求"),
        ]
    )
    sheet = build_sheet(_config(), run, [_item(1), _item(2), _item(3)])
    assert [row.seq for row in sheet.rows] == [1, 3]
    assert sheet.header.asset_name == "示例服务器1"
    assert sheet.header.asset_type == "服务器"
    assert sheet.header.check_date == "2026-11-21"
    assert sheet.header.domain == "安全计算环境"
    first = sheet.row_by_seq(1)
    assert first.result_text == "经核查：1) 口令复杂度满足要求"
    assert first.criteria == "不存在空口令账户"
    # 备注只承载不适用/未采集理由，不符合的说明留在判定层
    assert sheet.row_by_seq(3).note == ""


def test_compliance_text_comes_from_record_yaml() -> None:
    profile = load_profile(PACK_DIR)
    assert profile.text(Verdict.COMPLIANT) == "符合(1分)"
    assert profile.text(Verdict.NON_COMPLIANT) == "不符合(0分)"
    assert profile.text(Verdict.PARTIAL) == "不符合(0分)"
    assert profile.text(Verdict.NOT_APPLICABLE) == "不适用"
    assert profile.text(Verdict.UNCOLLECTED) == ""


def test_profile_requires_at_least_five_rules(tmp_path: Path) -> None:
    pack = _write_profile(
        tmp_path,
        """\
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
""",
    )
    with pytest.raises(RecordError, match="至少 5 条"):
        load_profile(pack)


def test_profile_rejects_duplicate_match(tmp_path: Path) -> None:
    pack = _write_profile(tmp_path, VALID_TEXT.replace("match: 未采集", "match: 符合"))
    with pytest.raises(RecordError, match="符合 重复出现"):
        load_profile(pack)


def test_profile_rejects_duplicate_id(tmp_path: Path) -> None:
    pack = _write_profile(tmp_path, VALID_TEXT.replace("id: REC-05", "id: REC-01"))
    with pytest.raises(RecordError, match="id 重复"):
        load_profile(pack)


def test_profile_rejects_unknown_match(tmp_path: Path) -> None:
    pack = _write_profile(tmp_path, VALID_TEXT.replace("match: 未采集", "match: 未知"))
    with pytest.raises(RecordError, match="未登记"):
        load_profile(pack)


def test_profile_rejects_invalid_value(tmp_path: Path) -> None:
    pack = _write_profile(
        tmp_path,
        VALID_TEXT.replace("text: 符合(1分)", "text: 符合(0.5分)"),
    )
    with pytest.raises(RecordError, match="非法"):
        load_profile(pack)


def test_profile_requires_record_yaml(tmp_path: Path) -> None:
    with pytest.raises(RecordError, match="缺少记录表生成规则库"):
        load_profile(tmp_path)


def test_changed_mapping_flows_into_sheet(tmp_path: Path) -> None:
    """改一条 record.yaml 映射后，记录表符合情况应随之变化。"""
    pack = _write_profile(
        tmp_path,
        VALID_TEXT.replace(
            "    match: 部分符合\n    text: 不符合(0分)",
            "    match: 部分符合\n    text: 不适用",
        ),
    )
    profile = load_profile(pack)
    run = _run([_result(1, Verdict.PARTIAL)])
    sheet = build_sheet(_config(pack), run, [_item(1)], profile=profile)
    assert sheet.rows[0].compliance == "不适用"
    # 未显式传入 profile 时，默认从同一 pack 的 record.yaml 加载
    default_sheet = build_sheet(_config(pack), run, [_item(1)])
    assert default_sheet.rows[0].compliance == "不适用"


def test_uncollected_item_has_diagnostic_text() -> None:
    run = _run(
        [
            _result(
                1,
                Verdict.UNCOLLECTED,
                note="未采集：未找到可核查证据块「A」",
            )
        ]
    )
    sheet = build_sheet(_config(), run, [_item(1)])
    row = sheet.rows[0]
    assert row.compliance == ""
    assert row.note.startswith("未采集：")
    assert row.result_text == "经核查：未采集：未找到可核查证据块「A」"


def test_item_without_points_still_has_result_text() -> None:
    run = _run([_result(1, Verdict.COMPLIANT)])
    sheet = build_sheet(_config(), run, [_item(1)])
    assert sheet.rows[0].result_text == "经核查：符合"


def test_not_applicable_note_is_kept() -> None:
    run = _run([_result(1, Verdict.NOT_APPLICABLE, note="采用堡垒机代理，不适用")])
    sheet = build_sheet(_config(), run, [_item(1)])
    assert sheet.rows[0].compliance == "不适用"
    assert sheet.rows[0].note == "采用堡垒机代理，不适用"


def test_build_sheet_requires_pack_dir() -> None:
    with pytest.raises(RecordError, match="pack_dir"):
        build_sheet(_config(pack_dir=None), _run([_result(1, Verdict.COMPLIANT)]), [_item(1)])


def test_database_asset_uses_own_family() -> None:
    asset = _asset(AssetType.DATABASE)
    assert asset.family == "database"
    assert _asset(AssetType.SERVER).family == "server"
    assert _asset(AssetType.STORAGE).family == "server"


def test_unknown_seq_is_skipped() -> None:
    sheet = build_sheet(_config(), _run([_result(9, Verdict.COMPLIANT)]), [_item(1)])
    assert sheet.rows == []


def test_pack_items_fit_record_sheet() -> None:
    """真实规则包的测评项必须能直接进记录表。"""
    from core.items.loader import load_pack

    pack = load_pack(PACK_DIR)
    items = pack.items_for_level(3)
    assert items
    results = [_result(item.seq, Verdict.COMPLIANT) for item in items]
    sheet = build_sheet(_config(), _run(results), items)
    assert len(sheet.rows) == len(items)
    assert all(row.control_item for row in sheet.rows)
