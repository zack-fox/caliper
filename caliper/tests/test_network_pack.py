"""网络设备规则域：H3C 三级端到端、厂商隔离、网络会话与采集命令。"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core.contracts.enums import AssetType, Importance
from core.contracts.verdict import Verdict
from core.evidence.capture import load_capture, render_script
from core.evidence.sessionparse import parse_session_text
from core.issues.summary import TextLibrary, build_issue_rows
from core.items.loader import load_pack
from core.judge.runner import run_project
from core.major.major import assess_major
from core.model.entities import Asset, ProjectConfig
from core.remediation import RemediationLibrary, suggest

PACK_DIR = Path(__file__).resolve().parents[1] / "packs" / "network_devices"
CASES_DIR = Path(__file__).resolve().parents[1] / "tests" / "cases"
EVIDENCE_ROOT = CASES_DIR / "network_h3c_l3" / "evidence"
FIXTURE = EVIDENCE_ROOT / "pkg-h3c"


def _project(
    tmp_path: Path,
    vendor: str,
    evidence: str = "pkg-h3c",
    level: int = 3,
    case: str = "network_h3c_l3",
) -> ProjectConfig:
    evidence_root = CASES_DIR / case / "evidence"
    data = {
        "project_code": "示例-网络-001",
        "system_name": "示例网络系统",
        "level": level,
        "check_date": "2026-11-22",
        "evidence_root": str(evidence_root),
        "output_dir": "out",
        "pack_dir": str(PACK_DIR),
        "assets": [
            {
                "device_name": "示例核心交换机",
                "ip": "192.0.2.1",
                "importance": "关键",
                "guide": f"{level}级-安全通用要求",
                "asset_type": "网络设备",
                "vendor": vendor,
                "evidence_package": evidence,
            }
        ],
    }
    path = tmp_path / "project.yaml"
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    from core.store.project import load_project

    project, _ = load_project(path)
    return project


@pytest.fixture()
def h3c_run(tmp_path: Path):
    pack = load_pack(PACK_DIR)
    project = _project(tmp_path, "H3C")
    result = run_project(project, pack)
    return pack, project, result, result.asset_runs[0], pack.items_for_level(3)


def test_pack_exposes_device_rule_domains() -> None:
    pack = load_pack(PACK_DIR)

    assert pack.meta.levels == [2, 3, 4]
    assert set(pack.adapters) == {
        "h3c",
        "huawei",
        "cisco",
        "zte",
        "firewall",
        "waf",
        "ids_ips",
        "vpn",
        "bastion",
        "load_balancer",
        "gap",
        "generic",
    }
    assert pack.meta.default_adapter == "generic"
    assert [len(pack.items_for_level(level)) for level in (2, 3, 4)] == [23, 34, 31]
    for vendor in ("h3c", "huawei", "cisco", "zte"):
        assert len(pack.adapters[vendor].checks.checks) == 6
        assert len(pack.adapters[vendor].rules.rules) >= 48
        assert pack.adapters[vendor].remediation is not None
    assert pack.adapters["generic"].meta.manual_all is True
    assert pack.major_library() is not None


def test_h3c_level3_end_to_end(h3c_run) -> None:
    pack, _, result, run, items = h3c_run

    assert run.adapter == "h3c"
    assert run.os_family == "unknown"
    assert not any("未映射" in line for line in run.diagnostics), run.diagnostics

    assert run.item_by_seq(2).verdict is Verdict.COMPLIANT
    assert run.item_by_seq(18).verdict is Verdict.COMPLIANT
    for seq in (23, 24, 25, 26):
        assert run.item_by_seq(seq).verdict is Verdict.COMPLIANT

    login = run.item_by_seq(1)
    assert login.verdict is Verdict.UNCOLLECTED
    assert {point.point for point in login.points if point.passed} == {2, 3, 4}
    assert {point.point for point in login.points if not point.passed} == {1}

    remote = run.item_by_seq(3)
    assert remote.verdict is Verdict.UNCOLLECTED
    assert {point.point for point in remote.points if point.passed} == {2}

    assert run.item_by_seq(4).verdict is Verdict.UNCOLLECTED
    assert run.item_by_seq(7).verdict is Verdict.UNCOLLECTED
    for seq in (16, 17, 28):
        assert run.item_by_seq(seq).verdict is Verdict.NOT_APPLICABLE

    assert len(result.asset_runs) == 1
    assert pack.items_for_level(3) == items


def test_vendor_commands_are_not_shared(h3c_run, tmp_path: Path) -> None:
    pack, _, _, _, _ = h3c_run
    project = _project(tmp_path, "Juniper")
    run = run_project(project, pack).asset_runs[0]

    assert run.adapter == "generic"
    assert any("不得套用其他厂商命令" in line for line in run.diagnostics)
    assert all(
        item.verdict in {Verdict.UNCOLLECTED, Verdict.NOT_APPLICABLE}
        for item in run.items
    )
    assert not any(item.verdict is Verdict.COMPLIANT for item in run.items)


def test_vendor_adapters_are_isolated() -> None:
    pack = load_pack(PACK_DIR)
    h3c = render_script(load_capture(PACK_DIR / "adapters" / "h3c"), "network", 3)
    huawei = render_script(load_capture(PACK_DIR / "adapters" / "huawei"), "network", 3)
    cisco = render_script(load_capture(PACK_DIR / "adapters" / "cisco"), "network", 3)
    zte = render_script(load_capture(PACK_DIR / "adapters" / "zte"), "network", 3)

    assert "display current-configuration" in h3c
    assert "display current-configuration" in huawei
    assert "show running-config" in cisco
    assert "show running-config" in zte
    assert "display current-configuration" not in cisco
    assert "display current-configuration" not in zte
    assert "show running-config" not in h3c
    assert "show running-config" not in huawei
    assert "undo user-interface password complexity-check disable" not in h3c
    assert "password-control" not in huawei
    for vendor in ("h3c", "huawei", "cisco", "zte"):
        assert pack.adapters[vendor].meta.levels == [2, 3, 4]


@pytest.mark.parametrize(
    ("vendor", "case", "package"),
    [
        ("H3C", "network_h3c_l3", "pkg-h3c"),
        ("HUAWEI", "network_huawei_l3", "pkg-huawei"),
        ("Cisco", "network_cisco_l3", "pkg-cisco"),
        ("中兴ZTE", "network_zte_l3", "pkg-zte"),
    ],
)
def test_vendor_level3_end_to_end(tmp_path, vendor, case, package) -> None:
    pack = load_pack(PACK_DIR)
    project = _project(tmp_path, vendor, package, 3, case)
    run = run_project(project, pack).asset_runs[0]

    assert run.adapter in {"h3c", "huawei", "cisco", "zte"}
    assert not any("未映射" in line for line in run.diagnostics), run.diagnostics
    items = {item.seq: item for item in pack.items_for_level(3)}
    for item in run.items:
        if items[item.seq].mode != "auto":
            continue
        for point in item.points:
            if point.manual:
                continue
            assert point.passed is True, (vendor, item.seq, point.point, point.reason)
    assert run.item_by_seq(2).verdict is Verdict.COMPLIANT
    assert run.item_by_seq(18).verdict is Verdict.COMPLIANT
    for seq in (23, 24, 25, 26):
        assert run.item_by_seq(seq).verdict is Verdict.COMPLIANT
    remote_point = next(
        point for point in run.item_by_seq(3).points if point.point == 2
    )
    assert remote_point.passed is True
    assert run.item_by_seq(1).verdict is Verdict.UNCOLLECTED
    assert run.item_by_seq(7).verdict is Verdict.UNCOLLECTED


def test_vendor_cannot_consume_other_vendor_evidence(tmp_path) -> None:
    pack = load_pack(PACK_DIR)
    project = _project(tmp_path, "HUAWEI", "pkg-h3c", 3, "network_h3c_l3")
    run = run_project(project, pack).asset_runs[0]

    assert run.adapter == "huawei"
    assert not any(item.verdict is Verdict.COMPLIANT for item in run.items)


@pytest.mark.parametrize("level", [2, 4])
def test_h3c_level2_and_level4_end_to_end(tmp_path, level) -> None:
    pack = load_pack(PACK_DIR)
    project = _project(tmp_path, "H3C", "pkg-h3c", level, "network_h3c_l3")
    run = run_project(project, pack).asset_runs[0]

    assert len(run.items) == {2: 23, 4: 31}[level]
    items = {item.seq: item for item in pack.items_for_level(level)}
    for item in run.items:
        if items[item.seq].mode != "auto":
            continue
        for point in item.points:
            if point.manual:
                continue
            assert point.passed is True, (level, item.seq, point.point, point.reason)
    assert run.item_by_seq(2).verdict is Verdict.COMPLIANT
    remote_point = next(
        point for point in run.item_by_seq(3).points if point.point == 2
    )
    assert remote_point.passed is True
    if level == 2:
        for seq in (11, 12, 19):
            assert run.item_by_seq(seq).verdict is Verdict.NOT_APPLICABLE
        assert run.item_by_seq(13).verdict is Verdict.COMPLIANT
        assert run.item_by_seq(17).verdict is Verdict.COMPLIANT
    else:
        for seq in (16, 17, 29):
            assert run.item_by_seq(seq).verdict is Verdict.NOT_APPLICABLE
        assert run.item_by_seq(18).verdict is Verdict.COMPLIANT
        for seq in (23, 24, 26, 27):
            assert run.item_by_seq(seq).verdict is Verdict.COMPLIANT


def test_zte_password_complexity_remains_manual(tmp_path) -> None:
    pack = load_pack(PACK_DIR)
    project = _project(tmp_path, "中兴ZTE", "pkg-zte", 3, "network_zte_l3")
    run = run_project(project, pack).asset_runs[0]

    auth = run.item_by_seq(1)
    assert auth.verdict is Verdict.UNCOLLECTED
    assert {point.point for point in auth.points if point.passed} == {2, 3}
    assert {point.point for point in auth.points if point.passed is None} == {1, 4}


def test_h3c_failure_generates_issue_and_remediation(h3c_run, tmp_path: Path) -> None:
    pack, _, _, _, items = h3c_run
    broken = tmp_path / "evidence" / "broken"
    (broken / "raw").mkdir(parents=True)
    text = (FIXTURE / "raw" / "h3c-l3.log").read_text(encoding="utf-8")
    # 保留 ACL 定义、去掉绑定到管理终端的 inbound 引用：应判不符合而不是未采集。
    text = text.replace("\n  acl 2001 inbound", "")
    (broken / "raw" / "h3c-l3.log").write_text(text, encoding="utf-8")

    project = _project(tmp_path, "H3C", evidence="broken")
    project.evidence_root = tmp_path / "evidence"
    run = run_project(project, pack).asset_runs[0]

    assert run.item_by_seq(18).verdict is Verdict.NON_COMPLIANT

    issues = build_issue_rows(
        run_project(project, pack), items, TextLibrary(pack.all_texts())
    )
    target = [issue for issue in issues if issue.seq == 18]
    assert target, "不符合项应生成安全问题记录"
    assert target[0].asset_type == "网络设备"

    library = RemediationLibrary.load(PACK_DIR, items)
    advices = suggest(library, items, run)
    assert any(advice.seq == 18 for advice in advices)


def test_h3c_high_risk_library_is_wired(h3c_run) -> None:
    pack, _, _, _, _ = h3c_run
    library = pack.major_library()
    assert library is not None
    candidates = assess_major(pack.all_high_risk(), library)
    assert len(candidates) == 16
    assert all(len(candidate.scores) == 3 for candidate in candidates)


def test_network_capture_renders_read_only_commands() -> None:
    library = load_capture(PACK_DIR / "adapters" / "h3c")
    script = render_script(library, "network", 3)

    assert "display current-configuration" in script
    assert "display ssh server status" in script
    assert "#!/usr/bin/env bash" not in script
    assert "仅供已授权环境使用" in script

    pack = load_pack(PACK_DIR)
    titles = {check.title for check in pack.adapters["h3c"].checks.checks}
    sections = {rule.section for rule in library.rules_for("network", 3)}
    assert sections == titles


def test_h3c_session_prompts_and_write_guard() -> None:
    pack = load_pack(PACK_DIR)
    text = """\
