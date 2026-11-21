"""主窗口：设备证据主流程 + 结果记录 + 问题与重大 + 导出。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QToolBar,
)

from app.controller import AppController
from app.screens.devices import DevicesScreen
from app.screens.export import ExportScreen
from app.screens.issues import IssuesScreen
from app.screens.result import ResultScreen
from app.screens.settings import SettingsDialog
from app.workers import RunWorker


class MainWindow(QMainWindow):
    def __init__(self, controller: AppController | None = None) -> None:
        super().__init__()
        self.controller = controller or AppController()
        self.worker: RunWorker | None = None
        self.setWindowTitle("Caliper v1.0.1 · 等保测评取证助手")
        self.resize(1280, 840)

        self.tabs = QTabWidget()
        self.devices_screen = DevicesScreen(self.controller)
        self.result_screen = ResultScreen(self.controller)
        self.issues_screen = IssuesScreen(self.controller)
        self.export_screen = ExportScreen(self.controller)
        self.tabs.addTab(self.devices_screen, "设备与证据")
        self.tabs.addTab(self.result_screen, "结果记录")
        self.tabs.addTab(self.issues_screen, "问题与重大")
        self.tabs.addTab(self.export_screen, "导出")
        self.setCentralWidget(self.tabs)

        toolbar = QToolBar("主操作")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.run_action = QAction("运行判定", self)
        self.run_action.triggered.connect(self._run)
        toolbar.addAction(self.run_action)
        self.load_action = QAction("加载项目…", self)
        self.load_action.triggered.connect(lambda: self.devices_screen.load_project())
        toolbar.addAction(self.load_action)
        self.save_action = QAction("保存项目…", self)
        self.save_action.triggered.connect(lambda: self.devices_screen.save_project())
        toolbar.addAction(self.save_action)
        toolbar.addSeparator()
        self.settings_action = QAction("设置…", self)
        self.settings_action.triggered.connect(self._open_settings)
        toolbar.addAction(self.settings_action)

        self.status = QLabel("就绪：先导入设备证据包，再开始核查")
        self.statusBar().addWidget(self.status, 1)
        self._apply_style()
        self.devices_screen.project_loaded.connect(self._on_project_loaded)
        self.devices_screen.run_requested.connect(self._run)

    def _apply_style(self) -> None:
        qss = Path(__file__).with_name("app.qss")
        if qss.exists():
            app = QApplication.instance()
            if app is not None:
                app.setStyleSheet(qss.read_text(encoding="utf-8"))

    def _on_project_loaded(self) -> None:
        self.result_screen.refresh()
        self.issues_screen.refresh()
        self.export_screen.refresh()
        self.status.setText(f"已加载项目：{self.controller.source_path}")

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.controller, self)
        if dialog.exec() != SettingsDialog.Accepted:
            return
        self.devices_screen.refresh()
        self.export_screen.refresh()
        self.status.setText("设置已更新")

    def _run(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        try:
            self.devices_screen.apply_form()
        except Exception as exc:
            QMessageBox.warning(self, "项目信息有误", str(exc))
            return
        self.run_action.setEnabled(False)
        self.status.setText("正在核查…")
        self.worker = RunWorker(self.controller, self)
        self.worker.succeeded.connect(self._on_run_ok)
        self.worker.failed.connect(self._on_run_failed)
        self.worker.finished.connect(self._on_run_finished)
        self.worker.start()

    def _on_run_ok(self, result) -> None:
        self.result_screen.refresh()
        self.issues_screen.refresh()
        self.export_screen.refresh()
        counts = result.verdict_counts()
        summary = "  ".join(f"{key} {value}" for key, value in counts.items())
        self.status.setText(f"核查完成：{summary}")
        self.tabs.setCurrentWidget(self.result_screen)

    def _on_run_failed(self, message: str) -> None:
        self.status.setText("核查失败")
        QMessageBox.critical(self, "核查失败", message)

    def _on_run_finished(self) -> None:
        self.run_action.setEnabled(True)
        self.worker = None

    def _export(self) -> None:
        if self.controller.run_result is None:
            QMessageBox.information(self, "提示", "请先运行判定")
            return
        try:
            target, problems = self.controller.export_result()
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))
            return
        if problems:
            QMessageBox.warning(self, "已导出但有自检问题", "\n".join(problems))
        else:
            QMessageBox.information(self, "导出完成", str(target))
        self.status.setText(f"已导出：{target}")

    def closeEvent(self, event) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(3000)
        super().closeEvent(event)
