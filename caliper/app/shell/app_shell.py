"""应用外壳：项目顶栏 + 分组侧栏 + 项目步骤条 + 页面栈 + 底部状态栏。"""

from __future__ import annotations

from PySide6.QtGui import QCloseEvent, QResizeEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
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
from app.screens.overview import OverviewScreen
from app.screens.results import ResultsScreen
from app.screens.risk import RiskScreen
from app.screens.rules import RulesScreen
from app.shell.navigation import NAV_STEPS
from app.shell.progress import step_states
from app.shell.sidebar import Sidebar
from app.shell.statusbar import AppStatusBar
from app.shell.stepbar import StepBar
from app.shell.topbar import TopBar
from app.theme.theme import ThemeManager
from app.theme.tokens import APP_NAME, APP_SUBTITLE, APP_VERSION, WINDOW_SIZE
from app.workers import RunWorker
from core.contracts.verdict import Verdict

# 小于该宽度自动折叠侧栏，保证内容区在 1280 宽度下不被挤压。
SIDEBAR_BREAKPOINT = 1360


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
        self._manual_collapsed = False
        self._pending_major = 0
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION} · {APP_SUBTITLE}")
        self.resize(*WINDOW_SIZE)
        self.setMinimumSize(1280, 800)

        root = QWidget()
        root.setObjectName("root")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.topbar = TopBar()
        root_layout.addWidget(self.topbar)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self.sidebar = Sidebar()
        body_layout.addWidget(self.sidebar)

        content = QWidget()
        content.setObjectName("content")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.stepbar = StepBar()
        self.stack = QStackedWidget()
        self.pages: dict[str, QWidget] = {
            "overview": OverviewScreen(self.controller),
            "evidence": EvidenceScreen(self.controller),
            "results": ResultsScreen(self.controller),
            "issues": IssuesScreen(self.controller),
            "risk": RiskScreen(self.controller),
            "export": ExportScreen(self.controller),
            "rules": RulesScreen(self.controller),
        }
        self._index_by_key = {step.key: index for index, step in enumerate(NAV_STEPS)}
        for step in NAV_STEPS:
            self.stack.addWidget(self.pages[step.key])

        content_layout.addWidget(self.stepbar)
        content_layout.addWidget(self.stack, 1)
        body_layout.addWidget(content, 1)
        root_layout.addWidget(body, 1)

        self.statusbar = AppStatusBar()
        root_layout.addWidget(self.statusbar)
        self.setCentralWidget(root)

        self._wire()
        self.refresh_all()

    # ---- 构建 ----
    def _wire(self) -> None:
        self.sidebar.navigate.connect(self.go)
        self.stepbar.navigate.connect(self.go)
        self.pages["overview"].navigate.connect(self.go)  # type: ignore[attr-defined]
        self.topbar.run_requested.connect(self.run)
        self.topbar.load_requested.connect(self.load_project)
        self.topbar.save_requested.connect(self.save_project)
        self.topbar.settings_requested.connect(self.open_settings)
        self.topbar.theme_requested.connect(self.toggle_theme)
        self.sidebar.toggle_button.clicked.connect(self._remember_sidebar_state)

        evidence: EvidenceScreen = self.pages["evidence"]  # type: ignore[assignment]
        evidence.project_loaded.connect(self._on_project_loaded)
        evidence.assets_changed.connect(self._on_assets_changed)
        evidence.run_requested.connect(self.run)

        export: ExportScreen = self.pages["export"]  # type: ignore[assignment]
        export.settings_changed.connect(self._on_settings_changed)

    # ---- 导航 ----
    def go(self, key: str) -> bool:
        index = self._index_by_key.get(key)
        if index is None:
            return False
        self.stack.setCurrentIndex(index)
        self.sidebar.set_current(key)
        self.stepbar.set_current(key)
        if key == "rules":
            self.pages[key].refresh()  # type: ignore[attr-defined]
        return True

    # ---- 刷新 ----
    def refresh_all(self) -> None:
        self._refresh_topbar()
        for key in ("overview", "evidence", "results", "issues", "risk", "export"):
            page = self.pages[key]
            refresh = getattr(page, "refresh", None)
            if callable(refresh):
                refresh()
        self._refresh_statusbar()

    def _refresh_topbar(self) -> None:
        project = self.controller.project
        self.topbar.set_project(
            project.project_code,
            project.system_name,
            project.level,
            len(project.assets),
            project.check_date,
        )

    def _refresh_statusbar(self) -> None:
        project = self.controller.project
        result = self.controller.run_result
        devices = len(project.assets)
        checked = total = non_compliant = 0
        if result is not None:
            for run in result.asset_runs:
                for item in run.items:
                    total += 1
                    if item.verdict != Verdict.UNCOLLECTED:
                        checked += 1
                    if item.verdict == Verdict.NON_COMPLIANT:
                        non_compliant += 1

        pending_major = 0
        note = ""
        if result is not None:
            try:
                reviews = self.controller.major_reviews()
            except Exception as exc:  # noqa: BLE001 - 统计失败时提示而非崩溃
                reviews = {}
                note = f"重大隐患统计失败：{exc}"
            pending_major = sum(
                1 for review in reviews.values() if review.reason == "未确认"
            )
        self._pending_major = pending_major

        pack_label = "规则包未加载"
        try:
            pack = self.controller.load_pack()
        except Exception:  # noqa: BLE001 - 规则包缺失不应阻断外壳刷新
            self.sidebar.set_pack("规则包未加载", "")
        else:
            pack_label = f"规则包 {pack.meta.name} v{pack.meta.version}"
            self.sidebar.set_pack(pack.meta.name, pack.meta.version)

        self.statusbar.set_stats(
            devices,
            checked,
            total,
            non_compliant,
            pending_major,
            pack_label,
        )
        if note:
            self.statusbar.set_message(note)
        self._refresh_steps()

    def _refresh_steps(self) -> None:
        states = step_states(
            bool(self.controller.project.assets),
            self.controller.run_result is not None,
            self._pending_major,
        )
        self.stepbar.set_states(states)

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
        self._refresh_statusbar()

    def _on_settings_changed(self) -> None:
        self.pages["evidence"].refresh()  # type: ignore[attr-defined]
        self._refresh_statusbar()
        self.set_status("设置已更新")

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.controller, self)
        if dialog.exec() != SettingsDialog.Accepted:
            return
        self.pages["evidence"].refresh()  # type: ignore[attr-defined]
        self.pages["export"].refresh()  # type: ignore[attr-defined]
        self._refresh_statusbar()
        self.set_status("已更新设置")

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
        self.set_status("正在解析材料并生成记录草稿…")
        self.worker = RunWorker(self.controller, self)
        self.worker.succeeded.connect(self._on_run_ok)
        self.worker.failed.connect(self._on_run_failed)
        self.worker.finished.connect(self._on_run_finished)
        self.worker.start()

    def _on_run_ok(self, result) -> None:
        self.refresh_all()
        counts: dict[str, int] = {}
        for run in result.asset_runs:
            for item in run.items:
                label = item.verdict.value
                counts[label] = counts.get(label, 0) + 1
        summary = "  ".join(f"{key} {value}" for key, value in counts.items())
        self.set_status(f"记录草稿已生成：{summary}")
        self.go("results")

    def _on_run_failed(self, message: str) -> None:
        self.set_status("核查失败")
        QMessageBox.critical(self, "核查失败", message)

    def _on_run_finished(self) -> None:
        self.topbar.set_running(False)
        self.worker = None

    # ---- 布局 ----
    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        sidebar = getattr(self, "sidebar", None)
        if sidebar is None:
            return
        if self.width() < SIDEBAR_BREAKPOINT:
            sidebar.set_collapsed(True)
        else:
            sidebar.set_collapsed(self._manual_collapsed)

    def _remember_sidebar_state(self) -> None:
        self._manual_collapsed = self.sidebar.is_collapsed()

    # ---- 杂项 ----
    def set_status(self, text: str) -> None:
        self.statusbar.set_message(text)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self.worker is not None and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(3000)
        super().closeEvent(event)
