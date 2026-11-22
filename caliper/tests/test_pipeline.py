"""全链路回归：采集命令库 → 合成 uniTerm 日志 → 解析 → 判定 → 记录表 → 整改 → 重大隐患。

测试完全使用合成数据：不读取案例模版、不联网、不执行采集脚本。
日志中的 IP 固定为文档保留地址 192.0.2.10，项目编号与主机名均为示例占位。
"""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest
import yaml

from core.contracts.verdict import Verdict
from core.evidence.capture import CaptureRule, load_capture
from core.evidence.logparse import END_MARKER, RESULTS_MARKER
from core.evidence.package import load_evidence
from core.issues.summary import TextLibrary, build_issue_rows
from core.items.loader import load_pack
from core.judge.runner import run_project
from core.major.major import (
    MajorGateError,
    assess_major,
    basis_fingerprints,
    compute_rule_version,
    ensure_major_confirmations,
)
from core.records.model import COLUMNS, build_sheet
from core.records.writer import COLUMN_WIDTHS, TITLE_TEXT, write_record_book
from core.remediation import RemediationLibrary, suggest
from core.store.corrections import CorrectionStore
from core.store.project import load_project

PACK_DIR = Path(__file__).resolve().parents[1] / "packs" / "linux_os"
SAMPLE_IP = "192.0.2.10"
SAMPLE_PROJECT_CODE = "示例-回归-001"
SAMPLE_SYSTEM = "示例系统A"

# 只取五个真正参与判定的检查块，覆盖第 1 项的全部实施点与第 18 项的唯一实施点。
SELECTED_TITLES = (
    "Duplicate UID / UID=0 accounts",
    "Empty / expired password",
    "Password complexity",
    "Password policy (login.defs)",
    "Remote login source restriction",
)

# 第 1 项全部实施点均不通过；第 18 项通过，用于同时观察两类结论。
BLOCK_OUTPUTS: dict[str, list[str]] = {
    "Duplicate UID / UID=0 accounts": [
        "duplicate uid: 1001",
        "UID=0: 占位账号",
    ],
    "Empty / expired password": [
        "占位账号 empty-password last-change=2026-01-01 max=99999 expire=",
    ],
    "Password complexity": [
        "pam_pwquality absent",
        "pwquality.conf not found",
    ],
    "Password policy (login.defs)": [
        "PASS_MAX_DAYS 999",
    ],
    "Remote login source restriction": [
        "AllowUsers 占位账号",
    ],
}


def _rule_by_title(rules: list[CaptureRule]) -> dict[str, CaptureRule]:
    return {rule.title: rule for rule in rules}


def _render_synthetic_log(rules: list[CaptureRule]) -> str:
    """按真实采集脚本的结构写出结果段，标题与命令全部取自 capture.yaml。"""
    index = _rule_by_title(rules)
    lines = [
        "# ===== Ubuntu/Debian baseline check (family=server, level=3) =====",
        RESULTS_MARKER,
    ]
    section = ""
    for number, title in enumerate(SELECTED_TITLES, 1):
        rule = index[title]
        if rule.section != section:
            lines.append(f"===== {rule.section} =====")
            section = rule.section
        lines.append(f"[{number:02d}] {title}")
        lines.append(f"  cmd: {' '.join(rule.command.split())}")
        if rule.file:
            lines.append(f"  file: {rule.file}")
        lines.extend(f"  {text}" for text in BLOCK_OUTPUTS[title])
    lines.extend(["", END_MARKER])
    return "\n".join(lines) + "\n"


