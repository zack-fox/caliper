"""项目步骤条：六个项目步骤 + 完成 / 待办 / 阻断状态。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QToolButton

from app.shell.navigation import workflow_steps
from app.theme.theme import restyle
from app.theme.tokens import STEPBAR_HEIGHT

STEP_STATES = ("done", "todo", "blocked")


class StepBar(QFrame):
    navigate = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("stepbar")
        self.setFixedHeight(STEPBAR_HEIGHT)
        self._buttons: dict[str, QToolButton] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 0, 18, 0)
        layout.setSpacing(10)

        steps = workflow_steps()
        for index, step in enumerate(steps, start=1):
            button = QToolButton()
            button.setObjectName("step_item")
            button.setText(f"{index}  {step.label}")
            button.setToolButtonStyle(Qt.ToolButtonTextOnly)
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(step.hint)
            button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            button.setMinimumHeight(STEPBAR_HEIGHT - 14)
            button.setProperty("state", "todo")
            button.setProperty("step_key", step.key)
            button.clicked.connect(
                lambda _checked=False, route=step.key: self.navigate.emit(route)
            )
            self._buttons[step.key] = button
            layout.addWidget(button)
            if index < len(steps):
                separator = QLabel("›")
                separator.setObjectName("muted")
                layout.addWidget(separator)
        layout.addStretch(1)

    def set_current(self, key: str) -> None:
        if key in self._buttons:
            self._buttons[key].setChecked(True)
            return
        for button in self._buttons.values():
            button.setChecked(False)

    def set_states(self, states: dict[str, str]) -> None:
        for key, state in states.items():
            button = self._buttons.get(key)
            if button is None or state not in STEP_STATES:
                continue
            button.setProperty("state", state)
            restyle(button)
