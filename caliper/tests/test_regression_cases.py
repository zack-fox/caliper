"""脱敏案例回归库驱动：自动发现 tests/cases/*/case.yaml 并跑全链路。

用例全部是入库的静态文件，只依赖仓库内 ``packs/linux_os``；
不读取 ``fixtures/``，也不写入仓库目录。
"""

from __future__ import annotations

import re
from pathlib import Path

import openpyxl
import pytest
import yaml

from core.contracts.verdict import Verdict
from core.evidence.package import load_evidence
from core.issues.summary import TextLibrary, build_issue_rows
from core.items.loader import load_pack
from core.judge.runner import run_project
from core.major.major import assess_major
from core.major.risk import triggers_for
from core.records.model import COLUMNS, build_sheet
from core.records.writer import write_record_book
from core.remediation import RemediationLibrary, suggest
from core.store.project import load_project

CASES_DIR = Path(__file__).resolve().parent / "cases"
PACK_DIR = Path(__file__).resolve().parents[1] / "packs" / "linux_os"
CASE_FILES = sorted(CASES_DIR.glob("*/case.yaml"))
CASE_IDS = [path.parent.name for path in CASE_FILES]

REQUIRED_CASE_FIELDS = {"id", "title", "level", "assets", "evidence", "expect"}
ALLOWED_IPS = {"192.0.2.10", "192.0.2.11"}
ALLOWED_COMPLIANCE = {"符合(1分)", "不符合(0分)", "不适用", None}
IPV4_RE = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")

assert len(CASE_FILES) >= 4, "tests/cases 至少需要 4 个 case.yaml"


