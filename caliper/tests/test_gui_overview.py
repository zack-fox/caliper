"""项目概述页：空状态、指标、步骤状态、待处理清单与导航信号。"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.controller import AppController, MajorReview  # noqa: E402
from app.screens.overview import OverviewScreen  # noqa: E402
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


def _asset() -> Asset:
    return Asset(
        device_name="概述设备",
        ip="192.0.2.40",
        importance="一般",
        guide="三级-安全通用要求",
    )


def _controller_with_run(tmp_path) -> AppController:
    controller = _controller(tmp_path)
    asset = _asset()
    project = controller.project.model_copy(
        update={
            "project_code": "P-GUI-OVERVIEW",
            "system_name": "概述示例系统",
            "assets": [asset],
        }
    )
    controller.project = project
    controller.run_result = RunResult(
        project=project,
        asset_runs=[
            AssetRun(
                asset=asset,
                items=[
                    ItemResult(
                        item_id="L3-CES1-01",
                        seq=1,
                        control_point="身份鉴别",
                        importance="重要",
                        verdict=Verdict.NON_COMPLIANT,
                    ),
                    ItemResult(
                        item_id="L3-CES1-02",
                        seq=2,
                        control_point="身份鉴别",
                        importance="重要",
                        verdict=Verdict.UNCOLLECTED,
                    ),
                ],
            )
        ],
    )
    return controller


def test_empty_project_shows_empty_state_and_placeholders(qapp, tmp_path):
    screen = OverviewScreen(_controller(tmp_path))

    assert screen.stack.currentIndex() == 1
    assert screen.empty.title_label.text() == "尚未导入项目材料"
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
    assert not screen.metric_hint.isHidden()

    received: list[str] = []
    screen.navigate.connect(received.append)
    screen.empty_import.click()
    assert received == ["evidence"]
    screen.close()


def test_metrics_and_pending_items_come_from_run_result(qapp, tmp_path):
    screen = OverviewScreen(_controller_with_run(tmp_path))

    assert screen.stack.currentIndex() == 0
    assert screen.pill_devices.value_label.text() == "1"
    assert screen.pill_checked.value_label.text() == "1/2"
    assert screen.pill_non_compliant.value_label.text() == "1"
    assert screen.pill_pending.value_label.text() == "0"
    assert screen.metric_hint.isHidden()
    assert screen.summary_fields["pack"].text().startswith("linux_os v")

    pending_text = " ".join(label.text() for label in screen.pending_labels)
    assert "未采集" in pending_text
    assert screen.pending_actions

    received: list[str] = []
    screen.navigate.connect(received.append)
    results_button = next(
        button for route, button in screen.pending_actions if route == "results"
    )
    results_button.click()
    assert received == ["results"]
    screen.close()


def test_pending_major_blocks_risk_step(qapp, tmp_path, monkeypatch):
    controller = _controller_with_run(tmp_path)
    review = MajorReview(
        rule_ids=(),
        reducible=False,
        reduction_basis=(),
        scores=(),
        total=0.0,
        threshold=0.0,
        is_candidate=True,
        confirmed=False,
        reason="未确认",
    )
    monkeypatch.setattr(
        controller, "major_reviews", lambda: {("L3-CES1-01", "服务器"): review}
    )

    screen = OverviewScreen(controller)

    assert screen.step_badges["risk"].text() == "阻断"
    assert screen.step_badges["export"].text() == "阻断"
    assert screen.step_badges["results"].text() == "已完成"
    assert screen.pill_pending.value_label.text() == "1"
    assert any("未确认重大隐患" in label.text() for label in screen.pending_labels)

    received: list[str] = []
    screen.navigate.connect(received.append)
    screen.step_buttons["risk"].click()
    assert received == ["risk"]
    screen.close()


def test_quick_entries_emit_routes(qapp, tmp_path):
    screen = OverviewScreen(_controller_with_run(tmp_path))

    assert [button.text() for button in screen.quick_entries.values()] == [
        "导入材料",
        "现场核查",
        "风险与结论",
        "导出交付",
    ]

    received: list[str] = []
    screen.navigate.connect(received.append)
    for key in ("evidence", "results", "risk", "export"):
        screen.quick_entries[key].click()
    assert received == ["evidence", "results", "risk", "export"]
    screen.close()
