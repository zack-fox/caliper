"""顶栏：品牌、项目上下文、等级 / 日期 / 设备徽章与主操作入口。"""

from __future__ import annotations

from datetime import date

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

        self.brand = QLabel("Caliper")
        self.brand.setObjectName("section_title")
        layout.addWidget(self.brand)
        layout.addSpacing(10)

        project_box = QLabel("项目")
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
        self.check_date = QLabel("核查日期 —")
        self.check_date.setObjectName("mono")
        self.asset_badge = QLabel("设备 0")
        self.asset_badge.setObjectName("context_badge")
        layout.addWidget(self.level_badge)
        layout.addWidget(self.check_date)
        layout.addWidget(self.asset_badge)
        layout.addStretch(1)

        self.run_button = self._button("生成记录草稿", "topbar_primary")
        self.theme_button = self._button("主题", "topbar_button")
        self.settings_button = self._button("设置", "topbar_button")
        self.run_button.clicked.connect(self.run_requested.emit)
        self.theme_button.clicked.connect(self.theme_requested.emit)
        self.settings_button.clicked.connect(self.settings_requested.emit)

        layout.addWidget(self.run_button)
        layout.addWidget(self.theme_button)
        layout.addWidget(self.settings_button)

    @staticmethod
    def _button(text: str, object_name: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName(object_name)
        button.setCursor(Qt.PointingHandCursor)
        return button

    # ---- 状态 ----
    def set_project(
        self,
        code: str,
        name: str,
        level: int,
        asset_count: int,
        check_date: date | str | None = None,
    ) -> None:
        self.project_code.setText(code or "未编号")
        self.project_name.setText(name or "未命名系统")
        self.level_badge.setText(f"等保{_level_text(level)}")
        self.check_date.setText(f"核查日期 {_date_text(check_date)}")
        self.asset_badge.setText(f"设备 {asset_count}")

    def set_running(self, running: bool) -> None:
        self.run_button.setEnabled(not running)
        self.run_button.setText("正在分析…" if running else "生成记录草稿")


def _level_text(level: int) -> str:
    return {2: "二级", 3: "三级", 4: "四级"}.get(level, f"{level}级")


def _date_text(value: date | str | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return str(value) or "—"
