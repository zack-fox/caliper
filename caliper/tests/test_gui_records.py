"""界面新增能力自检：记录表预览 / 生成入口、预览数据与 RecordSheet 一致。"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from app.controller import AppController, ControllerError  # noqa: E402
from app.screens.dialogs import RecordPreviewDialog  # noqa: E402
from app.screens.issues import PREVIEW_COLUMNS, IssuesScreen  # noqa: E402
from app.screens.results import ResultsScreen  # noqa: E402
from app.widgets import ComplianceBadge  # noqa: E402
from core.contracts.enums import AssetType, Importance  # noqa: E402
from core.contracts.verdict import Verdict  # noqa: E402
from core.model.entities import (  # noqa: E402
    Asset, AssetRun, EvidenceAnchor, ItemResult, PointResult, RunResult,
)
from core.records.model import COLUMNS  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _dispose(screen) -> None:
    """先销毁 Qt 对象再结束进程，避免离屏解释器退出时的析构崩溃。"""
    screen.close()
    screen.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QCoreApplication.processEvents()


def _controller_with_run(tmp_path):
    controller = AppController()
    controller.source_path = tmp_path / "project.yaml"
    controller.project = controller.project.model_copy(
        update={
            "project_code": "TEST-001",
            "system_name": "示例系统",
            "output_dir": tmp_path / "out",
        }
    )
    pack = controller.load_pack()
    items = pack.items_for_level(controller.project.level)[:4]
    asset = Asset(
        device_name="示例服务器",
        ip="192.0.2.30",
        importance=Importance.NORMAL,
        guide="三级-安全通用要求",
        asset_type=AssetType.SERVER,
    )
    results = [
        ItemResult(
            item_id=item.item_id,
            seq=item.seq,
            control_point=item.control_point,
            importance=item.importance,
            verdict=Verdict.NON_COMPLIANT if index < 2 else Verdict.COMPLIANT,
            result_text="示例运行结果",
            reviewed=True,
        )
        for index, item in enumerate(items)
    ]
    controller.run_result = RunResult(
        project=controller.project,
        asset_runs=[
            AssetRun(asset=asset, items=results, basis_fingerprint="gui-test")
        ],
    )
    return controller, asset


def test_results_screen_has_record_buttons(qapp, tmp_path):
    controller, _asset = _controller_with_run(tmp_path)
    screen = ResultsScreen(controller)
    assert screen.record_preview_button.text() == "记录表预览"
    assert screen.generate_record_button.text() == "生成记录表"
    screen.close()


def test_record_preview_matches_sheet(qapp, tmp_path):
    controller, asset = _controller_with_run(tmp_path)
    sheet = controller.record_sheet(asset.device_name)
    assert len(sheet.rows) == 4

    dialog = RecordPreviewDialog(sheet)
    assert dialog.stack.currentWidget() is dialog.table
    assert dialog.table.columnCount() == len(COLUMNS) == 9
    assert dialog.table.rowCount() == len(sheet.rows)
    for row_index, row in enumerate(sheet.rows):
        actual = tuple(
            dialog.table.item(row_index, column).text()
            for column in range(len(COLUMNS))
        )
        assert actual == row.values()
    dialog.close()


def test_record_preview_empty_state(qapp):
    dialog = RecordPreviewDialog(None)
    assert dialog.stack.currentWidget() is dialog.empty
    assert "暂无" in dialog.empty.title_label.text()
    dialog.close()


def test_generate_record_book_writes_output(qapp, tmp_path):
    controller, _asset = _controller_with_run(tmp_path)
    target = controller.generate_record_book()
    assert target.exists()
    assert target.parent == tmp_path / "out"


def test_issues_screen_shows_review_and_gate(qapp, tmp_path):
    controller, _asset = _controller_with_run(tmp_path)
    screen = IssuesScreen(controller)
    assert screen.table.columnCount() == len(PREVIEW_COLUMNS) == 9
    assert screen.table.rowCount() > 0
    assert screen.table.cellWidget(0, 8) is not None
    buttons = screen.table.cellWidget(0, 8).findChildren(QPushButton)
    assert any(button.text() in {"确认", "重新确认", "撤销"} for button in buttons)
    assert screen.table.item(0, 7).text()
    screen.close()

    with pytest.raises(ControllerError):
        controller.ensure_major_confirmations()


def _controller_with_domains(tmp_path):
    """服务器 + 数据库两台资产，用于领域页签、筛选与检查器回归。"""
    controller = AppController()
    controller.source_path = tmp_path / "project.yaml"
    controller.project = controller.project.model_copy(
        update={
            "project_code": "TEST-002",
            "system_name": "领域示例系统",
            "output_dir": tmp_path / "out",
        }
    )
    pack = controller.load_pack()
    items = pack.items_for_level(controller.project.level)[:4]
    server = Asset(
        device_name="应用服务器",
        ip="192.0.2.31",
        importance=Importance.NORMAL,
        guide="三级-安全通用要求",
        asset_type=AssetType.SERVER,
    )
    database = Asset(
        device_name="业务数据库",
        ip="192.0.2.32",
        importance=Importance.IMPORTANT,
        guide="三级-安全通用要求",
        asset_type=AssetType.DATABASE,
    )
    server_results = [
        ItemResult(
            item_id=item.item_id,
            seq=item.seq,
            control_point=item.control_point,
            importance=item.importance,
            verdict=Verdict.NON_COMPLIANT if index < 2 else Verdict.COMPLIANT,
            result_text=f"服务器记录 {index}",
            note="现场核查备注" if index == 0 else "",
            points=[
                PointResult(
                    point=1,
                    passed=False,
                    reason="示例实施点",
                    anchors=[
                        EvidenceAnchor(file="capture.log", line=42, snippet="示例片段"),
                        EvidenceAnchor(file="audit.log", line=7, snippet="审计片段"),
                    ],
                )
            ]
            if index == 0
            else [],
            reviewed=index == 0,
        )
        for index, item in enumerate(items)
    ]
    database_results = [
        ItemResult(
            item_id=item.item_id,
            seq=item.seq,
            control_point=item.control_point,
            importance=item.importance,
            verdict=Verdict.COMPLIANT,
            result_text=f"数据库记录 {index}",
        )
        for index, item in enumerate(items)
    ]
    controller.run_result = RunResult(
        project=controller.project,
        asset_runs=[
            AssetRun(asset=server, items=server_results, basis_fingerprint="gui-server"),
            AssetRun(asset=database, items=database_results, basis_fingerprint="gui-db"),
        ],
    )
    return controller


def test_results_record_navigation_and_editor(qapp, tmp_path):
    controller = _controller_with_domains(tmp_path)
    screen = ResultsScreen(controller)

    # 默认选中第一台设备（服务器），记录目录列出 4 条并自动选中首条。
    assert screen.record_list.count() == 4
    assert screen.record_stack.currentWidget() is screen.record_list
    assert screen.record_list.currentRow() == 0

    # 中间阅读区加载核查内容 / 判定标准；右侧编辑器加载结果记录。
    assert screen.current_result is not None
    assert screen.reading_stack.currentIndex() == 1
    assert screen.check_content_label.text()
    assert screen.criteria_label.text()

    # 结果判定为下拉框，五值且当前项为「不符合」。
    assert screen.verdict.count() == 5
    assert screen.verdict.itemText(0) == "符合"
    assert screen.verdict.currentText() == "不符合"

    # 结果记录是 hero 编辑区，已预填自动判定文本。
    assert screen.record_text.toPlainText() == "服务器记录 0"

    # 证据原文只读区（首条带两条锚点）。
    assert "capture.log:42" in screen.evidence_browser.toPlainText()
    assert "audit.log:7" in screen.evidence_browser.toPlainText()
    screen.close()


def test_results_record_list_has_compliance_badge(qapp, tmp_path):
    controller = _controller_with_domains(tmp_path)
    screen = ResultsScreen(controller)
    host = screen.record_list.itemWidget(screen.record_list.item(0))
    assert isinstance(host.findChild(ComplianceBadge), ComplianceBadge)
    screen.close()


def test_compliance_filter_and_no_match_state(qapp, tmp_path):
    controller = _controller_with_domains(tmp_path)
    screen = ResultsScreen(controller)

    assert screen.record_list.count() == 4
    screen.filter_chips["non_compliant"].click()
    assert screen.record_list.count() == 2
    screen.filter_chips["all"].click()
    assert screen.record_list.count() == 4

    screen.search.setText("不存在的控制项")
    assert screen.record_stack.currentWidget() is screen.record_empty
    assert screen.record_empty.title_label.text() == "当前筛选无结果"

    screen.restore_all_filters()
    assert screen.search.text() == ""
    assert screen._filter_key == "all"
    assert screen.record_list.count() == 4
    screen.close()


def test_domain_tabs_filter_tree_and_records(qapp, tmp_path):
    controller = _controller_with_domains(tmp_path)
    screen = ResultsScreen(controller)

    assert screen.domain_tabs.count() == 4
    assert screen.domain_tabs.tabText(0) == "安全通用要求 8/8"
    assert screen.domain_tabs.tabText(2) == "数据库 4/4"

    screen.domain_tabs.setCurrentIndex(2)
    assert screen.domain_tabs.current_key() == "database"
    assert screen._current_run().asset.device_name == "业务数据库"
    assert screen.record_list.count() == 4
    assert screen.current_result is None
    visible_names = [
        screen.asset_tree.topLevelItem(0).child(index).toolTip(0)
        for index in range(screen.asset_tree.topLevelItem(0).childCount())
    ]
    assert visible_names == ["业务数据库"]
    screen.close()


def test_editor_verdict_change_and_result_record(qapp, tmp_path):
    controller = _controller_with_domains(tmp_path)
    screen = ResultsScreen(controller)

    # 手动改判定 + 结果记录后，恢复建议按钮可用（走人工校正留痕）。
    index = screen.verdict.findData("部分符合")
    screen.verdict.setCurrentIndex(index)
    screen.record_text.setPlainText("人工补录的结果记录")

    screen.record_list.setCurrentRow(1)
    assert screen.record_text.toPlainText() == "服务器记录 1"

    screen.record_list.setCurrentRow(0)
    assert screen.current_result.seq == screen._visible_results[0].seq
    assert screen.record_badge.text() in {"待核对", "已确认"}
    screen.close()


def test_no_run_shows_page_empty_state(qapp):
    screen = ResultsScreen(AppController())
    assert screen.page_stack.currentWidget() is screen.page_empty
    assert screen.page_empty.title_label.text() == "尚未生成记录草稿"
    assert "材料与资产" in screen.page_empty.hint_label.text()
    screen.close()
