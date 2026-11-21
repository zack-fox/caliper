"""顶栏：品牌、当前项目上下文、等级徽章与主操作入口。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

from app.theme.tokens import TOPBAR_HEIGHT


class TopBar(QFrame):
    run_requested = Signal()
    load_requested = Signal()
    save_requested = Signal()
    settings_requested = Signal()
    theme_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("topbar")
        self.setFixedHeight(TOPBAR_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 0, 14, 0)
        layout.setSpacing(10)

        project_box = QLabel("当前项目")
        project_box.setObjectName("project_caption")
        self.project_code = QLabel("—")
        self.project_code.setObjectName("project_code")
        self.project_name = QLabel("未加载项目")
        self.project_name.setObjectName("project_name")
        layout.addWidget(project_box)
        layout.addWidget(self.project_code)
        layout.addWidget(self.project_name)

        self.level_badge = QLabel("—")
        self.level_badge.setObjectName("context_badge")
        self.asset_badge = QLabel("设备 0")
        self.asset_badge.setObjectName("context_badge")
        layout.addWidget(self.level_badge)
        layout.addWidget(self.asset_badge)
        layout.addStretch(1)

        self.load_button = self._button("加载项目", "topbar_button")
        self.save_button = self._button("保存项目", "topbar_button")
        self.theme_button = self._button("主题", "topbar_button")
        self.settings_button = self._button("设置", "topbar_button")
        self.run_button = self._button("生成记录草稿", "topbar_primary")
        self.load_button.clicked.connect(self.load_requested.emit)
        self.save_button.clicked.connect(self.save_requested.emit)
        self.theme_button.clicked.connect(self.theme_requested.emit)
        self.settings_button.clicked.connect(self.settings_requested.emit)
        self.run_button.clicked.connect(self.run_requested.emit)

        layout.addWidget(self.load_button)
        layout.addWidget(self.save_button)
        layout.addWidget(self.theme_button)
        layout.addWidget(self.settings_button)
        layout.addWidget(self.run_button)

    @staticmethod
    def _button(text: str, object_name: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName(object_name)
        button.setCursor(Qt.PointingHandCursor)
        return button

    # ---- 状态 ----
    def set_project(self, code: str, name: str, level: int, asset_count: int) -> None:
        self.project_code.setText(code or "未编号")
        self.project_name.setText(name or "未命名系统")
        self.level_badge.setText(f"等保{_level_text(level)}")
        self.asset_badge.setText(f"设备 {asset_count}")

    def set_running(self, running: bool) -> None:
        self.run_button.setEnabled(not running)
        self.run_button.setText("正在分析…" if running else "生成记录草稿")


def _level_text(level: int) -> str:
    return {2: "二级", 3: "三级", 4: "四级"}.get(level, f"{level}级")
