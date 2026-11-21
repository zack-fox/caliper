"""左侧导航：工作流四步 + 规则库，底部展示当前规则包信息。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QToolButton, QVBoxLayout

from app.shell.navigation import NavStep, rule_steps, workflow_steps
from app.theme.tokens import SIDEBAR_WIDTH


class Sidebar(QFrame):
    navigate = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(SIDEBAR_WIDTH)
        self._buttons: dict[str, QToolButton] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(6)

        brand = QLabel("Caliper")
        brand.setObjectName("brand_name")
        brand.setContentsMargins(8, 0, 0, 0)
        subtitle = QLabel("等保测评取证助手")
        subtitle.setObjectName("brand_sub")
        subtitle.setContentsMargins(8, 0, 0, 0)
        layout.addWidget(brand)
        layout.addWidget(subtitle)
        layout.addSpacing(14)

        layout.addWidget(self._section("工作流"))
        for step in workflow_steps():
            layout.addWidget(self._button(step))

        layout.addSpacing(10)
        layout.addWidget(self._section("规则"))
        for step in rule_steps():
            layout.addWidget(self._button(step))

        layout.addStretch(1)
        layout.addWidget(self._footer())

        self.set_current("evidence")

    # ---- 构建 ----
    @staticmethod
    def _section(title: str) -> QLabel:
        label = QLabel(title)
        label.setObjectName("nav_section")
        label.setContentsMargins(6, 2, 0, 2)
        return label

    def _button(self, step: NavStep) -> QToolButton:
        text = f"{step.numeral}    {step.label}" if step.numeral else f"·    {step.label}"
        button = QToolButton()
        button.setObjectName("nav")
        button.setText(text)
        button.setToolTip(step.hint)
        button.setCheckable(True)
        button.setAutoExclusive(True)
        button.setCursor(Qt.PointingHandCursor)
        button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        button.setFixedHeight(36)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.clicked.connect(lambda _checked=False, key=step.key: self.navigate.emit(key))
        self._buttons[step.key] = button
        return button

    def _footer(self) -> QFrame:
        footer = QFrame()
        footer.setObjectName("sidebar_footer")
        layout = QVBoxLayout(footer)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(3)

        captions = (
            ("规则包", "pack_value", "—"),
            ("等级", "level_value", "—"),
            ("控制项", "items_value", "—"),
        )
        self._footer_values: dict[str, QLabel] = {}
        for key_text, attr, default in captions:
            row = QLabel(f"{key_text}  {default}")
            row.setObjectName("sidebar_footer_value")
            layout.addWidget(row)
            self._footer_values[attr] = row
        return footer

    # ---- 交互 ----
    def set_current(self, key: str) -> None:
        button = self._buttons.get(key)
        if button is not None and not button.isChecked():
            button.setChecked(True)

    def set_pack_info(self, pack_name: str, level: int, item_count: int) -> None:
        self._footer_values["pack_value"].setText(f"pack     {pack_name or '—'}")
        self._footer_values["level_value"].setText(f"等级     {level} 级")
        self._footer_values["items_value"].setText(f"控制项   {item_count} 项")
