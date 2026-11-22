"""项目概述页：空状态、指标口径与导航信号。"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.controller import AppController  # noqa: E402
from app.screens.overview import OverviewScreen  # noqa: E402
from app.shell.app_shell import AppShell  # noqa: E402
from core.contracts.verdict import Verdict  # noqa: E402
from core.model.entities import Asset, AssetRun, ItemResult, RunResult  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _controller(tmp_path) -> AppController:
    """把校正库放到临时目录，避免测试读写用户数据目录。"""
    controller = AppController()
    controller.source_path = tmp_path / "project.yaml"
    return controller


def _controller_with_run(tmp_path) -> AppController:
    controller = _controller(tmp_path)
    asset = Asset(
        device_name="概述设备",
        ip="192.0.2.30",
        importance="一般",
        guide="三级-安全通用要求",
    )
    project = controller.project.model_copy(
        update={
            "project_code": "P-OVERVIEW",
            "system_name": "概述示例系统",
            "assets": [asset],
        }
    )
    controller.project = project
    items = [
        ItemResult(
            item_id="L3-CES1-01",
            seq=1,
            control_point="身份鉴别",
            importance="重要",
            verdict=Verdict.COMPLIANT,
        ),
        ItemResult(
            item_id="L3-CES1-02",
            seq=2,
            control_point="身份鉴别",
            importance="重要",
            verdict=Verdict.NON_COMPLIANT,
        ),
        ItemResult(
            item_id="L3-CES1-03",
            seq=3,
            control_point="身份鉴别",
            importance="重要",
            verdict=Verdict.UNCOLLECTED,
        ),
    ]
    controller.run_result = RunResult(
        project=project,
        asset_runs=[AssetRun(asset=asset, items=items)],
    )
    return controller


def test_empty_project_shows_empty_state_without_fake_stats(qapp, tmp_path):
    screen = OverviewScreen(_controller(tmp_path))

    assert screen.stack.currentIndex() == 1
    assert screen.stack.currentWidget() is not None
    for pill in (
        screen.pill_devices,
        screen.pill_checked,
        screen.pill_non_compliant,
        screen.pill_pending,
    ):
        assert pill.value_label.text() == "—"

    summary = " ".join(label.text() for label in screen.summary_fields.values())
    assert "0/0" not in summary
    assert screen.summary_fields["devices"].text() == "—"
    assert screen.summary_fields["project_code"].text() == "未设置"
    assert screen.summary_fields["system_name"].text() == "未设置"

    received: list[str] = []
    screen.navigate.connect(received.append)
    screen.import_button.click()
    assert received == ["evidence"]
    screen.close()


def test_project_without_result_uses_placeholders(qapp, tmp_path):
    controller = _controller(tmp_path)
    asset = Asset(
        device_name="待核查设备",
        ip="192.0.2.31",
        importance="一般",
        guide="三级-安全通用要求",
    )
    controller.project = controller.project.model_copy(
        update={"assets": [asset]}
    )
    screen = OverviewScreen(controller)

    assert screen.stack.currentIndex() == 0
    assert screen.pill_devices.value_label.text() == "1"
    assert screen.pill_checked.value_label.text() == "—"
    assert screen.pill_non_compliant.value_label.text() == "—"
    assert screen.pill_pending.value_label.text() == "—"
    assert screen.step_badges["overview"].text() == "已完成"
    assert screen.step_badges["evidence"].text() == "待处理"
    screen.close()


def test_metrics_match_controller_run_result(qapp, tmp_path):
    controller = _controller_with_run(tmp_path)
    screen = OverviewScreen(controller)

    assert screen.stack.currentIndex() == 0
    assert screen.pill_devices.value_label.text() == "1"
    assert screen.pill_checked.value_label.text() == "2/3"
    assert screen.pill_non_compliant.value_label.text() == "1"
    assert screen.pill_pending.value_label.text() == "0"

    assert screen.summary_fields["project_code"].text() == "P-OVERVIEW"
    assert screen.summary_fields["system_name"].text() == "概述示例系统"
    assert screen.summary_fields["level"].text() == "3 级"
    assert screen.summary_fields["devices"].text() == "1"
    assert screen.step_badges["results"].text() == "已完成"
    assert screen.step_badges["risk"].text() == "已完成"
    screen.close()


def test_quick_and_pending_entries_emit_navigation(qapp, tmp_path):
    controller = _controller_with_run(tmp_path)
    screen = OverviewScreen(controller)
    received: list[str] = []
    screen.navigate.connect(received.append)

    for key in ("evidence", "results", "risk", "export"):
        screen.quick_entries[key].click()
    assert received == ["evidence", "results", "risk", "export"]

    routes = [route for route, _button in screen.pending_actions]
    assert "evidence" in routes
    assert "results" in routes
    assert "issues" in routes
    pending_results = next(
        button
        for route, button in screen.pending_actions
        if route == "results"
    )
    pending_results.click()
    assert received[-1] == "results"
    screen.close()


def test_shell_routes_overview_navigation(qapp, tmp_path):
    shell = AppShell(_controller(tmp_path))
    try:
        overview = shell.pages["overview"]
        overview.navigate.emit("export")
        assert shell.stack.currentWidget() is shell.pages["export"]
    finally:
        shell.close()
