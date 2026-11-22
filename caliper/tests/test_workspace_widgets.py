"""工作台组件自检：离屏实例化、合规色调、域页签、检查器与状态栏。"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QWidget  # noqa: E402

from app.widgets.workspace import (  # noqa: E402
    ComplianceBadge,
    DomainTabs,
    FilterChip,
    InspectorDrawer,
    MetricPill,
    SplitPane,
    StatusBar,
    Toolbar,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_all_workspace_widgets_instantiate(qapp):
    toolbar = Toolbar()
    assert toolbar.objectName() == "workspace_toolbar"
    search = toolbar.add_search("搜索控制点")
    assert isinstance(search, QLineEdit)
    assert search.objectName() == "toolbar_search"

    chip = FilterChip("高风险", "high")
    assert chip.isCheckable()
    assert chip.objectName() == "filter_chip"
    assert chip.key == "high"

    pill = MetricPill("已核查", "0")
    pill.set_value("12")
    assert pill.objectName() == "metric_pill"

    tabs = DomainTabs()
    assert tabs.objectName() == "domain_tabs"

    pane = SplitPane()
    pane.set_main(QWidget())
    pane.set_side(QWidget(), 320)
    pane.set_side_visible(False)
    pane.set_side_visible(True)

    drawer = InspectorDrawer()
    assert drawer.objectName() == "inspector"

    status = StatusBar()
    assert status.objectName() == "statusbar"

    badge = ComplianceBadge("符合")
    assert badge.objectName() == "badge"

    for widget in (toolbar, chip, pill, tabs, pane, drawer, status, badge):
        widget.close()


def test_compliance_badge_maps_tone(qapp):
    assert ComplianceBadge("不符合").property("tone") == "bad"
    assert ComplianceBadge("符合").property("tone") == "ok"
    assert ComplianceBadge("部分符合").property("tone") == "warn"
    assert ComplianceBadge("不适用").property("tone") == "neutral"
    assert ComplianceBadge("未采集").property("tone") == "info"
    assert ComplianceBadge("其他").property("tone") == "neutral"


def test_domain_tabs_emit_and_expose_key(qapp):
    tabs = DomainTabs()
    tabs.set_domains(
        [
            ("physical", "安全物理环境", 3, 10),
            ("network", "安全通信网络", 1, 8),
        ]
    )
    assert tabs.current_key() == "physical"
    assert tabs.tabText(0) == "安全物理环境 3/10"

    seen: list[str] = []
    tabs.domain_changed.connect(seen.append)
    tabs.setCurrentIndex(1)
    assert seen == ["network"]
    assert tabs.current_key() == "network"
    tabs.close()


def test_inspector_drawer_switches_views(qapp):
    drawer = InspectorDrawer("检查器")
    first = QWidget()
    second = QWidget()
    drawer.add_view("detail", "详情", first)
    drawer.add_view("evidence", "证据", second)

    assert drawer.current_key() == "detail"
    drawer.set_view("evidence")
    assert drawer.current_key() == "evidence"
    assert drawer.body.currentWidget() is second
    assert drawer.title_label.text() == "证据"

    closed: list[bool] = []
    drawer.closed.connect(lambda: closed.append(True))
    drawer.close_button.click()
    assert closed == [True]
    drawer.close()


def test_status_bar_segments(qapp):
    status = StatusBar()
    status.set_segment("count", "共 12 条记录")
    status.set_segment("mode", "离线", side="right")

    texts = [label.text() for label in status.findChildren(QLabel, "status_segment")]
    assert "共 12 条记录" in texts
    assert "离线" in texts

    status.set_segment("count", "共 13 条记录")
    assert status.findChildren(QLabel, "status_segment")[0].text() == "共 13 条记录"

    status.remove_segment("mode")
    texts = [label.text() for label in status.findChildren(QLabel, "status_segment")]
    assert "离线" not in texts
    status.close()