<H3C>display ssh server status
 SSH server: Enable
<H3C>display telnet server status
 Telnet server: Disable
<H3C>reboot
<H3C>display ip https
 HTTPS server: Enable
"""
    outcome = parse_session_text(text, "h3c-session.log", pack.adapters["h3c"].checks)

    assert [block.title for block in outcome.blocks] == ["H3C 远程管理加密"]
    assert any("非只读" in warning for warning in outcome.warnings)


SECURITY_DEVICES = [
    ("防火墙", "firewall"),
    ("WAF", "waf"),
    ("IDS/IPS", "ids_ips"),
    ("VPN", "vpn"),
    ("堡垒机", "bastion"),
    ("负载均衡", "load_balancer"),
    ("网闸", "gap"),
]


@pytest.mark.parametrize(("device", "key"), SECURITY_DEVICES)
def test_security_device_templates_are_manual_only(tmp_path, device, key) -> None:
    pack = load_pack(PACK_DIR)
    adapter, matched = pack.resolve_adapter(device)

    assert matched is True
    assert adapter is not None and adapter.key == key
    assert adapter.meta.manual_all is True
    assert adapter.meta.levels == [2, 3, 4]
    # 没有厂商指导书时不编造采集命令或自动判定规则。
    assert adapter.checks.checks == []
    assert adapter.rules.rules == []
    assert not (PACK_DIR / "adapters" / key / "capture.yaml").exists()
    assert adapter.remediation is not None
    levels = {level for rule in adapter.remediation.rules for level in rule.applies_to.level}
    assert levels == {2, 3, 4}

    project = _project(tmp_path, device, "pkg-h3c", 3, "network_h3c_l3")
    run = run_project(project, pack).asset_runs[0]
    assert run.adapter == key
    assert all(
        item.verdict in {Verdict.UNCOLLECTED, Verdict.NOT_APPLICABLE}
        for item in run.items
    )
    assert any(
        "需人工核查" in (item.note or "")
        for item in run.items
        if item.verdict is Verdict.UNCOLLECTED
    )


def test_unknown_security_device_falls_back_to_generic(tmp_path) -> None:
    pack = load_pack(PACK_DIR)
    adapter, matched = pack.resolve_adapter("某未知安全设备厂商")

    assert matched is False
    assert adapter is not None and adapter.key == "generic"
    project = _project(tmp_path, "某未知安全设备厂商", "pkg-h3c", 3, "network_h3c_l3")
    run = run_project(project, pack).asset_runs[0]
    assert run.adapter == "generic"
    assert not any(item.verdict is Verdict.COMPLIANT for item in run.items)


def test_network_asset_type_maps_to_network_family() -> None:
    assert AssetType.NETWORK_DEVICE.family == "network"
    assert AssetType.SECURITY_DEVICE.family == "network"
    asset = Asset(
        device_name="示例设备",
        ip="192.0.2.9",
        importance=Importance.IMPORTANT,
        guide="三级-安全通用要求",
        asset_type=AssetType.SECURITY_DEVICE,
        vendor="H3C",
    )
    assert asset.family == "network"
