"""材料与资产页离屏回归：双栏结构、就绪度统计与既有动作保留。"""

from __future__ import annotations

import os
import re
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QTableWidget  # noqa: E402

from app.controller import AppController  # noqa: E402
from app.screens.evidence import (  # noqa: E402
    ACTION_COLUMN,
    ASSET_COLUMNS,
    EVIDENCE_COLUMN,
    LEFT_MAX_WIDTH,
    LEFT_MIN_WIDTH,
    EvidenceScreen,
)
from core.model.entities import Asset  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _valid_package(root: Path) -> Path:
    package = root / "device-evidence"
    package.mkdir()
    (package / "capture.log").write_text(
        "# ===== Ubuntu baseline check =====\n"
        "===== RESULTS (collected) =====\n"
        "===== SYSTEM =====\n"
        "[01] Host info\n"
        "  hostname: evidence-host\n"
        "===== END OF REPORT =====\n",
        encoding="utf-8",
    )
    return package


def _asset(device_name: str = "测试设备", ip: str = "192.0.2.40", **kwargs) -> Asset:
    return Asset(
        device_name=device_name,
        ip=ip,
        importance="一般",
        guide="三级-安全通用要求",
        **kwargs,
    )


def _screen(controller: AppController) -> EvidenceScreen:
    screen = EvidenceScreen(controller)
    screen.resize(1280, 800)
    screen.show()
    QApplication.processEvents()
    return screen


def test_empty_state_is_explicit(qapp):
    screen = _screen(AppController())

    assert screen.table.rowCount() == 0
    assert screen.table.columnCount() == len(ASSET_COLUMNS)
    assert screen.readiness_badge.text() == "待导入"
    assert screen.readiness_summary.text() == "尚未导入设备材料"
    assert "尚未导入设备" in screen.table_hint.text()
    assert screen.table_stack.currentWidget() is screen.empty_state
    assert screen.empty_state.title_label.text() == "尚未添加设备"
    screen.close()


def test_added_asset_appears_after_refresh_and_search_filters(qapp):
    controller = AppController()
    controller.add_asset(_asset())
    screen = _screen(controller)

    assert screen.table.rowCount() == 1
    assert "设备 1 台" in screen.readiness_summary.text()
    assert screen.readiness_summary.text() == "设备 1 台 / 已识别材料 0 台 / 需处理 1 台"
    assert screen.table_stack.currentWidget() is screen.table

    screen.search.setText("不存在的设备")
    QApplication.processEvents()
    assert screen.table.rowCount() == 0
    assert screen.table_stack.currentWidget() is screen.empty_state

    screen.search.clear()
    QApplication.processEvents()
    assert screen.table.rowCount() == 1
    assert screen.table_stack.currentWidget() is screen.table

    screen.search.setText("192.0.2.40")
    QApplication.processEvents()
    assert screen.table.rowCount() == 1
    screen.close()


def test_run_button_emits_run_requested(qapp):
    screen = _screen(AppController())
    fired: list[bool] = []
    screen.run_requested.connect(lambda: fired.append(True))

    screen.run_button.click()

    assert fired == [True]
    screen.close()


def test_readiness_uses_real_evidence_counts(qapp, tmp_path):
    _valid_package(tmp_path)
    controller = AppController()
    controller.project = controller.project.model_copy(
        update={
            "evidence_root": tmp_path,
            "assets": [
                Asset(
                    device_name="已关联设备",
                    ip="192.0.2.30",
                    importance="一般",
                    guide="三级-安全通用要求",
                    evidence_package="device-evidence",
                ),
                Asset(
                    device_name="待处理设备",
                    ip="192.0.2.31",
                    importance="一般",
                    guide="三级-安全通用要求",
                ),
            ],
        }
    )
    screen = _screen(controller)

    assert screen.table.rowCount() == 2
    assert screen.readiness_summary.text() == "设备 2 台 / 已识别材料 1 台 / 需处理 1 台"
    assert screen.readiness_badge.text() == "1 台需处理"
    assert screen.readiness_badge.property("tone") == "warn"
    assert "待处理设备（未关联证据）" in screen.readiness_pending.text()
    assert "可核查：" in screen.table.item(0, EVIDENCE_COLUMN).text()
    assert screen.table.cellWidget(0, EVIDENCE_COLUMN) is not None
    assert screen.table.item(0, 5).text() == "1"
    assert screen.table.item(1, EVIDENCE_COLUMN).text() == "未关联证据"
    assert screen.table.item(1, 5).text() == "—"
    screen.close()


def test_layout_keeps_left_column_and_scrollable_table(qapp):
    screen = _screen(AppController())

    assert screen.body.count() == 2
    assert screen.left_panel.minimumWidth() == LEFT_MIN_WIDTH
    assert screen.left_panel.maximumWidth() == LEFT_MAX_WIDTH
    assert screen.body.widget(0) is screen.left_panel
    assert screen.body.widget(1) is screen.right_panel
    assert screen.table.horizontalScrollBar() is not None
    assert screen.table.wordWrap() is False
    assert screen.table.horizontalScrollMode() == QTableWidget.ScrollPerPixel
    screen.close()


def test_existing_actions_and_signals_are_preserved(qapp):
    screen = _screen(AppController())

    assert screen.project_loaded is not None
    assert screen.assets_changed is not None
    assert screen.run_requested is not None
    for name in (
        "apply_form",
        "load_project",
        "save_project",
        "refresh",
        "_on_dropped",
        "_add_asset",
        "_edit_asset",
        "_review_evidence",
        "_remove_asset",
    ):
        assert callable(getattr(screen, name))
    labels = {label.text() for label in screen.findChildren(QLabel)}
    assert {"项目编号", "系统名称", "等保等级", "检查日期", "证据根目录"} <= labels
    for button_name in (
        "save_button",
        "load_button",
        "add_button",
        "import_button",
        "run_button",
    ):
        assert getattr(screen, button_name).isEnabled()

    screen.controller.add_asset(_asset(device_name="操作列设备"))
    screen.refresh()
    action_cell = screen.table.cellWidget(0, ACTION_COLUMN)
    assert action_cell is not None
    texts = {button.text() for button in action_cell.findChildren(QPushButton)}
    assert {"查看材料", "编辑", "删除"} <= texts
    assert all(button.isEnabled() for button in action_cell.findChildren(QPushButton))
    screen.close()


def test_page_has_no_hard_coded_colors():
    source = Path(__file__).resolve().parents[1] / "app" / "screens" / "evidence.py"
    assert re.search(r"#[0-9a-fA-F]{3,8}\b", source.read_text(encoding="utf-8")) is None
