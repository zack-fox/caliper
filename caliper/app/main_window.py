"""主窗口：四个页签 + 顶栏动作。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QToolBar,
)

from app.controller import AppController
from app.screens.export import ExportScreen
from app.screens.issues import IssuesScreen
from app.screens.project import ProjectScreen
from app.screens.result import ResultScreen
from app.workers import RunWorker


class MainWindow(QMainWindow):
    def __init__(self, controller: AppController | None = None) -> None:
        super().__init__()
        self.controller = controller or AppController()
        self.worker: RunWorker | None = None
        self.setWindowTitle("Caliper · 等保测评取证助手")
        self.resize(1240, 820)

        self.tabs = QTabWidget()
        self.project_screen = ProjectScreen(self.controller)
        self.result_screen = ResultScreen(self.controller)
        self.issues_screen = IssuesScreen(self.controller)
        self.export_screen = ExportScreen(self.controller)
        self.tabs.addTab(self.project_screen, "项目与资产")
        self.tabs.addTab(self.result_screen, "结果记录")
        self.tabs.addTab(self.issues_screen, "问题与重大")
        self.tabs.addTab(self.export_screen, "导出与设置")
        self.setCentralWidget(self.tabs)

        toolbar = QToolBar("主操作")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.run_action = QAction("运行判定", self)
        self.run_action.triggered.connect(self._run)
        toolbar.addAction(self.run_action)
        self.load_action = QAction("加载项目…", self)
        self.load_action.triggered.connect(self._load_project)
        toolbar.addAction(self.load_action)
        self.save_action = QAction("保存项目…", self)
        self.save_action.triggered.connect(self._save_project)
        toolbar.addAction(self.save_action)
        toolbar.addSeparator()
        self.export_action = QAction("导出结果记录表", self)
        self.export_action.triggered.connect(self._export)
        toolbar.addAction(self.export_action)

        self.status = QLabel("就绪：先填写项目与资产，再运行判定")
        self.statusBar().addWidget(self.status, 1)
        self._apply_style()
        self.project_screen.project_loaded.connect(self._on_project_loaded)

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

    def _load_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "加载项目", str(self.controller.base_dir), "YAML (*.yaml *.yml)"
        )
        if not path:
            return
        try:
            self.controller.load_project(Path(path))
        except Exception as exc:
            QMessageBox.critical(self, "加载失败", str(exc))
            return
        self.project_screen.refresh()
        self._on_project_loaded()

    def _save_project(self) -> None:
        try:
            project = self.project_screen.apply_form()
        except Exception as exc:
            QMessageBox.warning(self, "项目信息有误", str(exc))
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "保存项目", str(self.controller.base_dir / "project.yaml"), "YAML (*.yaml *.yml)"
        )
        if not path:
            return
        target = Path(path)
        if not target.suffix:
            target = target.with_suffix(".yaml")
        try:
            self.controller.save_project(project, target)
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        self.status.setText(f"已保存：{target}")

    def _run(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        try:
            self.project_screen.apply_form()
        except Exception as exc:
            QMessageBox.warning(self, "项目信息有误", str(exc))
            return
        self.run_action.setEnabled(False)
        self.status.setText("正在跑判定…")
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
        self.status.setText(f"判定完成：{summary}")
        self.tabs.setCurrentWidget(self.result_screen)

    def _on_run_failed(self, message: str) -> None:
        self.status.setText("判定失败")
        QMessageBox.critical(self, "判定失败", message)

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
