"""主题渲染与切换：由设计令牌生成 QSS，应用到 QApplication，并持久化偏好。

QSS 里颜色全部写成 ``@token@`` 占位符，渲染时按当前调色板替换，
因此同一套模板同时支持浅色 / 深色，且能被 ``ui_lint`` 静态校验。
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import QApplication

from app.theme.tokens import FONT_FAMILY, FONT_MONO, PALETTES

_QSS_TEMPLATE = r"""
/* ============================ 基础 ============================ */
QWidget {
    background: @bg@;
    color: @text@;
    font-family: @font_family@;
    font-size: 13px;
}
QLabel { background: transparent; }
QDialog { background: @surface@; }
QMainWindow, QWidget#root, QWidget#content, QWidget#page { background: @bg@; }
QToolTip {
    background: @text@;
    color: @white@;
    border: none;
    padding: 6px 8px;
    border-radius: 6px;
}

/* ============================ 顶栏 ============================ */
QFrame#topbar { background: @surface@; border: none; border-bottom: 1px solid @border@; }
QFrame#topbar_sep { background: @nav_alt@; border: none; }
QLabel#brand_name {
    color: @nav_text_strong@;
    font-size: 15px;
    font-weight: 700;
    background: transparent;
}
QLabel#brand_sub { color: @nav_section@; font-size: 11px; background: transparent; }
QLabel#project_code {
    color: @text_secondary@;
    font-family: @font_mono@;
    font-size: 11px;
    background: transparent;
}
QLabel#project_name { color: @text@; font-size: 13px; background: transparent; }
QLabel#project_caption { color: @muted@; font-size: 11px; background: transparent; }
QLabel#context_badge { background: @primary_soft@; color: @primary_ink@; border-radius: 6px; padding: 5px 9px; font-size: 12px; font-weight: 600; }

/* ============================ 侧导航 ============================ */
QFrame#sidebar { background: @primary@; border: none; }
QLabel#rail_mark {
    background: @white@;
    color: @primary@;
    border-radius: 12px;
    font-size: 21px;
    font-weight: 800;
}
QToolButton#rail_button {
    background: transparent;
    color: @white@;
    border: none;
    border-radius: 10px;
    font-size: 21px;
    font-weight: 500;
}
QToolButton#rail_button:hover { background: @primary_hover@; }
QToolButton#rail_button:checked { background: @white@; color: @primary@; }
QFrame#workflowbar { background: @surface@; border: none; border-bottom: 1px solid @border@; }
QLabel#workflow_caption { color: @muted@; font-size: 12px; font-weight: 600; }
QToolButton#workflow_step {
    background: @surface_alt@;
    color: @text_secondary@;
    border: 1px solid @border@;
    border-radius: 8px;
    padding: 0 14px;
    text-align: left;
    font-size: 13px;
    font-weight: 600;
}
QToolButton#workflow_step:hover { color: @primary@; border-color: @primary@; }
QToolButton#workflow_step:checked {
    background: @primary_soft@;
    color: @primary_ink@;
    border-color: @primary@;
}
QFrame#context_panel, QFrame#tree_panel {
    background: @surface@;
    border: 1px solid @border@;
    border-radius: 8px;
}
QLabel#project_value { color: @text@; font-size: 13px; font-weight: 600; }
QLabel#context_hint { color: @primary_ink@; background: @primary_soft@; border-radius: 6px; padding: 8px; }
QPushButton#domain_tab_active {
    background: @surface@;
    color: @primary@;
    border: 1px solid @border@;
    border-bottom: 2px solid @primary@;
    border-radius: 6px 6px 0 0;
    padding: 0 14px;
    font-weight: 600;
}
QFrame#record_editor { background: @surface@; border: 1px solid @border@; border-radius: 8px; }
QLabel#evidence_summary { color: @text_secondary@; font-size: 11px; }
QLabel#nav_section {
    color: @nav_section@;
    font-size: 11px;
    font-weight: 600;
    background: transparent;
    padding: 0px 4px;
}
QToolButton#nav {
    background: transparent;
    color: @nav_text@;
    border: none;
    border-radius: 6px;
    padding: 9px 10px 9px 12px;
    text-align: left;
    font-size: 13px;
}
QToolButton#nav:hover { background: @nav_alt@; color: @nav_text_strong@; }
QToolButton#nav:checked {
    background: @nav_alt@;
    color: @nav_text_strong@;
    font-weight: 600;
    border-left: 2px solid @primary@;
    padding-left: 10px;
}
QFrame#sidebar_footer { background: @nav_alt@; border: none; border-radius: 8px; }
QLabel#sidebar_footer_key { color: @nav_section@; font-size: 11px; background: transparent; }
QLabel#sidebar_footer_value {
    color: @nav_text@;
    font-size: 11px;
    font-family: @font_mono@;
    background: transparent;
}
QToolButton#ai_rail {
    background: @ai_soft@;
    color: @ai_ink@;
    border: none;
    font-size: 12px;
    font-weight: 600;
}
QToolButton#ai_rail:hover { background: @ai@; color: @white@; }

