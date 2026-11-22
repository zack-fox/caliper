"""可折叠分组侧栏：品牌标记、项目 / 工具分组导航与规则包信息。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.shell.navigation import NAV_STEPS, NavStep
from app.theme.theme import restyle
from app.theme.tokens import SIDEBAR_EXPANDED_WIDTH, SIDEBAR_WIDTH

# 折叠态显示两字缩写，完整名称保留在 tooltip 中。
COMPACT_LABELS: dict[str, str] = {
    "overview": "概览",
    "evidence": "材料",
    "results": "核查",
    "issues": "问题",
    "risk": "风险",
    "export": "导出",
    "rules": "规则",
}


class Sidebar(QFrame):
    navigate = Signal(str)
    collapsed_changed = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self._collapsed = False
        self._current = ""
        self._pack_name = "规则包"
        self._pack_version = ""
        self._buttons: dict[str, QToolButton] = {}
        self._group_frames: list[QWidget] = []

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 10, 8, 10)
        self._layout.setSpacing(6)

        self._build_brand()
        self._build_groups()
        self._layout.addStretch(1)
        self._build_footer()
        self.set_collapsed(False)
        self.set_current("overview")

    # ---- 构建 ----
    def _build_brand(self) -> None:
        self._brand = QWidget()
        row = QHBoxLayout(self._brand)
        row.setContentsMargins(6, 0, 6, 0)
        row.setSpacing(6)

        self.mark = QLabel("C")
        self.mark.setObjectName("rail_mark")
        self.mark.setAlignment(Qt.AlignCenter)
        self.mark.setFixedSize(32, 32)
        row.addWidget(self.mark)
        row.addStretch(1)

        self.toggle_button = QPushButton("«")
        self.toggle_button.setObjectName("sidebar_toggle")
        self.toggle_button.setFixedSize(24, 24)
        self.toggle_button.setCursor(Qt.PointingHandCursor)
        self.toggle_button.setToolTip("折叠侧栏")
        self.toggle_button.clicked.connect(self.toggle)
        row.addWidget(self.toggle_button)

        self._layout.addWidget(self._brand)
        self._layout.addSpacing(8)

    def _build_groups(self) -> None:
        sections: list[str] = []
        for step in NAV_STEPS:
            if step.section not in sections:
                sections.append(step.section)
        for section in sections:
            frame = QWidget()
            group = QVBoxLayout(frame)
            group.setContentsMargins(0, 0, 0, 6)
            group.setSpacing(2)

            caption = QLabel(section)
            caption.setObjectName("nav_section")
            caption.setProperty("section", section)
            group.addWidget(caption)
            group.addSpacing(2)

            for step in NAV_STEPS:
                if step.section == section:
                    group.addWidget(self._make_button(step))

            self._group_frames.append(frame)
            self._layout.addWidget(frame)

    def _make_button(self, step: NavStep) -> QToolButton:
        button = QToolButton()
        button.setObjectName("nav")
        button.setCheckable(True)
        button.setAutoExclusive(True)
        button.setCursor(Qt.PointingHandCursor)
        button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        button.setMinimumHeight(34)
        button.setToolTip(f"{step.label} · {step.hint}")
        button.clicked.connect(lambda _checked=False, route=step.key: self.navigate.emit(route))
        button.setProperty("nav_key", step.key)
        self._buttons[step.key] = button
        return button

    def _build_footer(self) -> None:
        self.footer = QFrame()
        self.footer.setObjectName("sidebar_footer")
        box = QVBoxLayout(self.footer)
        box.setContentsMargins(8, 6, 8, 6)
        box.setSpacing(2)

        key = QLabel("规则包")
        key.setObjectName("sidebar_footer_key")
        self.pack_value = QLabel("未加载")
        self.pack_value.setObjectName("sidebar_footer_value")
        self.pack_value.setWordWrap(True)
        box.addWidget(key)
        box.addWidget(self.pack_value)
        self._layout.addWidget(self.footer)

    # ---- 折叠 ----
    def is_collapsed(self) -> bool:
        return self._collapsed

    def toggle(self) -> None:
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed: bool) -> None:
        collapsed = bool(collapsed)
        changed = collapsed != self._collapsed
        self._collapsed = collapsed
        self.setFixedWidth(SIDEBAR_WIDTH if collapsed else SIDEBAR_EXPANDED_WIDTH)
        self._layout.setContentsMargins(
            4 if collapsed else 8, 10, 4 if collapsed else 8, 10
        )
        self.mark.setVisible(not collapsed)
        self.footer.setVisible(not collapsed)
        for frame in self._group_frames:
            for label in frame.findChildren(QLabel):
                if label.objectName() == "nav_section":
                    label.setVisible(not collapsed)
        for key, button in self._buttons.items():
            if collapsed:
                button.setText(COMPACT_LABELS.get(key, key[:1]))
                button.setFixedWidth(SIDEBAR_WIDTH - 12)
                button.setToolTip(self._tooltip_for(key))
                button.setProperty("compact", True)
            else:
                button.setText(self._label_for(key))
                button.setMinimumWidth(0)
                button.setMaximumWidth(16_777_215)
                button.setToolTip(self._tooltip_for(key))
                button.setProperty("compact", False)
            restyle(button)
        self.toggle_button.setText("»" if collapsed else "«")
        self.toggle_button.setToolTip("展开侧栏" if collapsed else "折叠侧栏")
        if changed:
            self.collapsed_changed.emit(collapsed)

    # ---- 状态 ----
    def set_current(self, key: str) -> None:
        self._current = key
        for route, button in self._buttons.items():
            active = route == key
            button.setProperty("active", active)
            button.setChecked(active)
            restyle(button)

    def set_pack(self, name: str, version: str) -> None:
        self._pack_name = name or "规则包"
        self._pack_version = version
        text = self._pack_name
        if self._pack_version:
            text = f"{text} v{self._pack_version}"
        self.pack_value.setText(text)
        self.footer.setToolTip(text)

    # ---- 内部 ----
    def _label_for(self, key: str) -> str:
        for step in NAV_STEPS:
            if step.key == key:
                return step.label
        return key

    def _tooltip_for(self, key: str) -> str:
        for step in NAV_STEPS:
            if step.key == key:
                return f"{step.label} · {step.hint}"
        return key
