"""右侧 AI 抽屉（v1 仅占位）：保持版式完整，后续替换为真实助手面板。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSizePolicy, QToolButton, QVBoxLayout, QWidget


class AiDrawer(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedWidth(40)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 10)
        layout.setSpacing(0)

        self.rail = QToolButton()
        self.rail.setObjectName("ai_rail")
        self.rail.setText("AI")
        self.rail.setFixedSize(40, 44)
        self.rail.setCursor(Qt.PointingHandCursor)
        self.rail.setToolTip("AI 助手（规划中）：只生成文案类字段，不参与判定")
        layout.addWidget(self.rail)
        layout.addStretch(1)