/* ============================ 页头 ============================ */
QLabel#page_title { color: @text@; font-size: 17px; font-weight: 700; }
QLabel#page_sub { color: @muted@; font-size: 12px; }
QLabel#section_title { color: @text@; font-size: 15px; font-weight: 600; }
QLabel#section_sub { color: @muted@; font-size: 12px; }
QLabel#h1 { color: @text@; font-size: 24px; font-weight: 700; }
QLabel#h2 { color: @text@; font-size: 15px; font-weight: 600; }
QLabel#muted { color: @muted@; }
QLabel#secondary { color: @text_secondary@; }
QLabel#mono {
    color: @text_secondary@;
    font-family: @font_mono@;
    font-size: 12px;
}

/* ============================ 卡片 ============================ */
QFrame#card {
    background: @surface@;
    border: 1px solid @border@;
    border-radius: 10px;
}
QFrame#card_flat {
    background: @surface_alt@;
    border: 1px solid @border@;
    border-radius: 8px;
}
QFrame#card_clickable:hover { border-color: @primary@; }
QFrame#divider { background: @border@; border: none; }
QFrame#card_header { background: @surface_alt@; border: none; }
QFrame#stat_card {
    background: @surface@;
    border: 1px solid @border@;
    border-radius: 10px;
}
QLabel#stat_value {
    color: @text@;
    font-size: 24px;
    font-weight: 700;
    font-family: @font_mono@;
}
QLabel#stat_label { color: @muted@; font-size: 12px; }
QLabel#stat_hint { color: @muted@; font-size: 11px; }

/* ============================ 徽章 / 状态点 ============================ */
QLabel#badge {
    border-radius: 9px;
    padding: 2px 9px;
    font-size: 11px;
    font-weight: 600;
}
QLabel#badge[tone="ok"] { background: @success_soft@; color: @success_ink@; }
QLabel#badge[tone="warn"] { background: @warning_soft@; color: @warning_ink@; }
QLabel#badge[tone="bad"] { background: @danger_soft@; color: @danger_ink@; }
QLabel#badge[tone="info"] { background: @primary_soft@; color: @primary_ink@; }
QLabel#badge[tone="neutral"] { background: @neutral_soft@; color: @neutral@; }
QLabel#badge[tone="ai"] { background: @ai_soft@; color: @ai_ink@; }
QLabel#chip {
    background: @surface_sunken@;
    color: @text_secondary@;
    border: 1px solid @border@;
    border-radius: 11px;
    padding: 2px 10px;
    font-size: 11px;
}
QLabel#nav_badge {
    background: @nav_alt@;
    color: @nav_text@;
    border-radius: 9px;
    padding: 1px 8px;
    font-size: 11px;
    font-family: @font_mono@;
}

/* ============================ 按钮 ============================ */
QPushButton {
    background: @surface@;
    color: @text@;
    border: 1px solid @border_strong@;
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 13px;
}
QPushButton:hover { border-color: @primary@; color: @primary@; }
QPushButton:pressed { background: @surface_alt@; }
QPushButton:disabled { color: @muted@; border-color: @border@; background: @surface_alt@; }
QPushButton#primary {
    background: @primary@;
    border-color: @primary@;
    color: @white@;
    font-weight: 600;
}
QPushButton#primary:hover { background: @primary_hover@; border-color: @primary_hover@; color: @white@; }
QPushButton#primary:disabled { background: @border_strong@; border-color: @border_strong@; color: @white@; }
QPushButton#danger { color: @danger@; border-color: @danger@; background: @surface@; }
QPushButton#danger:hover { background: @danger_soft@; }
QPushButton#ghost { background: transparent; border: 1px solid transparent; color: @primary@; }
QPushButton#ghost:hover { background: @primary_soft@; }
QPushButton#subtle {
    background: @surface_alt@;
    border: 1px solid @border@;
    color: @text_secondary@;
}
QPushButton#subtle:hover { border-color: @primary@; color: @primary@; }
QPushButton#topbar_button {
    background: @surface@;
    border: 1px solid @border@;
    color: @text_secondary@;
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 12px;
}
QPushButton#topbar_button:hover { color: @primary@; border-color: @primary@; }
QPushButton#topbar_primary {
    background: @primary@;
    border: 1px solid @primary@;
    color: @white@;
    border-radius: 6px;
    padding: 4px 12px;
    font-size: 12px;
    font-weight: 600;
}
QPushButton#topbar_primary:hover { background: @primary_hover@; }
QToolButton#icon {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 5px 8px;
    color: @text_secondary@;
}
QToolButton#icon:hover { background: @surface_alt@; color: @primary@; }

