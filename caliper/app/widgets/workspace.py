"""工作台通用组件：工具栏、筛选片、指标胶囊、安全域页签、分栏、
侧边检查器、状态栏与合规徽章。

只做外观与布局组合，不承载业务逻辑，供各页面复用。
"""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from app.theme.tokens import INSPECTOR_WIDTH
from app.widgets.base import Badge


class Toolbar(QFrame):
    """工作台工具栏：左侧操作区 + 弹性留白 + 右侧操作区。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("workspace_toolbar")
        outer = QHBoxLayout(self)
        outer.setContentsMargins(12, 6, 12, 6)
        outer.setSpacing(8)

        self._left = QHBoxLayout()
        self._left.setSpacing(8)
        self._right = QHBoxLayout()
        self._right.setSpacing(8)
        outer.addLayout(self._left)
        outer.addStretch(1)
        outer.addLayout(self._right)

        self.search: QLineEdit | None = None

    def add_left(self, widget: QWidget) -> QWidget:
        self._left.addWidget(widget)
        return widget

    def add_right(self, widget: QWidget) -> QWidget:
        self._right.addWidget(widget)
        return widget

    def add_search(self, placeholder: str = "搜索") -> QLineEdit:
        edit = QLineEdit()
        edit.setObjectName("toolbar_search")
        edit.setPlaceholderText(placeholder)
        edit.setClearButtonEnabled(True)
        self._left.addWidget(edit)
        self.search = edit
        return edit


class FilterChip(QPushButton):
    """可勾选的筛选片；``key`` 用于外部识别筛选项。"""

    def __init__(self, text: str, key: str, parent=None) -> None:
        super().__init__(text, parent)
        self.key = key
        self.setObjectName("filter_chip")
        self.setCheckable(True)


class MetricPill(QFrame):
    """指标胶囊：标签 + 数值。"""

    def __init__(self, label: str, value: str = "—", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("metric_pill")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 3, 10, 3)
        layout.setSpacing(6)

        self.label_label = QLabel(label)
        self.label_label.setObjectName("metric_pill_label")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("metric_pill_value")
        layout.addWidget(self.label_label)
        layout.addWidget(self.value_label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


class DomainTabs(QTabBar):
    """安全域页签：显示 ``标签 已核查/总数``，切换时发出当前 key。"""

    domain_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("domain_tabs")
        self.setDrawBase(False)
        self.setExpanding(False)
        self._keys: list[str] = []
        self.currentChanged.connect(self._emit_current)

    def set_domains(self, domains: Iterable[tuple[str, str, int, int]]) -> None:
        self.blockSignals(True)
        try:
            while self.count():
                self.removeTab(0)
            self._keys = []
            for key, label, checked, total in domains:
                self.addTab(f"{label} {checked}/{total}")
                self._keys.append(key)
            if self._keys:
                self.setCurrentIndex(0)
        finally:
            self.blockSignals(False)

    def _emit_current(self, index: int) -> None:
        if 0 <= index < len(self._keys):
            self.domain_changed.emit(self._keys[index])

    def current_key(self) -> str:
        index = self.currentIndex()
        return self._keys[index] if 0 <= index < len(self._keys) else ""


class SplitPane(QSplitter):
    """主区 + 侧栏的横向分栏；侧栏可显隐，不强制最小宽度。"""

    def __init__(self, parent=None) -> None:
        super().__init__(Qt.Horizontal, parent)
        self.setObjectName("split_pane")
        self.setChildrenCollapsible(False)
        self.setHandleWidth(1)
        self._main: QWidget | None = None
        self._side: QWidget | None = None
        self._side_width = INSPECTOR_WIDTH

    def set_main(self, widget: QWidget) -> QWidget:
        if widget is self._main:
            return widget
        if self._main is not None:
            self._main.setParent(None)
        self._main = widget
        self.insertWidget(0, widget)
        self.setStretchFactor(0, 1)
        self._apply_sizes()
        return widget

    def set_side(self, widget: QWidget, width: int | None = None) -> QWidget:
        if width is not None:
            self._side_width = int(width)
        if widget is self._side:
            return widget
        if self._side is not None:
            self._side.setParent(None)
        self._side = widget
        widget.setMinimumWidth(0)
        self.addWidget(widget)
        self.setStretchFactor(self.indexOf(widget), 0)
        self._apply_sizes()
        return widget

    def set_side_visible(self, visible: bool) -> None:
        if self._side is not None:
            self._side.setVisible(visible)

    def _apply_sizes(self) -> None:
        if self._main is None or self._side is None:
            return
        total = max(self.width(), self._side_width + 320)
        self.setSizes([total - self._side_width, self._side_width])


class InspectorDrawer(QFrame):
    """右侧检查器：头部标题 + 关闭按钮，主体为可切换的堆叠视图。"""

    closed = Signal()

    def __init__(self, title: str = "详情", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inspector")
        self.setFixedWidth(INSPECTOR_WIDTH)

        self._default_title = title
        self._views: dict[str, int] = {}
        self._titles: dict[str, str] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QFrame()
        header.setObjectName("inspector_header")
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(14, 8, 10, 8)
        header_row.setSpacing(8)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("inspector_title")
        self.close_button = QPushButton("×")
        self.close_button.setObjectName("inspector_close")
        self.close_button.setFixedSize(24, 24)
        self.close_button.clicked.connect(self.closed.emit)
        header_row.addWidget(self.title_label)
        header_row.addStretch(1)
        header_row.addWidget(self.close_button)
        outer.addWidget(header)

        self.body = QStackedWidget()
        outer.addWidget(self.body, 1)

    def add_view(self, key: str, title: str, widget: QWidget) -> QWidget:
        index = self.body.addWidget(widget)
        self._views[key] = index
        self._titles[key] = title
        if self.body.count() == 1:
            self.title_label.setText(title)
        return widget

    def set_view(self, key: str) -> None:
        index = self._views.get(key)
        if index is None:
            return
        self.body.setCurrentIndex(index)
        self.title_label.setText(self._titles.get(key, self._default_title))

    def current_key(self) -> str:
        index = self.body.currentIndex()
        for key, view_index in self._views.items():
            if view_index == index:
                return key
        return ""


class StatusBar(QFrame):
    """底部状态栏：左侧弹性段区 + 右侧固定段区。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("statusbar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 8, 0)
        layout.setSpacing(0)
        self._left = QHBoxLayout()
        self._left.setSpacing(4)
        self._right = QHBoxLayout()
        self._right.setSpacing(4)
        layout.addLayout(self._left, 1)
        layout.addLayout(self._right, 0)
        self._segments: dict[str, QLabel] = {}

    def set_segment(self, key: str, text: str, side: str = "left") -> QLabel:
        label = self._segments.get(key)
        if label is None:
            label = QLabel()
            label.setObjectName("status_segment")
            self._segments[key] = label
            (self._right if side == "right" else self._left).addWidget(label)
        label.setText(text)
        return label

    def remove_segment(self, key: str) -> None:
        label = self._segments.pop(key, None)
        if label is None:
            return
        self._left.removeWidget(label)
        self._right.removeWidget(label)
        label.setParent(None)
        label.deleteLater()


COMPLIANCE_TONES: dict[str, str] = {
    "符合": "ok",
    "部分符合": "warn",
    "不符合": "bad",
    "不适用": "neutral",
    "未采集": "info",
}


class ComplianceBadge(Badge):
    """记录表三值口径徽章：文字与色调同步映射。"""

    def __init__(self, text: str = "未采集", parent=None) -> None:
        super().__init__(text, COMPLIANCE_TONES.get(text, "neutral"), parent)

    def set_compliance(self, text: str) -> None:
        self.setText(text)
        self.set_tone(COMPLIANCE_TONES.get(text, "neutral"))
