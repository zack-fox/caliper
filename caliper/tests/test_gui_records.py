"""界面新增能力自检：记录表预览 / 生成入口、预览数据与 RecordSheet 一致。"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from app.controller import AppController, ControllerError  # noqa: E402
from app.screens.dialogs import RecordPreviewDialog  # noqa: E402
from app.screens.issues import PREVIEW_COLUMNS, IssuesScreen  # noqa: E402
from app.screens.results import ResultsScreen  # noqa: E402
from core.contracts.enums import AssetType, Importance  # noqa: E402
from core.contracts.verdict import Verdict  # noqa: E402
from core.model.entities import Asset, AssetRun, ItemResult, RunResult  # noqa: E402
from core.records.model import COLUMNS  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


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