/* ============================ 输入 ============================ */
QLineEdit, QComboBox, QDateEdit, QTextEdit, QTextBrowser, QSpinBox, QPlainTextEdit {
    background: @surface@;
    color: @text@;
    border: 1px solid @border_strong@;
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: @selection@;
    selection-color: @text@;
}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTextEdit:focus,
QSpinBox:focus, QPlainTextEdit:focus { border: 1px solid @primary@; }
QLineEdit:disabled, QComboBox:disabled { color: @muted@; background: @surface_alt@; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: @surface@;
    border: 1px solid @border_strong@;
    selection-background-color: @primary_soft@;
    selection-color: @primary_ink@;
    outline: none;
}
QTextBrowser#evidence {
    background: @code_bg@;
    color: @code_text@;
    border: 1px solid @border@;
    border-radius: 8px;
    font-family: @font_mono@;
    font-size: 12px;
    padding: 10px;
}
QTextEdit#log {
    background: @surface_sunken@;
    border: 1px solid @border@;
    border-radius: 8px;
    font-family: @font_mono@;
    font-size: 12px;
    color: @text_secondary@;
}

/* ============================ 表格 ============================ */
QTableWidget, QTableView {
    background: @surface@;
    alternate-background-color: @row_alt@;
    border: 1px solid @border@;
    border-radius: 8px;
    gridline-color: @line_soft@;
    selection-background-color: @primary_soft@;
    selection-color: @text@;
    outline: none;
}
QTableWidget::item, QTableView::item { padding: 6px 8px; border: none; }
QTableWidget::item:selected, QTableView::item:selected {
    background: @primary_soft@;
    color: @text@;
}
QHeaderView::section {
    background: @header_bg@;
    color: @text_secondary@;
    border: none;
    border-bottom: 1px solid @border@;
    border-right: 1px solid @line_soft@;
    padding: 8px;
    font-weight: 600;
    font-size: 12px;
}
QTableCornerButton::section { background: @header_bg@; border: none; }

/* ============================ 列表 / 树 ============================ */
QListWidget, QTreeWidget, QTreeView {
    background: @surface@;
    border: 1px solid @border@;
    border-radius: 8px;
    color: @text@;
    outline: none;
}
QListWidget::item { padding: 7px 9px; border-radius: 6px; margin: 1px 4px; }
QListWidget::item:hover { background: @surface_alt@; }
QListWidget::item:selected { background: @primary_soft@; color: @primary_ink@; }
QTreeWidget::item, QTreeView::item { padding: 6px; }
QTreeWidget::item:selected, QTreeView::item:selected {
    background: @primary_soft@;
    color: @primary_ink@;
}

/* ============================ 容器 ============================ */
QSplitter::handle { background: @border@; }
QSplitter::handle:horizontal { width: 1px; }
QSplitter::handle:vertical { height: 1px; }
QGroupBox {
    background: @surface@;
    border: 1px solid @border@;
    border-radius: 10px;
    margin-top: 14px;
    padding: 12px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: @text@;
    font-weight: 600;
}
QTabWidget::pane {
    border: 1px solid @border@;
    border-radius: 8px;
    background: @surface@;
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    color: @text_secondary@;
    padding: 8px 16px;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:selected { color: @primary@; border-bottom: 2px solid @primary@; }
QTabBar::tab:hover { color: @primary@; }

/* ============================ 拖拽上传区 ============================ */
QFrame#dropzone {
    background: @surface@;
    border: 2px dashed @upload_border@;
    border-radius: 10px;
}
QFrame#dropzone[active="true"] {
    background: @primary_soft@;
    border: 2px dashed @primary@;
}
QLabel#dropzone_title { color: @text@; font-size: 15px; font-weight: 600; }
QLabel#dropzone_hint { color: @muted@; font-size: 12px; }

/* ============================ 状态栏 ============================ */
QStatusBar { background: @surface_alt@; border-top: 1px solid @border@; }
QStatusBar::item { border: none; }
QLabel#status_text {
    color: @status_text@;
    font-family: @font_mono@;
    font-size: 11px;
}

/* ============================ 工作台：工具栏 ============================ */
QFrame#workspace_toolbar {
    background: @surface@;
    border: none;
    border-bottom: 1px solid @border@;
    min-height: 48px;
}
QLineEdit#toolbar_search {
    background: @surface_sunken@;
    border: 1px solid @border@;
    border-radius: 6px;
    padding: 5px 10px;
    min-width: 220px;
}
QPushButton#filter_chip {
    background: @surface@;
    color: @text_secondary@;
    border: 1px solid @border_strong@;
    border-radius: 999px;
    padding: 4px 12px;
    font-size: 12px;
}
QPushButton#filter_chip:hover { border-color: @primary@; color: @primary@; }
QPushButton#filter_chip:checked {
    background: @primary_soft@;
    color: @primary_ink@;
    border-color: @primary@;
    font-weight: 600;
}
QFrame#metric_pill, QLabel#metric_pill {
    background: @surface_sunken@;
    color: @text_secondary@;
    border: 1px solid @border@;
    border-radius: 999px;
    padding: 4px 12px;
    font-size: 12px;
}
QLabel#metric_pill_label { color: @muted@; font-size: 12px; background: transparent; }
QLabel#metric_pill_value {
    color: @text@;
    font-size: 13px;
    font-weight: 700;
    font-family: @font_mono@;
    background: transparent;
}

