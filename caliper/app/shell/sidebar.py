"""Compact blue application rail inspired by the supplied assessment-workbench layout."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QToolButton, QVBoxLayout


class Sidebar(QFrame):
    navigate = Signal(str)

    NAV_ITEMS = (
        ("evidence", "⌂", "项目与材料"),
        ("results", "▤", "现场核查与记录"),
        ("issues", "!", "问题汇总"),
        ("export", "⇧", "导出记录表"),
        ("rules", "◇", "规则库"),
    )

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(58)
        self._buttons: dict[str, QToolButton] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 12, 6, 12)
        layout.setSpacing(10)

        mark = QLabel("C")
        mark.setObjectName("rail_mark")
        mark.setAlignment(Qt.AlignCenter)
        mark.setFixedSize(42, 42)
        layout.addWidget(mark, 0, Qt.AlignHCenter)
        layout.addSpacing(12)

        for key, symbol, hint in self.NAV_ITEMS:
            button = QToolButton()
            button.setObjectName("rail_button")
            button.setText(symbol)
            button.setToolTip(hint)
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setFixedSize(44, 44)
            button.clicked.connect(lambda _checked=False, route=key: self.navigate.emit(route))
            self._buttons[key] = button
            layout.addWidget(button, 0, Qt.AlignHCenter)

        layout.addStretch(1)
        help_button = QToolButton()
        help_button.setObjectName("rail_button")
        help_button.setText("?")
        help_button.setToolTip("帮助")
        help_button.setFixedSize(44, 44)
        layout.addWidget(help_button, 0, Qt.AlignHCenter)
        self.set_current("evidence")

    def set_current(self, key: str) -> None:
        button = self._buttons.get(key)
        if button is not None:
            button.setChecked(True)
