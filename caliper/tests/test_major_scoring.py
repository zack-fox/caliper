"""高风险降风险字段、重大隐患三维评分与人工确认失效规则。"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from core.contracts.columns import MAJOR_COLUMNS
from core.issues.summary import IssueRow
from core.items.loader import load_pack
from core.major.major import (
    MajorGateError,
    assess_major,
    basis_fingerprints,
    compute_rule_version,
    ensure_major_confirmations,
)
from core.major.risk import build_major_rows
from core.model.entities import Asset, AssetRun, ProjectConfig, RunResult
from core.store.corrections import CorrectionStore

PACK = Path(__file__).resolve().parents[1] / "packs" / "linux_os"


def _pack():
    return load_pack(PACK)


def _result(fingerprint: str = "fp-示例-01") -> RunResult:
    asset = Asset(
        device_name="示例系统A-应用服务器",
        ip="192.0.2.10",
        importance="一般",
        guide="三级-安全通用要求",
        asset_type="服务器",
    )
    return RunResult(
        project=ProjectConfig(level=3, check_date=date.today()),
        asset_runs=[AssetRun(asset=asset, basis_fingerprint=fingerprint)],
    )


def _issue() -> IssueRow:
    values = {column: "" for column in MAJOR_COLUMNS}
    values.update(
        {
            "安全要求": "安全通用要求",
            "安全层面": "安全计算环境",
            "安全控制点": "身份鉴别",
            "测评项": "应对登录的用户进行身份标识和鉴别",
            "资产类型": "服务器",
            "关联资产": "示例系统A-应用服务器",
            "问题概述": "存在弱口令账户",
            "整改建议": "调整口令策略",
            "影响的网络区域": "计算区",
        }
    )
    return IssueRow(1, "L3-CES1-01", "服务器", "T001", values)


def test_high_risk_entries_have_reduction_fields() -> None:
    pack = _pack()
    assert len(pack.high_risk) == 16
    for row in pack.high_risk:
        assert isinstance(row["可降风险"], bool)
        assert isinstance(row["降风险前提"], str)
        if row["可降风险"]:
            assert row["降风险前提"].strip()
    assert {row["hr_id"] for row in pack.high_risk if row["可降风险"]} == {
        f"HR-{index:02d}" for index in range(1, 13)
    }


def test_major_library_covers_every_high_risk_with_valid_scores() -> None:
    pack = _pack()
    library = pack.major
    assert library is not None
    assert library.status == "active"
    assert abs(sum(item.weight for item in library.dimensions) - 1) < 0.001
    assert library.missing_hr_ids(row["hr_id"] for row in pack.high_risk) == []
    for rule in library.rules:
        assert rule.hr_ids
        for name in ("相关性", "严重性", "高发性"):
            assert 0 <= rule.scores[name].score <= 3
            assert rule.scores[name].reason.strip()


def test_assessment_is_deterministic_and_threshold_boundary() -> None:
    pack = _pack()
    first = assess_major(pack.high_risk, pack.major)
    second = assess_major(pack.high_risk, pack.major)
    assert first == second
    by_rule = {item.rule_id: item for item in first}
    # MR-12 加权总分恰好等于阈值，按“达到即候选”处理。
    assert by_rule["MR-12"].total == by_rule["MR-12"].threshold == 2.4
    assert by_rule["MR-12"].is_candidate is True
    assert by_rule["MR-06"].total < by_rule["MR-06"].threshold
    assert by_rule["MR-06"].is_candidate is False
    assert all(len(item.scores) == 3 for item in first)
    assert all(item.clauses for item in first)


def test_rule_version_changes_with_rule_content(tmp_path: Path) -> None:
    high_risk = tmp_path / "high_risk.yaml"
    major = tmp_path / "major.yaml"
    high_risk.write_text("a: 1\n", encoding="utf-8")
    major.write_text("b: 2\n", encoding="utf-8")
    first = compute_rule_version([high_risk, major])
    assert first == compute_rule_version([high_risk, major])
    major.write_text("b: 3\n", encoding="utf-8")
    assert compute_rule_version([high_risk, major]) != first


def test_confirmation_version_or_fingerprint_mismatch_is_invalid(tmp_path: Path) -> None:
    store = CorrectionStore(tmp_path / "corrections.db")
    try:
        assert not store.major_confirmation_valid(3, "L3-CES1-01", "服务器", "v1", "fp-1")
        store.confirm_major(3, "L3-CES1-01", "服务器", "v1", "fp-1")
        assert store.major_confirmation_valid(3, "L3-CES1-01", "服务器", "v1", "fp-1")
        assert store.major_confirmation_issue(
            3, "L3-CES1-01", "服务器", "v2", "fp-1"
        ) == "规则版本已变更，需重新确认"
        assert store.major_confirmation_issue(
            3, "L3-CES1-01", "服务器", "v1", "fp-2"
        ) == "判定依据已变化，需重新确认"
    finally:
        store.close()


def test_export_gate_blocks_unconfirmed_and_stale_entries(tmp_path: Path) -> None:
    pack = _pack()
    result = _result()
    issue = _issue()
    version = compute_rule_version(
        [PACK / "high_risk.yaml", PACK / "major.yaml"]
    )
    store = CorrectionStore(tmp_path / "corrections.db")
    try:
        with pytest.raises(MajorGateError, match="未完成有效人工确认"):
            ensure_major_confirmations(
                [issue], pack.high_risk, pack.major, 3, result, store, version
            )

        store.confirm_major(3, issue.item_id, issue.asset_type, version, "fp-示例-01")
        ensure_major_confirmations(
            [issue], pack.high_risk, pack.major, 3, result, store, version
        )

        store.confirm_major(3, issue.item_id, issue.asset_type, "旧版本", "fp-示例-01")
        with pytest.raises(MajorGateError, match="规则版本已变更"):
            ensure_major_confirmations(
                [issue], pack.high_risk, pack.major, 3, result, store, version
            )
    finally:
        store.close()


def test_basis_fingerprints_group_by_asset_type() -> None:
    result = _result("fp-示例-01")
    assert basis_fingerprints(result) == {"服务器": "fp-示例-01"}


def test_major_rows_fill_three_dimension_scores() -> None:
    pack = _pack()
    rows = build_major_rows(
        [_issue()], pack.high_risk, 3, {("L3-CES1-01", "服务器")}, pack.major
    )
    assert len(rows) == 1
    values = rows[0].values
    assert values["相关性"].startswith("3（")
    assert values["严重性"].startswith("3（")
    assert values["高发性"].startswith("3（")
    assert "MR-01" in values["综合分析"]
    assert "2.40" in values["综合分析"]


def test_old_corrections_schema_upgrades_without_data_loss(tmp_path: Path) -> None:
    path = tmp_path / "corrections.db"
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE corrections (
            level INTEGER NOT NULL,
            item_id TEXT NOT NULL,
            asset_type TEXT NOT NULL,
            field TEXT NOT NULL,
            value TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            PRIMARY KEY (level, item_id, asset_type, field)
        )
        """
    )
    connection.execute(
        "INSERT INTO corrections VALUES (3, 'L3-CES1-01', '服务器', 'note', '旧备注', '', '2026-01-01T00:00:00')"
    )
    connection.execute(
        "INSERT INTO corrections VALUES (3, 'L3-CES1-01', '服务器', 'major', '1', '', '2026-01-01T00:00:00')"
    )
    connection.commit()
    connection.close()

    store = CorrectionStore(path)
    try:
        columns = {
            str(row[1])
            for row in store._connection.execute("PRAGMA table_info(corrections)")
        }
        assert {"rule_version", "basis_fingerprint"} <= columns
        assert store.get(3, "L3-CES1-01", "服务器", "note") == "旧备注"
        assert store.major_confirmed(3) == {("L3-CES1-01", "服务器")}
        # 旧确认没有版本/指纹留痕，按失效处理，不静默放行。
        assert not store.major_confirmation_valid(
            3, "L3-CES1-01", "服务器", "v1", "fp-1"
        )
    finally:
        store.close()