def _write_project(base: Path, evidence_root: Path) -> Path:
    project_path = base / "project.yaml"
    project_path.write_text(
        yaml.safe_dump(
            {
                "project_code": SAMPLE_PROJECT_CODE,
                "system_name": SAMPLE_SYSTEM,
                "level": 3,
                "check_date": "2026-11-21",
                "evidence_root": str(evidence_root),
                "output_dir": "out",
                "pack_dir": str(PACK_DIR),
                "assets": [
                    {
                        "device_name": f"{SAMPLE_SYSTEM}-应用服务器",
                        "ip": SAMPLE_IP,
                        "importance": "一般",
                        "guide": "三级-安全通用要求",
                        "asset_type": "服务器",
                        "evidence_package": "pkg-示例",
                    }
                ],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return project_path


@pytest.fixture()
def pipeline(tmp_path: Path):
    """准备合成日志、临时项目与跑批结果，供各断言复用。"""
    rules = load_capture(PACK_DIR).rules_for("server", 3)
    evidence_root = tmp_path / "evidence"
    package_root = evidence_root / "pkg-示例"
    (package_root / "raw").mkdir(parents=True)
    (package_root / "raw" / "uniterm.log").write_text(
        _render_synthetic_log(rules), encoding="utf-8"
    )
    project, base_dir = load_project(_write_project(tmp_path, evidence_root))
    pack = load_pack(PACK_DIR)
    result = run_project(project, pack, base_dir=base_dir)
    return {
        "tmp": tmp_path,
        "evidence_root": evidence_root,
        "package_root": package_root,
        "project": project,
        "pack": pack,
        "result": result,
        "run": result.asset_runs[0],
        "items": pack.items_for_level(3),
        "checks": pack.checks,
    }


def test_parses_synthetic_log_without_unmapped_blocks(pipeline) -> None:
    package = load_evidence(pipeline["package_root"], host=SAMPLE_SYSTEM, level=3)

    assert len(package.blocks) == len(SELECTED_TITLES)
    assert [block.title for block in package.blocks] == list(SELECTED_TITLES)
    assert {block.section for block in package.blocks} == {"2. IDENTIFICATION"}
    assert all(block.os_family == "debian" for block in package.blocks)
    assert all(block.status.value == "collected" for block in package.blocks)

    diagnostics = [*package.diagnostics, *pipeline["run"].diagnostics]
    assert not any("未映射" in line for line in diagnostics), diagnostics

    # 每个块都必须在 checks_map.yaml 中有标题映射。
    mapped_titles = {check.title for check in pipeline["checks"].checks}
    assert set(SELECTED_TITLES) <= mapped_titles


def test_runner_uses_pack_checks_for_mysql_session(pipeline) -> None:
    mysql_log = """\
mysql> SELECT VERSION();
+--------------------+
| VERSION()          |
+--------------------+
| 8.0.0-0ubuntu0.1   |
+--------------------+
1 row in set (0.00 sec)
mysql>
"""
    (pipeline["package_root"] / "raw" / "uniterm.log").write_text(mysql_log, encoding="utf-8")

    result = run_project(pipeline["project"], pipeline["pack"], base_dir=pipeline["tmp"])
    run = result.asset_runs[0]

    assert run.os_family == "unknown"
    assert any("按交互会话解析 1 个检查块" in line for line in run.diagnostics)
    assert run.item_by_seq(6).verdict is Verdict.UNCOLLECTED


def test_judge_produces_verdicts(pipeline) -> None:
    run = pipeline["run"]
    assert len(run.items) == len(pipeline["items"]) == 34

    first = run.item_by_seq(1)
    assert first is not None
    assert first.verdict is Verdict.NON_COMPLIANT
    assert {point.point for point in first.points if not point.passed} == {1, 2, 3, 4}

    remote_login = run.item_by_seq(18)
    assert remote_login is not None
    assert remote_login.verdict is Verdict.COMPLIANT

    counts = pipeline["result"].verdict_counts()
    assert counts.get("不符合(0分)") == 1
    assert counts.get("符合(1分)") == 1

    # 没有采集到实施点的测评项应给出显式诊断，而不是静默通过。
    second = run.item_by_seq(2)
    assert second is not None
    assert second.verdict is Verdict.UNCOLLECTED


def test_build_sheet_uses_company_columns(pipeline) -> None:
    sheet = build_sheet(pipeline["project"], pipeline["run"], pipeline["items"])

    assert len(sheet.rows) == len(pipeline["items"])
    assert [row.seq for row in sheet.rows] == [item.seq for item in pipeline["items"]]
    allowed = {"符合(1分)", "不符合(0分)", "不适用", ""}
    assert all(row.compliance in allowed for row in sheet.rows)
    assert all(row.result_text.startswith("经核查：") for row in sheet.rows)
    assert sheet.row_by_seq(1).compliance == "不符合(0分)"
    assert sheet.row_by_seq(18).compliance == "符合(1分)"
    assert sheet.rows[0].values()[3].startswith("经核查：")


def test_write_record_book_round_trips(pipeline) -> None:
    target = write_record_book(
        pipeline["project"],
        pipeline["result"],
        {3: pipeline["items"]},
        out_dir=pipeline["tmp"] / "out",
    )
    assert target.is_file()

    workbook = openpyxl.load_workbook(target)
    assert workbook.sheetnames == [pipeline["run"].asset.device_name]
    sheet = workbook.worksheets[0]

    assert sheet["A1"].value == TITLE_TEXT
    assert sheet["C2"].value == SAMPLE_PROJECT_CODE
    assert sheet["F2"].value == SAMPLE_SYSTEM
    assert sheet["C4"].value == SAMPLE_IP
    assert tuple(cell.value for cell in sheet[7]) == COLUMNS
    assert sheet["A8"].value == "安全通用要求"
    assert sheet.max_row == 8 + len(pipeline["items"])
    assert sheet.column_dimensions["H"].width == COLUMN_WIDTHS["H"]

    written = [sheet.cell(row=row, column=5).value for row in range(9, sheet.max_row + 1)]
    assert set(written) <= {"符合(1分)", "不符合(0分)", "不适用", None}
    assert written.count("不符合(0分)") == 1


def test_remediation_for_non_compliant_item(pipeline) -> None:
    library = RemediationLibrary.load(PACK_DIR, pipeline["items"])
    advices = suggest(library, pipeline["items"], pipeline["run"])

    first = [advice for advice in advices if advice.seq == 1]
    assert first, "不符合项应生成整改建议"
    advice = first[0]
    assert advice.rule_id == "REM-01"
    assert advice.problem and advice.action and advice.clause
    assert advice.priority in {"高", "中", "低"}
    assert all(advice.seq != 18 for advice in advices)


def test_major_scoring_is_deterministic_and_gates_export(pipeline, tmp_path: Path) -> None:
    library = pipeline["pack"].major
    assert library is not None

    first = assess_major(pipeline["pack"].high_risk, library)
    second = assess_major(pipeline["pack"].high_risk, library)
    assert first == second
    assert any(candidate.is_candidate for candidate in first)
    assert any(not candidate.is_candidate for candidate in first)
    assert all(len(candidate.scores) == 3 for candidate in first)

    hr01 = next(candidate for candidate in first if candidate.hr_ids == ("HR-01",))
    assert hr01.is_candidate
    assert hr01.total == pytest.approx(3.0)

    issues = build_issue_rows(
        pipeline["result"], pipeline["items"], TextLibrary(pipeline["pack"].texts)
    )
    assert len(issues) == 1
    assert issues[0].seq == 1
    assert issues[0].asset_type == "服务器"

    rule_version = compute_rule_version(
        [PACK_DIR / "high_risk.yaml", PACK_DIR / "major.yaml"]
    )
    fingerprint = basis_fingerprints(pipeline["result"])["服务器"]
    store = CorrectionStore(tmp_path / "corrections.db")
    try:
        with pytest.raises(MajorGateError, match="未完成有效人工确认"):
            ensure_major_confirmations(
                issues,
                pipeline["pack"].high_risk,
                library,
                3,
                pipeline["result"],
                store,
                rule_version,
            )

        store.confirm_major(
            3, issues[0].item_id, "服务器", rule_version, fingerprint
        )
        ensure_major_confirmations(
            issues,
            pipeline["pack"].high_risk,
            library,
            3,
            pipeline["result"],
            store,
            rule_version,
        )

        store.confirm_major(
            3, issues[0].item_id, "服务器", rule_version, "指纹-已变更"
        )
        with pytest.raises(MajorGateError, match="判定依据已变化"):
            ensure_major_confirmations(
                issues,
                pipeline["pack"].high_risk,
                library,
                3,
                pipeline["result"],
                store,
                rule_version,
            )
    finally:
        store.close()
