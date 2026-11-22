"""底部状态栏：左侧消息 + 右侧设备 / 核查 / 不符合 / 重大 / 规则包统计。"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QVBoxLayout

from app.theme.tokens import STATUS_HEIGHT
from app.widgets.workspace import StatusBar


class AppStatusBar(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("statusbar")
        self.setFixedHeight(STATUS_HEIGHT)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._bar = StatusBar()
        self._bar.setObjectName("statusbar_body")
        self._bar.setStyleSheet("background: transparent; border: none;")
        outer.addWidget(self._bar)

        self.set_message("就绪：导入现场材料，生成并核对测评记录")

    def set_message(self, text: str) -> None:
        self._bar.set_segment("message", text, side="left")

    def set_stats(
        self,
        devices: int,
        checked: int,
        total: int,
        non_compliant: int,
        pending_major: int,
        pack_label: str,
    ) -> None:
        self._bar.set_segment("devices", f"设备 {devices}", side="right")
        self._bar.set_segment("checked", f"已核查 {checked}/{total}", side="right")
        self._bar.set_segment("non_compliant", f"不符合 {non_compliant}", side="right")
        self._bar.set_segment("pending_major", f"待确认重大 {pending_major}", side="right")
        self._bar.set_segment("pack", pack_label, side="right")
