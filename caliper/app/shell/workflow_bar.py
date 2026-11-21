"""Horizontal process navigation shown below the project context bar."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton


class WorkflowBar(QFrame):
    navigate = Signal(str)

    STEPS = (
        ("evidence", "01", "项目与材料"),
        ("results", "02", "现场核查与记录"),
        ("export", "03", "导出记录表"),
    )

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("workflowbar")
        self._buttons: dict[str, QToolButton] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 9, 18, 9)
        layout.setSpacing(8)
        caption = QLabel("工作流程")
        caption.setObjectName("workflow_caption")
        layout.addWidget(caption)
        layout.addSpacing(12)

        for key, number, title in self.STEPS:
            button = QToolButton()
            button.setObjectName("workflow_step")
            button.setText(f"{number}   {title}")
            button.setToolButtonStyle(Qt.ToolButtonTextOnly)
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setMinimumWidth(180)
            button.setFixedHeight(42)
            button.clicked.connect(lambda _checked=False, route=key: self.navigate.emit(route))
            self._buttons[key] = button
            layout.addWidget(button)
        layout.addStretch(1)

    def set_current(self, key: str) -> None:
        button = self._buttons.get(key)
        if button is not None:
            button.setChecked(True)
