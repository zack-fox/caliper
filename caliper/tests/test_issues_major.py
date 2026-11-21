"""问题汇总、重大隐患与校正持久化。"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from core.contracts.verdict import Verdict
from core.issues.summary import TextLibrary, build_issue_rows, render_issue_workbook, verify_issue_workbook
from core.major.risk import build_major_rows, render_major_workbook, verify_major_workbook
from core.model.entities import (
    Asset,
    AssetRun,
    Item,
    ItemResult,
    PointResult,
    ProjectConfig,
    RunResult,
)
from core.store.corrections import CorrectionStore, apply_notes

ROOT = Path(__file__).resolve().parents[1]
HIGH_RISK = [
    {
        "level_min": 3,
        "binds_items": [1],
        "问题简述": "口令策略过弱",
        "整改建议": "调整口令有效期",
    }
]


def _run(verdict: Verdict = Verdict.PARTIAL) -> RunResult:
    asset = Asset(
        device_name="示例系统A-应用服务器",
        ip="192.0.2.10",
        importance="一般",
        guide="三级-安全通用要求",
        asset_type="服务器",
        zone="计算区",
    )
    item = Item(
        item_id="L3-CES1-01",
        level=3,
        seq=1,
        unit_no=1,
        control_point="身份鉴别",
        control_item="a）应对登录的用户进行身份标识和鉴别",
        importance="重要",
        check_content="检查",
        criteria="判断",
        policy="mixed_partial",
        mode="auto",
        binary=False,
        optional_clause=False,
    )
    result = ItemResult(
        item_id=item.item_id,
        seq=1,
        control_point=item.control_point,
        importance=item.importance,
        verdict=verdict,
        result_text="",
        note="",
        points=[
            PointResult(
                point=4,
                passed=False,
                reason="口令最大有效期超过 90 天",
                block_title="Password policy",
            )
        ],
    )
    return RunResult(
        project=ProjectConfig(level=3, check_date=date.today()),
        asset_runs=[AssetRun(asset=asset, items=[result])],
    )


def test_issue_and_major_rows() -> None:
    result = _run()
    item = Item(
        item_id="L3-CES1-01",
        level=3,
        seq=1,
        unit_no=1,
        control_point="身份鉴别",
        control_item="a）应对登录的用户进行身份标识和鉴别",
        importance="重要",
        check_content="检查",
        criteria="判断",
        policy="mixed_partial",
        mode="auto",
        binary=False,
        optional_clause=False,
    )
    rows = build_issue_rows(result, [item], TextLibrary([]))
    assert len(rows) == 1
    row = rows[0]
    assert row.issue_no == "T001"
    assert row.values["资产类型"] == "服务器"
    assert row.values["关联资产"] == "示例系统A-应用服务器"
    assert "口令最大有效期" in row.values["问题详述"]
    assert row.values["是否符合重大判定原则"] == ""

    confirmed = {("L3-CES1-01", "服务器")}
    assert build_major_rows(rows, HIGH_RISK, 3, set()) == []
    major = build_major_rows(rows, HIGH_RISK, 3, confirmed)
    assert len(major) == 1
    assert major[0].values["重大风险隐患触发项"] == "口令策略过弱"
    assert major[0].values["是否整改"] == "未整改"


def test_render_issue_and_major(tmp_path: Path) -> None:
    result = _run()
    item = Item(
        item_id="L3-CES1-01",
        level=3,
        seq=1,
        unit_no=1,
        control_point="身份鉴别",
        control_item="a）应对登录的用户进行身份标识和鉴别",
        importance="重要",
        check_content="检查",
        criteria="判断",
        policy="mixed_partial",
        mode="auto",
        binary=False,
        optional_clause=False,
    )
    project = ProjectConfig(
        level=3,
        check_date=date.today(),
        project_code="示例-001",
        system_name="示例系统A",
    )
    rows = build_issue_rows(result, [item], TextLibrary([]), {("L3-CES1-01", "服务器")})
    moment = datetime(2026, 11, 21, 12, 0, 0)

    issue_path = render_issue_workbook(
        rows, project, ROOT / "templates" / "issue_summary.xlsx", tmp_path, moment
    )
    assert verify_issue_workbook(issue_path, 1) == []

    major_rows = build_major_rows(rows, HIGH_RISK, 3, {("L3-CES1-01", "服务器")})
    major_path = render_major_workbook(
        major_rows, project, ROOT / "templates" / "major_risk.xlsx", tmp_path, moment
    )
    assert verify_major_workbook(major_path) == []


def test_corrections_roundtrip(tmp_path: Path) -> None:
    result = _run()
    store = CorrectionStore(tmp_path / "corrections.db")
    try:
        store.set(3, "L3-CES1-01", "服务器", "note", "现场已确认")
        store.set(3, "L3-CES1-01", "服务器", "major", "1")
        assert store.notes(3) == {("L3-CES1-01", "服务器"): "现场已确认"}
        assert store.major_confirmed(3) == {("L3-CES1-01", "服务器")}
        apply_notes(result, store, 3)
        assert result.asset_runs[0].items[0].note == "现场已确认"
        store.set(3, "L3-CES1-01", "服务器", "note", "")
        assert store.notes(3) == {}
    finally:
        store.close()


def test_record_changes_clear_stale_major_confirmation(tmp_path: Path) -> None:
    store = CorrectionStore(tmp_path / "corrections.db")
    try:
        store.save_record_override(
            3,
            "L3-CES1-01",
            "服务器A",
            "原始记录",
            "部分符合",
            "",
            "首次人工校正",
            asset_type="服务器",
        )
        store.set(3, "L3-CES1-01", "服务器", "major", "1")
        store.save_record_override(
            3,
            "L3-CES1-01",
            "服务器A",
            "修改后的记录",
            "不符合",
            "",
            "现场复核后调整",
            asset_type="服务器",
        )
        assert store.major_confirmed(3) == set()

        store.set(3, "L3-CES1-01", "服务器", "major", "1")
        store.clear_record_override(
            3, "L3-CES1-01", "服务器A", asset_type="服务器"
        )
        assert store.major_confirmed(3) == set()
    finally:
        store.close()
