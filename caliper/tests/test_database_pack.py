"""数据库规则域：MySQL/Oracle 三级端到端、引擎隔离、人工核查与风险整改。"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core.contracts.verdict import Verdict
from core.evidence.capture import load_capture, render_script
from core.issues.summary import TextLibrary, build_issue_rows
from core.items.loader import load_pack
from core.judge.runner import run_project
from core.major.major import assess_major
from core.remediation import RemediationLibrary, suggest

PACK_DIR = Path(__file__).resolve().parents[1] / "packs" / "database"
CASES_DIR = Path(__file__).resolve().parents[1] / "tests" / "cases"


def _project(
    tmp_path: Path,
    vendor: str,
    evidence: str = "pkg-mysql",
    level: int = 3,
    case: str = "database_mysql_l3",
    evidence_root: Path | None = None,
) -> Path:
    data = {
        "project_code": "示例-数据库-001",
        "system_name": "示例数据库系统",
        "level": level,
        "check_date": "2026-11-22",
        "evidence_root": str(evidence_root or (CASES_DIR / case / "evidence")),
        "output_dir": "out",
        "pack_dir": str(PACK_DIR),
        "assets": [
            {
                "device_name": "示例数据库实例",
                "ip": "192.0.2.10",
                "importance": "关键",
                "guide": f"{level}级-安全通用要求",
                "asset_type": "数据库",
                "vendor": vendor,
                "evidence_package": evidence,
            }
        ],
    }
    path = tmp_path / "project.yaml"
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return path


def _run(tmp_path: Path, vendor: str, **kwargs):
    from core.store.project import load_project

    project, _ = load_project(_project(tmp_path, vendor, **kwargs))
    pack = load_pack(PACK_DIR)
    return pack, project, run_project(project, pack).asset_runs[0]


def test_pack_exposes_database_rule_domains() -> None:
    pack = load_pack(PACK_DIR)

    assert pack.meta.levels == [2, 3, 4]
    assert set(pack.adapters) == {"mysql", "oracle", "sqlserver", "generic"}
    assert pack.meta.default_adapter == "generic"
    assert [len(pack.items_for_level(level)) for level in (2, 3, 4)] == [23, 34, 36]

    assert len(pack.adapters["mysql"].checks.checks) == 5
    assert len(pack.adapters["oracle"].checks.checks) == 5
    for key, expected in (("mysql", [15, 18, 18]), ("oracle", [7, 7, 7])):
        rules = pack.adapters[key].rules.rules
        counts = [sum(1 for rule in rules if rule.level == level) for level in (2, 3, 4)]
        assert counts == expected

    for key in ("sqlserver", "generic"):
        adapter = pack.adapters[key]
        assert adapter.meta.manual_all is True
        assert adapter.checks.checks == []
        assert adapter.rules.rules == []
        assert adapter.remediation is not None
        levels = {level for rule in adapter.remediation.rules for level in rule.applies_to.level}
        assert levels == {2, 3, 4}

    assert pack.major_library() is not None
    assert len(pack.all_high_risk()) == 16


def test_checks_map_binds_all_levels() -> None:
    pack = load_pack(PACK_DIR)

    for key in ("mysql", "oracle"):
        checks = pack.adapters[key].checks
        levels = {bind.level for check in checks.checks for bind in check.binds}
        assert levels == {2, 3, 4}


def test_mysql_level3_end_to_end(tmp_path: Path) -> None:
    pack, _, run = _run(tmp_path, "MySQL")

    assert run.adapter == "mysql"
    assert not any("未映射" in line for line in run.diagnostics), run.diagnostics
    assert run.item_by_seq(2).verdict is Verdict.COMPLIANT
    assert {point.point for point in run.item_by_seq(2).points} == {1, 2, 3}

    auth = run.item_by_seq(1)
    assert auth.verdict is Verdict.UNCOLLECTED
    assert {point.point for point in auth.points if point.passed} == {1, 2, 4}
    assert {point.point for point in auth.points if point.passed is None} == {3}

    remote = run.item_by_seq(3)
    assert remote.verdict is Verdict.UNCOLLECTED
    assert next(point for point in remote.points if point.point == 2).passed is True
    assert next(point for point in remote.points if point.point == 1).manual is True

    audit = run.item_by_seq(12)
    assert audit.verdict is Verdict.UNCOLLECTED
    assert next(point for point in audit.points if point.point == 1).passed is True
    assert {point.point for point in audit.points if point.manual} == {2, 3, 4}

    protected = run.item_by_seq(14)
    assert {point.point for point in protected.points if point.passed} == {1, 3}
    assert {point.point for point in protected.points if point.manual} == {2}

    for seq in (16, 17, 19, 21, 22, 23, 33, 34):
        assert run.item_by_seq(seq).verdict is Verdict.NOT_APPLICABLE
    for seq in (4, 6, 9, 10, 11, 13, 15, 20, 28, 29, 30, 31, 32):
        assert run.item_by_seq(seq).verdict is Verdict.UNCOLLECTED


def test_oracle_level3_end_to_end(tmp_path: Path) -> None:
    pack, _, run = _run(
        tmp_path, "Oracle", evidence="pkg-oracle", level=3, case="database_oracle_l3"
    )

    assert run.adapter == "oracle"
    assert not any("未映射" in line for line in run.diagnostics), run.diagnostics

    auth = run.item_by_seq(1)
    assert auth.verdict is Verdict.UNCOLLECTED
    assert {point.point for point in auth.points if point.passed} == {2, 4}
    assert {point.point for point in auth.points if point.manual} == {1, 3}

    login = run.item_by_seq(2)
    assert login.verdict is Verdict.UNCOLLECTED
    assert {point.point for point in login.points if point.passed} == {2, 3}
    assert {point.point for point in login.points if point.manual} == {1}

    assert next(
        point for point in run.item_by_seq(7).points if point.point == 2
    ).passed is True
    assert next(
        point for point in run.item_by_seq(12).points if point.point == 1
    ).passed is True
    assert next(
        point for point in run.item_by_seq(8).points if point.point == 2
    ).passed is True

    # Oracle 指导书未给出这些实施点的查询，只能保留人工核查，不能套用 MySQL 事实。
    for seq in (24, 25, 26, 27):
        item = run.item_by_seq(seq)
        assert item.verdict is Verdict.UNCOLLECTED
        assert all(point.passed is None for point in item.points), (seq, item.points)


@pytest.mark.parametrize("level", [2, 4])
@pytest.mark.parametrize(
    ("vendor", "adapter", "evidence", "case"),
    [
        ("MySQL", "mysql", "pkg-mysql", "database_mysql_l3"),
        ("Oracle", "oracle", "pkg-oracle", "database_oracle_l3"),
    ],
)
def test_database_level2_and_level4_end_to_end(
    tmp_path: Path, level: int, vendor: str, adapter: str, evidence: str, case: str
) -> None:
    pack, _, run = _run(
        tmp_path, vendor, evidence=evidence, level=level, case=case
    )

    assert run.adapter == adapter
    assert len(run.items) == {2: 23, 4: 36}[level]
    assert not any("未映射" in line for line in run.diagnostics), run.diagnostics
    items = {item.seq: item for item in pack.items_for_level(level)}
    for item in run.items:
        if items[item.seq].mode != "auto":
            continue
        for point in item.points:
            if point.manual:
                continue
            assert point.passed is not False, (level, vendor, item.seq, point.point, point.reason)


def test_engine_commands_are_isolated() -> None:
    mysql = render_script(load_capture(PACK_DIR / "adapters" / "mysql"), "database", 3)
    oracle = render_script(load_capture(PACK_DIR / "adapters" / "oracle"), "database", 3)

    assert "mysql -N -B" in mysql
    assert "validate_password" in mysql
    assert "sqlplus" not in mysql

    assert "sqlplus" in oracle
    assert "dba_users" in oracle
    assert "mysql -N -B" not in oracle
    assert "validate_password" not in oracle

    pack = load_pack(PACK_DIR)
    mysql_titles = {check.title for check in pack.adapters["mysql"].checks.checks}
    oracle_titles = {check.title for check in pack.adapters["oracle"].checks.checks}
    assert mysql_titles.isdisjoint(oracle_titles)


def test_mysql_cannot_consume_oracle_evidence(tmp_path: Path) -> None:
    pack, _, run = _run(
        tmp_path, "MySQL", evidence="pkg-oracle", level=3, case="database_oracle_l3"
    )

    assert run.adapter == "mysql"
    assert not any(item.verdict is Verdict.COMPLIANT for item in run.items)
    assert any("未映射" in line for line in run.diagnostics)


@pytest.mark.parametrize(
    ("vendor", "adapter"),
    [("SQL Server", "sqlserver"), ("PostgreSQL", "generic")],
)
def test_manual_only_engines_do_not_apply_vendor_commands(
    tmp_path: Path, vendor: str, adapter: str
) -> None:
    pack, _, run = _run(tmp_path, vendor)

    assert run.adapter == adapter
    assert all(
        item.verdict in {Verdict.UNCOLLECTED, Verdict.NOT_APPLICABLE}
        for item in run.items
    )
    assert not any(item.verdict is Verdict.COMPLIANT for item in run.items)
    if adapter == "generic":
        assert any("不得套用其他厂商命令" in line for line in run.diagnostics)


def test_oracle_manual_points_follow_level(tmp_path: Path) -> None:
    pack = load_pack(PACK_DIR)
    oracle = pack.adapters["oracle"]

    level2 = {item.seq: item for item in pack.items_for_level(2)}
    level3 = {item.seq: item for item in pack.items_for_level(3)}

    # 二级审计保护项 seq=10，三级为 seq=14；人工核查点必须绑定到各自等级。
    assert {point.point for point in oracle.meta.manual_points_by_level[2][10]} == {1, 3}
    assert {point.point for point in oracle.meta.manual_points_by_level[3][14]} == {1, 3}
    assert 14 not in oracle.meta.manual_points_by_level[2]
    assert level2[10].mode == "auto"
    assert level3[14].mode == "auto"

    _, _, run = _run(
        tmp_path, "Oracle", evidence="pkg-oracle", level=2, case="database_oracle_l3"
    )
    item = run.item_by_seq(10)
    assert item.verdict is Verdict.UNCOLLECTED
    # 共享人工点（审计备份）与 Oracle 特有手工点（删除审计记录）合并。
    assert {point.point for point in item.points if point.manual} == {1, 2, 3}


def test_mysql_failure_generates_issue_and_remediation(tmp_path: Path) -> None:
    pack = load_pack(PACK_DIR)
    items = pack.items_for_level(3)

    broken = tmp_path / "evidence" / "broken" / "raw"
    broken.mkdir(parents=True)
    text = (
        CASES_DIR / "database_mysql_l3" / "evidence" / "pkg-mysql" / "raw" / "mysql-l3.log"
    ).read_text(encoding="utf-8")
    text = (
        text.replace("\tACTIVE", "\tINACTIVE")
        .replace("threshold\t5", "threshold\t20")
        .replace("interactive_timeout\t600", "interactive_timeout\t3600")
        .replace("wait_timeout\t600", "wait_timeout\t3600")
    )
    (broken / "mysql-l3.log").write_text(text, encoding="utf-8")

    project_path = _project(
        tmp_path,
        "MySQL",
        evidence="broken",
        evidence_root=tmp_path / "evidence",
    )
    from core.store.project import load_project

    project, _ = load_project(project_path)
    result = run_project(project, pack)
    run = result.asset_runs[0]

    assert run.item_by_seq(2).verdict is Verdict.NON_COMPLIANT

    issues = build_issue_rows(result, items, TextLibrary(pack.all_texts()))
    target = [issue for issue in issues if issue.seq == 2]
    assert target, "不符合项应生成安全问题记录"
    assert target[0].asset_type == "数据库"

    all_items = [
        item for level in (2, 3, 4) for item in pack.items_for_level(level)
    ]
    library = RemediationLibrary.load(PACK_DIR, all_items)
    advices = suggest(library, items, run)
    assert any(advice.seq == 2 for advice in advices)


def test_high_risk_bindings_are_level_specific() -> None:
    pack = load_pack(PACK_DIR)
    library = pack.major_library()
    assert library is not None

    counts = {level: len(pack.items_for_level(level)) for level in (2, 3, 4)}
    for entry in pack.all_high_risk():
        binds = entry.get("binds") or {}
        for level, seqs in binds.items():
            level = int(level)
            assert 1 <= level <= 4
            assert all(1 <= seq <= counts[level] for seq in seqs), (entry["hr_id"], level, seqs)

    candidates = assess_major(pack.all_high_risk(), library)
    assert len(candidates) == 16
    assert all(len(candidate.scores) == 3 for candidate in candidates)
