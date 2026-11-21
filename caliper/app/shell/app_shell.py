"""应用外壳：顶栏 + 左侧导航 + 内容区 + 状态栏 + AI 抽屉。"""

from __future__ import annotations

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.controller import AppController
from app.screens.dialogs import SettingsDialog
from app.screens.evidence import EvidenceScreen
from app.screens.export import ExportScreen
from app.screens.issues import IssuesScreen
from app.screens.results import ResultsScreen
from app.screens.rules import RulesScreen
from app.shell.ai_drawer import AiDrawer
from app.shell.navigation import NAV_STEPS
from app.shell.sidebar import Sidebar
from app.shell.topbar import TopBar
from app.theme.theme import ThemeManager
from app.theme.tokens import APP_NAME, APP_SUBTITLE, APP_VERSION, WINDOW_SIZE
from app.workers import RunWorker


class AppShell(QMainWindow):
    """主窗口：只负责导航、刷新与线程编排，业务全部下沉到 controller/core。"""

    def __init__(
        self,
        controller: AppController | None = None,
        theme: ThemeManager | None = None,
    ) -> None:
        super().__init__()
        self.controller = controller or AppController()
        self.theme = theme
        self.worker: RunWorker | None = None
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION} · {APP_SUBTITLE}")
        self.resize(*WINDOW_SIZE)
        self.setMinimumSize(1180, 760)

        root = QWidget()
        root.setObjectName("root")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.sidebar = Sidebar()
        root_layout.addWidget(self.sidebar)

        content = QWidget()
        content.setObjectName("content")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.topbar = TopBar()
        self.stack = QStackedWidget()
        self.pages: dict[str, QWidget] = {
            "evidence": EvidenceScreen(self.controller),
            "results": ResultsScreen(self.controller),
            "issues": IssuesScreen(self.controller),
            "export": ExportScreen(self.controller),
            "rules": RulesScreen(self.controller),
        }
        self._index_by_key = {step.key: index for index, step in enumerate(NAV_STEPS)}
        for step in NAV_STEPS:
            self.stack.addWidget(self.pages[step.key])

        content_layout.addWidget(self.topbar)
        content_layout.addWidget(self.stack, 1)
        root_layout.addWidget(content, 1)
        root_layout.addWidget(AiDrawer())
        self.setCentralWidget(root)

        self._build_statusbar()
        self._wire()
        self.refresh_all()

    # ---- 构建 ----
    def _build_statusbar(self) -> None:
        self.status_label = QLabel("就绪：先导入设备证据，再开始核查")
        self.status_label.setObjectName("status_text")
        version = QLabel(f"{APP_NAME.lower()} {APP_VERSION}")
        version.setObjectName("status_text")
        bar = self.statusBar()
        bar.addWidget(self.status_label, 1)
        bar.addPermanentWidget(version)

    def _wire(self) -> None:
        self.sidebar.navigate.connect(self.go)
        self.topbar.run_requested.connect(self.run)
        self.topbar.load_requested.connect(self.load_project)
        self.topbar.save_requested.connect(self.save_project)
        self.topbar.settings_requested.connect(self.open_settings)
        self.topbar.theme_requested.connect(self.toggle_theme)

        evidence: EvidenceScreen = self.pages["evidence"]  # type: ignore[assignment]
        evidence.project_loaded.connect(self._on_project_loaded)
        evidence.assets_changed.connect(self._on_assets_changed)
        evidence.run_requested.connect(self.run)

        export: ExportScreen = self.pages["export"]  # type: ignore[assignment]
        export.settings_changed.connect(self._on_settings_changed)

    # ---- 导航 ----
    def go(self, key: str) -> None:
        index = self._index_by_key.get(key)
        if index is None:
            return
        self.stack.setCurrentIndex(index)
        self.sidebar.set_current(key)
        page = self.pages[key]
        if key == "rules":
            page.refresh()  # type: ignore[attr-defined]

    # ---- 刷新 ----
    def refresh_all(self) -> None:
        self._refresh_topbar()
        self._refresh_pack_info()
        for key in ("evidence", "results", "issues", "export"):
            page = self.pages[key]
            page.refresh()  # type: ignore[attr-defined]

    def _refresh_topbar(self) -> None:
        project = self.controller.project
        self.topbar.set_project(
            project.project_code,
            project.system_name,
            project.level,
            len(project.assets),
        )

    def _refresh_pack_info(self) -> None:
        try:
            pack = self.controller.load_pack()
            items = pack.items_for_level(self.controller.project.level)
        except Exception:
            self.sidebar.set_pack_info("不可用", self.controller.project.level, 0)
            return
        self.sidebar.set_pack_info(pack.meta.name, self.controller.project.level, len(items))

    # ---- 项目 ----
    def load_project(self) -> None:
        self.pages["evidence"].load_project()  # type: ignore[attr-defined]

    def save_project(self) -> None:
        if self.pages["evidence"].save_project():  # type: ignore[attr-defined]
            self._refresh_topbar()

    def _on_project_loaded(self) -> None:
        self.refresh_all()
        self.set_status(f"已加载项目：{self.controller.source_path}")

    def _on_assets_changed(self) -> None:
        self._refresh_topbar()

    def _on_settings_changed(self) -> None:
        self._refresh_pack_info()
        self.pages["evidence"].refresh()  # type: ignore[attr-defined]
        self.set_status("设置已更新")

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.controller, self)
        if dialog.exec() != SettingsDialog.Accepted:
            return
        self.pages["evidence"].refresh()  # type: ignore[attr-defined]
        self.pages["export"].refresh()  # type: ignore[attr-defined]
        self._refresh_pack_info()
        self.set_status("设置已更新")

    def toggle_theme(self) -> None:
        if self.theme is None:
            return
        name = self.theme.toggle()
        self.set_status(f"已切换到{'深色' if name == 'dark' else '浅色'}主题")

    # ---- 核查 ----
    def run(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        try:
            self.pages["evidence"].apply_form()  # type: ignore[attr-defined]
        except Exception as exc:
            QMessageBox.warning(self, "项目信息有误", str(exc))
            return
        self.topbar.set_running(True)
        self.set_status("正在核查…")
        self.worker = RunWorker(self.controller, self)
        self.worker.succeeded.connect(self._on_run_ok)
        self.worker.failed.connect(self._on_run_failed)
        self.worker.finished.connect(self._on_run_finished)
        self.worker.start()

    def _on_run_ok(self, result) -> None:
        self.pages["results"].refresh()  # type: ignore[attr-defined]
        self.pages["issues"].refresh()  # type: ignore[attr-defined]
        self.pages["export"].refresh()  # type: ignore[attr-defined]
        counts: dict[str, int] = {}
        for run in result.asset_runs:
            for item in run.items:
                label = item.verdict.value
                counts[label] = counts.get(label, 0) + 1
        summary = "  ".join(f"{key} {value}" for key, value in counts.items())
        self.set_status(f"核查完成：{summary}")
        self.go("results")

    def _on_run_failed(self, message: str) -> None:
        self.set_status("核查失败")
        QMessageBox.critical(self, "核查失败", message)

    def _on_run_finished(self) -> None:
        self.topbar.set_running(False)
        self.worker = None

    # ---- 杂项 ----
    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self.worker is not None and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(3000)
        super().closeEvent(event)