def _load_case(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{path}：case.yaml 应为对象"
    missing = REQUIRED_CASE_FIELDS - set(data)
    assert not missing, f"{path}：缺少字段 {sorted(missing)}"
    assert data["level"] in {2, 3}, f"{path}：level 只支持 2/3"
    assert data["assets"], f"{path}：assets 不能为空"
    assert data["evidence"], f"{path}：evidence 不能为空"
    assert path.parent.name == data["id"], f"{path}：id 应与目录名一致"
    return data


def _write_project(base: Path, case: dict, case_dir: Path) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    payload = {
        "project_code": case.get("project_code", "示例-回归-001"),
        "system_name": case.get("system_name", "示例系统A"),
        "level": case["level"],
        "check_date": case.get("check_date", "2026-11-21"),
        "evidence_root": str(case_dir / "evidence"),
        "output_dir": str(base / "out"),
        "pack_dir": str(PACK_DIR),
        "assets": [
            {**asset, "evidence_package": case["evidence"]}
            for asset in case["assets"]
        ],
    }
    path = base / "project.yaml"
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


def _execute(base: Path, case: dict, case_dir: Path):
    project, base_dir = load_project(_write_project(base, case, case_dir))
    pack = load_pack(PACK_DIR)
    result = run_project(project, pack, base_dir=base_dir)
    return project, pack, result


def _candidate_hr_ids(issues, pack, level: int) -> list[str]:
    assert pack.major is not None
    found: set[str] = set()
    for issue in issues:
        entries = triggers_for(issue.seq, level, pack.high_risk)
        for candidate in assess_major(entries, pack.major):
            if candidate.is_candidate:
                found.update(candidate.hr_ids)
    return sorted(found)


def _assert_sanitized(case: dict, case_dir: Path) -> None:
    assert "示例" in case.get("project_code", "示例-回归-001"), "项目编号必须为示例占位"
    assert "示例" in case.get("system_name", "示例系统A"), "系统名必须为示例占位"
    for asset in case["assets"]:
        assert asset["ip"] in ALLOWED_IPS, f"资产 IP 必须使用文档保留地址：{asset['ip']}"
        assert "示例" in asset["device_name"], f"资产名必须为示例占位：{asset['device_name']}"
    for path in case_dir.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for address in IPV4_RE.findall(text):
            assert address in ALLOWED_IPS, f"{path}：出现非文档保留地址 {address}"


@pytest.mark.parametrize("case_file", CASE_FILES, ids=CASE_IDS)
def test_case_pipeline(case_file: Path, tmp_path: Path) -> None:
    case = _load_case(case_file)
    case_dir = case_file.parent
    project, pack, result = _execute(tmp_path, case, case_dir)
    expect = case["expect"]

    run = result.asset_runs[0]
    items = pack.items_for_level(case["level"])
    assert len(run.items) == len(items)

    package = load_evidence(
        case_dir / "evidence" / case["evidence"],
        host=run.asset.device_name,
        level=case["level"],
    )
    assert len(package.blocks) == expect["blocks"]
    assert sorted({block.session for block in package.blocks}) == list(
        range(1, expect["sessions"] + 1)
    )
    assert [block.title for block in package.blocks] == (
        expect["block_titles"] * expect["sessions"]
    )
    for session, family in enumerate(expect["os_family_by_session"], start=1):
        families = {
            block.os_family for block in package.blocks if block.session == session
        }
        assert families == {family}

    diagnostics = [*package.diagnostics, *run.diagnostics]
    unmapped = [line for line in diagnostics if "未映射" in line]
    assert len(unmapped) == expect["unmapped"], diagnostics

    sheet = build_sheet(project, run, items)
    for seq, verdict in expect["verdicts"].items():
        item = run.item_by_seq(int(seq))
        assert item is not None
        assert item.verdict == Verdict(verdict)
        row = sheet.row_by_seq(int(seq))
        assert row is not None
        assert row.compliance == expect["compliance"].get(int(seq), "")

    library = RemediationLibrary.load(PACK_DIR, items)
    advices = suggest(library, items, run)
    assert [advice.rule_id for advice in advices] == expect["remediation"]

    issues = build_issue_rows(result, items, TextLibrary(pack.texts))
    assert _candidate_hr_ids(issues, pack, case["level"]) == sorted(
        expect["major_candidates"]
    )

    rerun_project, rerun_pack, rerun = _execute(tmp_path / "rerun", case, case_dir)
    rerun_run = rerun.asset_runs[0]
    assert rerun_run.model_dump() == run.model_dump()
    rerun_sheet = build_sheet(rerun_project, rerun_run, items)
    assert [row.values() for row in rerun_sheet.rows] == [
        row.values() for row in sheet.rows
    ]
    rerun_advices = suggest(
        RemediationLibrary.load(PACK_DIR, items), items, rerun_run
    )
    assert [(item.rule_id, item.seq) for item in rerun_advices] == [
        (item.rule_id, item.seq) for item in advices
    ]
    rerun_issues = build_issue_rows(rerun, items, TextLibrary(rerun_pack.texts))
    assert _candidate_hr_ids(rerun_issues, rerun_pack, case["level"]) == _candidate_hr_ids(
        issues, pack, case["level"]
    )


@pytest.mark.parametrize("case_file", CASE_FILES, ids=CASE_IDS)
def test_case_record_book_and_sanitized(case_file: Path, tmp_path: Path) -> None:
    case = _load_case(case_file)
    case_dir = case_file.parent
    _assert_sanitized(case, case_dir)

    project, pack, result = _execute(tmp_path, case, case_dir)
    items = pack.items_for_level(case["level"])
    target = write_record_book(
        project, result, {case["level"]: items}, out_dir=tmp_path / "out"
    )
    assert target.is_file()

    workbook = openpyxl.load_workbook(target)
    assert len(workbook.worksheets) == len(case["assets"])
    for sheet, asset in zip(workbook.worksheets, case["assets"], strict=True):
        assert tuple(cell.value for cell in sheet[7]) == COLUMNS
        assert len(tuple(cell.value for cell in sheet[7])) == 9
        assert sheet["C3"].value == asset["device_name"]
        values = [
            sheet.cell(row=row, column=5).value for row in range(9, sheet.max_row + 1)
        ]
        assert set(values) <= ALLOWED_COMPLIANCE
        for seq, text in case["expect"]["compliance"].items():
            expected = text or None
            assert sheet.cell(row=8 + int(seq), column=5).value == expected
