"""后台线程：跑判定不卡界面。"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from app.controller import AppController


class RunWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, controller: AppController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller

    def run(self) -> None:  # noqa: D401 - Qt 线程入口
        try:
            result = self.controller.run()
        except Exception as exc:  # 错误交给界面展示
            self.failed.emit(str(exc))
            return
        self.succeeded.emit(result)
