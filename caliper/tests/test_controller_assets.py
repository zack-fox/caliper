"""界面装配层：设备增改删与证据包预览。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.controller import AppController, ControllerError
from core.contracts.verdict import Verdict
from core.items.loader import load_pack
from core.judge.runner import run_project
from core.model.entities import Asset, AssetRun, ItemResult, ProjectConfig, RunResult


def _asset(name: str = "设备A", ip: str = "192.0.2.10", package: str | None = None) -> Asset:
    return Asset(
        device_name=name,
        ip=ip,
        importance="一般",
        guide="三级-安全通用要求",
        asset_type="服务器",
        evidence_package=package,
    )


def test_add_update_and_remove_asset() -> None:
    controller = AppController()
    controller.add_asset(_asset())
    with pytest.raises(ControllerError):
        controller.add_asset(_asset())

    controller.update_asset("设备A", _asset("设备B"))
    assert [asset.device_name for asset in controller.project.assets] == ["设备B"]

    controller.add_asset(_asset("设备C", ip="192.0.2.11"))
    with pytest.raises(ControllerError):
        controller.update_asset("设备B", _asset("设备C", ip="192.0.2.12"))
    with pytest.raises(ControllerError):
        controller.update_asset("不存在的设备", _asset())

    controller.remove_asset("设备B")
    assert [asset.device_name for asset in controller.project.assets] == ["设备C"]


def test_inspect_evidence_states() -> None:
    controller = AppController()
    empty = controller.inspect_evidence(None)
    assert empty.ok is False
    assert "未关联" in empty.message

    missing = controller.inspect_evidence("不存在的包")
    assert missing.ok is False
    assert "不存在" in missing.message


def test_unreviewed_machine_records_cannot_be_exported() -> None:
    controller = AppController()
    asset = _asset()
    result = ItemResult(
        item_id="L3-001",
        seq=1,
        control_point="身份鉴别",
        importance="一般",
        verdict=Verdict.COMPLIANT,
        result_text="自动生成的核查建议",
    )
    controller.run_result = RunResult(
        project=controller.project,
        asset_runs=[AssetRun(asset=asset, items=[result])],
    )

    assert controller.pending_review_records() == [(asset.device_name, 1, "L3-001")]
    for export in (controller.export_result, controller.export_issue, controller.export_major):
        with pytest.raises(ControllerError, match="待人工核对"):
            export()

    result.reviewed = True
    assert controller.pending_review_records() == []
    controller._require_reviewed_records()


def test_run_reports_unmapped_evidence_and_missing_rules(tmp_path) -> None:
    log = tmp_path / "host.log"
    log.write_text(
        "# ===== Ubuntu baseline check =====\n"
        "===== RESULTS (collected) =====\n"
        "===== 99. EXTRA =====\n"
        "[01] Vendor service status\n"
        "  service vendor-agent active\n"
        "===== END OF REPORT =====\n",
        encoding="utf-8",
    )
    asset = _asset(package=str(log))
    project = ProjectConfig(
        level=3,
        check_date=date.today(),
        evidence_root=tmp_path,
        assets=[asset],
    )
    pack = load_pack(Path("packs/linux_os"))
    result = run_project(project, pack, base_dir=tmp_path)
    diagnostics = result.asset_runs[0].diagnostics
    assert any("Vendor service status" in message and "未参与自动判定" in message for message in diagnostics)
    assert any("尚未配置判定规则" in message for message in diagnostics)
