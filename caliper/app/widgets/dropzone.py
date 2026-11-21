"""证据拖拽上传区：把日志 / 命令输出 / 资产表拖进来就能解析。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from app.theme.theme import restyle

EVIDENCE_SUFFIXES = (".log", ".txt", ".out", ".cmd", ".json", ".xlsx", ".xls", ".csv")


class DropZone(QFrame):
    """虚线拖拽区；拖入后发出本地路径。"""

    path_dropped = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("dropzone")
        self.setAcceptDrops(True)
        self.setProperty("active", "false")
        self.setMinimumHeight(132)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignCenter)

        self.title = QLabel("把现场采集日志、命令输出或资产记录表拖到这里")
        self.title.setObjectName("dropzone_title")
        self.title.setAlignment(Qt.AlignCenter)
        self.hint = QLabel(
            "支持 .log / .txt / .out / .cmd / .json / .xlsx；本地离线解析，不上传云端"
        )
        self.hint.setObjectName("dropzone_hint")
        self.hint.setAlignment(Qt.AlignCenter)
        self.hint.setWordWrap(True)
        self.hint.setMinimumWidth(560)

        layout.addWidget(self.title)
        layout.addWidget(self.hint)

        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        self.actions.setAlignment(Qt.AlignCenter)
        layout.addSpacing(4)
        layout.addLayout(self.actions)

    def add_action(self, widget) -> None:
        self.actions.addWidget(widget)

    def set_hint(self, text: str) -> None:
        self.hint.setText(text)

    # ---- 拖拽事件 ----
    def _set_active(self, active: bool) -> None:
        self.setProperty("active", "true" if active else "false")
        restyle(self)

    @staticmethod
    def _first_local_path(mime) -> str:
        if not mime.hasUrls():
            return ""
        for url in mime.urls():
            if url.isLocalFile():
                return url.toLocalFile()
        return ""

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if self._first_local_path(event.mimeData()):
            event.acceptProposedAction()
            self._set_active(True)
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self._set_active(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        self._set_active(False)
        path = self._first_local_path(event.mimeData())
        if path:
            event.acceptProposedAction()
            self.path_dropped.emit(path)
        else:
            event.ignore()