/* ============================ 工作台：安全域页签 ============================ */
QTabBar#domain_tabs { background: transparent; }
QTabBar#domain_tabs::tab {
    background: transparent;
    color: @text_secondary@;
    padding: 7px 14px;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: 13px;
}
QTabBar#domain_tabs::tab:hover { color: @primary@; }
QTabBar#domain_tabs::tab:selected {
    color: @primary@;
    border-bottom: 2px solid @primary@;
    font-weight: 600;
}

/* ============================ 工作台：记录表 ============================ */
QTableWidget#records_table QHeaderView::section {
    background: @table_header_bg@;
    color: @text_secondary@;
    border: none;
    border-bottom: 1px solid @border@;
    border-right: 1px solid @line_soft@;
    padding: 0 10px;
    height: 32px;
    font-weight: 600;
    font-size: 12px;
}
QTableWidget#records_table::item {
    height: 34px;
    padding: 0 10px;
    border: none;
}
QTableWidget#records_table::item:hover { background: @table_row_hover@; }
QTableWidget#records_table::item:selected {
    background: @table_row_selected@;
    color: @text@;
}

/* ============================ 工作台：步骤条 ============================ */
QFrame#stepbar {
    background: @stepbar_bg@;
    border: none;
    border-bottom: 1px solid @border@;
    min-height: 46px;
}
#step_item { background: transparent; border: none; color: @step_todo@; }
#step_item[state="done"] { color: @step_done@; }
#step_item[state="todo"] { color: @step_todo@; }
#step_item[state="blocked"] { color: @step_blocked@; }

/* ============================ 工作台：侧边检查器 ============================ */
QFrame#inspector {
    background: @inspector_bg@;
    border: none;
    border-left: 1px solid @inspector_border@;
}
QFrame#inspector_header {
    background: @inspector_bg@;
    border: none;
    border-bottom: 1px solid @inspector_border@;
    min-height: 44px;
}
QLabel#inspector_title { color: @text@; font-size: 13px; font-weight: 600; background: transparent; }
QPushButton#inspector_close {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    color: @text_secondary@;
    padding: 2px 8px;
    font-size: 13px;
}
QPushButton#inspector_close:hover { background: @surface_alt@; color: @text@; }

/* ============================ 工作台：状态栏 ============================ */
QFrame#statusbar {
    background: @statusbar_bg@;
    border: none;
    border-top: 1px solid @border@;
    min-height: 26px;
}
QLabel#status_segment {
    color: @statusbar_text@;
    font-family: @font_mono@;
    font-size: 11px;
    background: transparent;
    padding: 0 8px;
}

/* ============================ 滚动条 ============================ */
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: @border_strong@; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: @muted@; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: @border_strong@; border-radius: 4px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: @muted@; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
"""


def render_qss(palette: dict[str, str], font_family: str = FONT_FAMILY) -> str:
    """把调色板代入 QSS 模板。"""
    qss = _QSS_TEMPLATE
    for key, value in palette.items():
        qss = qss.replace(f"@{key}@", value)
    qss = qss.replace("@font_family@", font_family)
    qss = qss.replace("@font_mono@", FONT_MONO)
    return qss


def restyle(widget) -> None:
    """动态属性（tone / active）变化后重新应用样式。"""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


class ThemeManager:
    """读取/写入主题偏好并应用到 QApplication。"""

    def __init__(
        self,
        app: QApplication,
        get_pref: Callable[[], str] | None = None,
        set_pref: Callable[[str], None] | None = None,
        font_family: str = FONT_FAMILY,
    ) -> None:
        self._app = app
        self._get_pref = get_pref or (lambda: "light")
        self._set_pref = set_pref or (lambda _name: None)
        self._font = font_family

    def current(self) -> str:
        name = (self._get_pref() or "light").strip().lower()
        return name if name in PALETTES else "light"

    def apply(self, name: str | None = None) -> str:
        name = (name or self.current()).strip().lower()
        if name not in PALETTES:
            name = "light"
        self._app.setStyleSheet(render_qss(PALETTES[name], self._font))
        self._set_pref(name)
        return name

    def toggle(self) -> str:
        return self.apply("dark" if self.current() == "light" else "light")
