"""操作系统规则域：Linux/Ubuntu 端到端、平台隔离、人工核查与风险整改。"""

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
from core.remediation import suggest

PACK_DIR = Path(__file__).resolve().parents[1] / "packs" / "os_devices"
CASES_DIR = Path(__file__).resolve().parents[1] / "tests" / "cases"


def _project(
    tmp_path: Path,
    vendor: str,
    level: int = 3,
    evidence: str = "pkg-linux",
    case: str = "os_linux_l3",
    evidence_root: Path | None = None,
) -> Path:
    data = {
        "project_code": "示例-操作系统-001",
        "system_name": "示例操作系统",
        "level": level,
        "check_date": "2026-11-22",
        "evidence_root": str(evidence_root or (CASES_DIR / case / "evidence")),
        "output_dir": "out",
        "pack_dir": str(PACK_DIR),
        "assets": [
            {
                "device_name": "示例服务器",
                "ip": "192.0.2.20",
                "importance": "一般",
                "guide": f"{level}级-安全通用要求",
                "asset_type": "服务器",
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


def test_pack_exposes_os_rule_domains() -> None:
    pack = load_pack(PACK_DIR)

    assert pack.meta.levels == [2, 3, 4]
    assert set(pack.adapters) == {
        "linux",
        "ubuntu",
        "windows",
        "aix",
        "solaris",
        "esxi",
        "generic",
    }
    assert pack.meta.default_adapter == "generic"
    assert [len(pack.items_for_level(level)) for level in (2, 3, 4)] == [23, 34, 34]

    assert len(pack.adapters["linux"].checks.checks) == 44
    assert len(pack.adapters["linux"].rules.rules) == 101
    assert len(pack.adapters["ubuntu"].checks.checks) == 43
    assert len(pack.adapters["ubuntu"].rules.rules) == 99

    for key in ("windows", "aix", "solaris", "esxi", "generic"):
        adapter = pack.adapters[key]
        assert adapter.meta.manual_all is True
        assert adapter.checks.checks == []
        assert adapter.rules.rules == []
        assert adapter.remediation is not None
        levels = {level for rule in adapter.remediation.rules for level in rule.applies_to.level}
        assert levels == {2, 3, 4}

    assert pack.major_library() is not None
    assert len(pack.adapters["linux"].high_risk) == 16


def test_checks_map_binds_all_levels() -> None:
    pack = load_pack(PACK_DIR)

    for key in ("linux", "ubuntu"):
        levels = {
            bind.level
            for check in pack.adapters[key].checks.checks
            for bind in check.binds
        }
        assert levels == {2, 3, 4}


def test_linux_level3_end_to_end(tmp_path: Path) -> None:
    pack, _, run = _run(tmp_path, "Linux")

    assert run.adapter == "linux"
    assert not any("未映射" in line for line in run.diagnostics), run.diagnostics

    assert run.item_by_seq(1).verdict is Verdict.COMPLIANT
    assert all(point.passed for point in run.item_by_seq(1).points)

    default_accounts = run.item_by_seq(6)
    assert default_accounts.verdict is Verdict.UNCOLLECTED
    assert next(
        point for point in default_accounts.points if point.point == 1
    ).passed is True
    assert {point.point for point in default_accounts.points if point.manual} == {2}

    separation = run.item_by_seq(8)
    assert separation.verdict is Verdict.UNCOLLECTED
    assert {point.point for point in separation.points if point.passed} == {1, 2}
    assert {point.point for point in separation.points if point.manual} == {3}

    authorized = run.item_by_seq(9)
    assert authorized.verdict is Verdict.UNCOLLECTED
    assert {point.point for point in authorized.points if point.passed} == {1, 2}
    assert {point.point for point in authorized.points if point.manual} == {3}

    assert run.item_by_seq(18).verdict is Verdict.COMPLIANT


def test_ubuntu_level3_end_to_end(tmp_path: Path) -> None:
    pack, _, run = _run(tmp_path, "Ubuntu")

    assert run.adapter == "ubuntu"
    assert not any("未映射" in line for line in run.diagnostics), run.diagnostics
    assert run.item_by_seq(1).verdict is Verdict.COMPLIANT
    assert run.item_by_seq(6).verdict is Verdict.UNCOLLECTED
    assert run.item_by_seq(8).verdict is Verdict.UNCOLLECTED
    assert run.item_by_seq(9).verdict is Verdict.UNCOLLECTED
    assert run.item_by_seq(18).verdict is Verdict.COMPLIANT

    # Ubuntu 不使用 SELinux，对应实施点必须显式转为人工核查。
    security_label = run.item_by_seq(11)
    assert next(
        point for point in security_label.points if point.point == 1
    ).manual is True
    manual = pack.adapters["ubuntu"].meta.manual_points_by_level[3][11]
    assert {point.point for point in manual} == {1}


@pytest.mark.parametrize("level", [2, 4])
@pytest.mark.parametrize(("vendor", "adapter"), [("Linux", "linux"), ("Ubuntu", "ubuntu")])
def test_os_level2_and_level4_end_to_end(
    tmp_path: Path, level: int, vendor: str, adapter: str
) -> None:
    pack, _, run = _run(tmp_path, vendor, level=level)

    assert run.adapter == adapter
    assert len(run.items) == {2: 23, 4: 34}[level]
    assert not any("未映射" in line for line in run.diagnostics), run.diagnostics
    items = {item.seq: item for item in pack.items_for_level(level)}
    for item in run.items:
        if items[item.seq].mode != "auto":
            continue
        for point in item.points:
            if point.manual:
                continue
            assert point.passed is not False, (
                level,
                vendor,
                item.seq,
                point.point,
                point.reason,
            )


def test_platform_commands_are_isolated() -> None:
    linux = render_script(load_capture(PACK_DIR / "adapters" / "linux"), "server", 3)
    ubuntu = render_script(load_capture(PACK_DIR / "adapters" / "ubuntu"), "server", 3)

    assert "getenforce" in linux
    assert "rpm -qa" in linux
    assert "dnf check-update" in linux
    assert "apt " not in linux
    assert "dpkg -l" not in linux

    assert "apt list" in ubuntu
    assert "dpkg -l" in ubuntu
    assert "getenforce" not in ubuntu
    assert "rpm -qa" not in ubuntu
    assert "dnf check-update" not in ubuntu

    pack = load_pack(PACK_DIR)
    linux_titles = {check.title for check in pack.adapters["linux"].checks.checks}
    ubuntu_titles = {check.title for check in pack.adapters["ubuntu"].checks.checks}
    assert "SELinux status" in linux_titles
    assert "SELinux status" not in ubuntu_titles


@pytest.mark.parametrize("vendor", ["Windows", "AIX", "Solaris", "VMware ESXi", "OtherOS"])
def test_manual_platforms_do_not_apply_linux_commands(
    tmp_path: Path, vendor: str
) -> None:
    pack, _, run = _run(tmp_path, vendor)

    assert run.adapter in {"windows", "aix", "solaris", "esxi", "generic"}
    assert all(
        item.verdict in {Verdict.UNCOLLECTED, Verdict.NOT_APPLICABLE}
        for item in run.items
    )
    assert not any(item.verdict is Verdict.COMPLIANT for item in run.items)
    if run.adapter == "generic":
        assert any("不得套用其他厂商命令" in line for line in run.diagnostics)


def test_linux_failure_generates_issue_and_remediation(tmp_path: Path) -> None:
    pack = load_pack(PACK_DIR)
    items = pack.items_for_level(3)

    broken = tmp_path / "evidence" / "broken" / "raw"
    broken.mkdir(parents=True)
    text = (
        CASES_DIR / "os_linux_l3" / "evidence" / "pkg-linux" / "raw" / "linux-l3.log"
    ).read_text(encoding="utf-8")
    text = (
        text.replace("no duplicate uid", "1000")
        .replace("UID=0: root", "UID=0: root, app")
        .replace("no empty-password account", "app empty-password")
        .replace("minlen=10", "minlen=6")
        .replace("PASS_MAX_DAYS 90", "PASS_MAX_DAYS 9999")
        .replace("pam_unix.so", "pam_unknown.so")
    )
    (broken / "linux-l3.log").write_text(text, encoding="utf-8")

    project_path = _project(
        tmp_path,
        "Linux",
        evidence="broken",
        evidence_root=tmp_path / "evidence",
    )
    from core.store.project import load_project

    project, _ = load_project(project_path)
    result = run_project(project, pack)
    run = result.asset_runs[0]

    assert run.item_by_seq(1).verdict is Verdict.NON_COMPLIANT

    issues = build_issue_rows(result, items, TextLibrary(pack.all_texts()))
    target = [issue for issue in issues if issue.seq == 1]
    assert target, "不符合项应生成安全问题记录"
    assert target[0].asset_type == "服务器"

    library = pack.remediation_library("linux")
    assert library is not None
    advices = suggest(library, items, run)
    assert any(advice.seq == 1 for advice in advices)


def test_high_risk_bindings_are_level_specific() -> None:
    pack = load_pack(PACK_DIR)
    library = pack.major_library()
    assert library is not None

    entries = pack.adapters["linux"].high_risk
    counts = {level: len(pack.items_for_level(level)) for level in (2, 3, 4)}
    for entry in entries:
        for level, seqs in (entry.get("binds") or {}).items():
            level = int(level)
            assert 1 <= level <= 4
            assert all(1 <= seq <= counts[level] for seq in seqs), (
                entry["hr_id"],
                level,
                seqs,
            )

    candidates = assess_major(entries, library)
    assert len(candidates) == 16
    assert all(len(candidate.scores) == 3 for candidate in candidates)
