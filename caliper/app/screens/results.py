"""现场核查工作区：领域页签 + 资产树 + 记录导航 + 核查内容/证据阅读 + 结果记录编辑。

信息架构借鉴测评行业通行布局（左目录 / 中阅读 / 右判定与结果记录）：
- 左栏：设备与资产树 + 当前资产的核查记录目录；
- 中栏：核查内容、判定标准、证据原文三块只读参考；
- 右栏：结果判定下拉框 + 结果记录大编辑区（本页核心）+ 备注 / 修改理由 / 整改建议。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from adapters.llm import build_payload
from app.controller import AppController, ControllerError
from app.screens.dialogs import PolishPreviewDialog, RecordPreviewDialog, TextDetailsDialog
from app.widgets import Badge, ComplianceBadge, DomainTabs, EmptyState, FilterChip
from core.contracts.verdict import Verdict
from core.model.entities import Item, ItemResult
from core.remediation import Advice
from core.traceability import standard_references

VERDICT_TONES = {
    Verdict.COMPLIANT: "ok",
    Verdict.PARTIAL: "warn",
    Verdict.NON_COMPLIANT: "bad",
    Verdict.NOT_APPLICABLE: "neutral",
    Verdict.UNCOLLECTED: "info",
}

# 结果判定下拉框的固定顺序（与五值落表口径一致）。
VERDICT_ORDER = (
    Verdict.COMPLIANT,
    Verdict.PARTIAL,
    Verdict.NON_COMPLIANT,
    Verdict.NOT_APPLICABLE,
    Verdict.UNCOLLECTED,
)

DOMAINS = (
    ("general", "安全通用要求"),
    ("computing", "安全计算环境"),
    ("database", "数据库"),
    ("middleware", "中间件"),
)
# 当前规则包没有项级领域字段，按资产类型映射到领域页签。
DOMAIN_ASSET_TYPES = {
    "computing": {"服务器", "终端设备"},
    "database": {"数据库"},
    "middleware": {"中间件"},
}
FILTERS = (
    ("all", "全部"),
    ("compliant", "符合"),
    ("partial", "部分符合"),
    ("non_compliant", "不符合"),
    ("not_applicable", "不适用"),
    ("uncollected", "未采集"),
)
FILTER_VERDICTS = {
    "compliant": Verdict.COMPLIANT,
    "partial": Verdict.PARTIAL,
    "non_compliant": Verdict.NON_COMPLIANT,
    "not_applicable": Verdict.NOT_APPLICABLE,
    "uncollected": Verdict.UNCOLLECTED,
}

LEFT_PANEL_WIDTH = 300
EDITOR_WIDTH = 380


class ResultsScreen(QWidget):
    """现场核查工作台：左目录 / 中阅读 / 右判定与结果记录。"""

    def __init__(self, controller: AppController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.current_result: ItemResult | None = None
        self.current_advice: Advice | None = None
        self._items: dict[int, Item] = {}
        self._visible_results: list[ItemResult] = []
        self._domain_runs: list = []
        self._domain_key = DOMAINS[0][0]
        self._filter_key = "all"
        self._diagnostic_entries: list[tuple[str, str]] = []
        self._tree_signals_blocked = False
        self.setObjectName("page")

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)

        heading = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        self.heading = QLabel("现场核查")
        self.heading.setObjectName("page_title")
        self.subheading = QLabel("核对测评项证据与判定标准，编写并确认结果记录")
        self.subheading.setObjectName("page_sub")
        title_box.addWidget(self.heading)
        title_box.addWidget(self.subheading)
        heading.addLayout(title_box)
        heading.addStretch(1)
        self.summary = QLabel("尚未生成记录草稿")
        self.summary.setObjectName("muted")
        heading.addWidget(self.summary)
        root.addLayout(heading)

        self.page_stack = QStackedWidget()
        self.page_empty = EmptyState(
            "尚未生成记录草稿",
            "前往「材料与资产」导入现场材料并生成记录草稿后，资产与核查记录会显示在这里。",
        )
        self.page_stack.addWidget(self.page_empty)
        self.workspace = self._build_workspace()
        self.page_stack.addWidget(self.workspace)
        root.addWidget(self.page_stack, 1)
        self.refresh()

    # ------------------------------------------------------------------ 构建
    def _build_workspace(self) -> QWidget:
        host = QWidget()
        column = QVBoxLayout(host)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(8)

        column.addWidget(self._build_diagnostic_banner())
        self.domain_tabs = DomainTabs()
        self.domain_tabs.setFixedHeight(40)
        self.domain_tabs.set_domains([(key, label, 0, 0) for key, label in DOMAINS])
        self.domain_tabs.domain_changed.connect(self._on_domain_changed)
        column.addWidget(self.domain_tabs)

        column.addWidget(self._build_toolbar())
        column.addWidget(self._build_filter_row())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(10)
        body.addWidget(self._build_left_panel())
        body.addWidget(self._build_reading_pane(), 1)
        body.addWidget(self._build_editor())
        column.addLayout(body, 1)
        return host

    def _build_diagnostic_banner(self) -> QFrame:
        self.diagnostic_banner = QFrame()
        self.diagnostic_banner.setObjectName("context_panel")
        layout = QHBoxLayout(self.diagnostic_banner)
        layout.setContentsMargins(12, 7, 10, 7)
        layout.setSpacing(10)
        title = QLabel("判定范围提示")
        title.setObjectName("secondary")
        self.diagnostic_summary = QLabel("")
        self.diagnostic_summary.setObjectName("muted")
        self.diagnostic_summary.setWordWrap(True)
        details = QPushButton("查看明细")
        details.setObjectName("subtle")
        details.clicked.connect(self._show_diagnostics)
        layout.addWidget(title)
        layout.addWidget(self.diagnostic_summary, 1)
        layout.addWidget(details)
        self.diagnostic_banner.hide()
        return self.diagnostic_banner

    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("workspace_toolbar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(10, 7, 10, 7)
        row.setSpacing(8)
        self.search = QLineEdit()
        self.search.setObjectName("toolbar_search")
        self.search.setPlaceholderText("搜索控制点、控制项、结果记录或备注")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._populate_records)
        row.addWidget(self.search, 1)
        self.row_count = QLabel("0 / 0 项")
        self.row_count.setObjectName("muted")
        row.addWidget(self.row_count)
        self.record_preview_button = QPushButton("记录表预览")
        self.record_preview_button.setObjectName("subtle")
        self.record_preview_button.clicked.connect(self._preview_record)
        self.generate_record_button = QPushButton("生成记录表")
        self.generate_record_button.setObjectName("subtle")
        self.generate_record_button.clicked.connect(self._generate_record)
        self.refresh_button = QPushButton("刷新")
        self.refresh_button.setObjectName("subtle")
        self.refresh_button.clicked.connect(self.refresh)
        row.addWidget(self.record_preview_button)
        row.addWidget(self.generate_record_button)
        row.addWidget(self.refresh_button)
        return bar

    def _build_filter_row(self) -> QWidget:
        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(2, 0, 2, 0)
        row.setSpacing(6)
        self.filter_chips: dict[str, FilterChip] = {}
        for key, label in FILTERS:
            chip = FilterChip(label, key)
            if key == self._filter_key:
                chip.setChecked(True)
            chip.clicked.connect(lambda _checked=False, name=key: self._apply_filter(name))
            self.filter_chips[key] = chip
            row.addWidget(chip)
        row.addStretch(1)
        return host

    def _build_left_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("tree_panel")
        panel.setFixedWidth(LEFT_PANEL_WIDTH)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 8, 8)
        layout.setSpacing(8)

        title = QLabel("设备与资产")
        title.setObjectName("section_title")
        layout.addWidget(title)
        self.asset_search = QLineEdit()
        self.asset_search.setPlaceholderText("搜索资产")
        self.asset_search.setClearButtonEnabled(True)
        self.asset_search.textChanged.connect(self._on_asset_search)
        layout.addWidget(self.asset_search)

        self.asset_stack = QStackedWidget()
        self.asset_tree = QTreeWidget()
        self.asset_tree.setHeaderHidden(True)
        self.asset_tree.setIndentation(14)
        self.asset_tree.currentItemChanged.connect(self._on_asset_selected)
        self.asset_empty = EmptyState("当前领域暂无资产", "切换领域页签或前往「材料与资产」导入材料。")
        self.asset_stack.addWidget(self.asset_tree)
        self.asset_stack.addWidget(self.asset_empty)
        layout.addWidget(self.asset_stack, 2)

        records_title = QLabel("核查记录")
        records_title.setObjectName("section_title")
        layout.addWidget(records_title)
        self.record_stack = QStackedWidget()
        self.record_list = QListWidget()
        self.record_list.setObjectName("record_list")
        self.record_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.record_list.currentItemChanged.connect(self._on_record_selected)
        self.record_empty = EmptyState("暂无核查记录", "选择设备后，这里列出该设备的测评项目录。")
        self.record_stack.addWidget(self.record_list)
        self.record_stack.addWidget(self.record_empty)
        layout.addWidget(self.record_stack, 3)
        return panel

    def _build_reading_pane(self) -> QWidget:
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.reading_stack = QStackedWidget()
        self.reading_placeholder = QWidget()
        placeholder_layout = QVBoxLayout(self.reading_placeholder)
        placeholder_layout.setContentsMargins(0, 0, 0, 0)
        placeholder_layout.addWidget(
            EmptyState("选择一条核查记录", "左侧选择设备与测评项后，这里显示核查内容、判定标准与证据原文。"),
            1,
        )
        self.reading_stack.addWidget(self.reading_placeholder)
        self.reading_stack.addWidget(self._build_reading_form())
        layout.addWidget(self.reading_stack, 1)
        return host

    def _build_reading_form(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        head = QHBoxLayout()
        self.selected_title = QLabel("—")
        self.selected_title.setObjectName("section_title")
        self.selected_title.setWordWrap(True)
        head.addWidget(self.selected_title, 1)
        layout.addLayout(head)

        self.record_meta = QLabel("")
        self.record_meta.setObjectName("muted")
        self.record_meta.setWordWrap(True)
        layout.addWidget(self.record_meta)

        layout.addWidget(self._section_label("核查内容"))
        self.check_content_label = QLabel("")
        self.check_content_label.setObjectName("reading_text")
        self.check_content_label.setWordWrap(True)
        self.check_content_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.check_content_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        layout.addWidget(self.check_content_label)

        layout.addWidget(self._section_label("判定标准"))
        self.criteria_label = QLabel("")
        self.criteria_label.setObjectName("reading_text")
        self.criteria_label.setWordWrap(True)
        self.criteria_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.criteria_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        layout.addWidget(self.criteria_label)

        layout.addWidget(self._section_label("证据原文"))
        self.evidence_browser = QTextBrowser()
        self.evidence_browser.setObjectName("evidence")
        self.evidence_browser.setOpenExternalLinks(False)
        self.evidence_browser.setMinimumHeight(180)
        layout.addWidget(self.evidence_browser, 1)

        layout.addStretch(1)
        scroll.setWidget(content)
        return scroll

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("secondary")
        return label

    def _build_editor(self) -> QFrame:
        editor = QFrame()
        editor.setObjectName("record_editor")
        editor.setFixedWidth(EDITOR_WIDTH)
        layout = QVBoxLayout(editor)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        head = QHBoxLayout()
        editor_title = QLabel("结果记录")
        editor_title.setObjectName("section_title")
        self.record_badge = Badge("待核对", "neutral")
        head.addWidget(editor_title)
        head.addStretch(1)
        head.addWidget(self.record_badge)
        layout.addLayout(head)

        verdict_label = QLabel("结果判定")
        verdict_label.setObjectName("secondary")
        layout.addWidget(verdict_label)
        self.verdict = QComboBox()
        for value in VERDICT_ORDER:
            self.verdict.addItem(value.value, value.value)
        layout.addWidget(self.verdict)

        record_label = QLabel("结果记录（现场核查结论，可编辑）")
        record_label.setObjectName("secondary")
        layout.addWidget(record_label)
        self.record_text = QPlainTextEdit()
        self.record_text.setPlaceholderText("依据核查内容与证据原文，记录现场核查过程和结论")
        self.record_text.setMinimumHeight(200)
        layout.addWidget(self.record_text, 3)

        note_label = QLabel("备注")
        note_label.setObjectName("secondary")
        layout.addWidget(note_label)
        self.note_text = QPlainTextEdit()
        self.note_text.setPlaceholderText("可选")
        self.note_text.setFixedHeight(64)
        layout.addWidget(self.note_text)

        reason_label = QLabel("修改理由")
        reason_label.setObjectName("secondary")
        layout.addWidget(reason_label)
        self.reason = QLineEdit()
        self.reason.setPlaceholderText("人工修改或补录时说明理由")
        layout.addWidget(self.reason)

        advice_title = QLabel("整改建议")
        advice_title.setObjectName("secondary")
        layout.addWidget(advice_title)
        self.remediation_body = QLabel("选择一条记录查看整改建议")
        self.remediation_body.setObjectName("muted")
        self.remediation_body.setWordWrap(True)
        self.remediation_body.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.remediation_body.setMinimumHeight(64)
        layout.addWidget(self.remediation_body)

        actions = QHBoxLayout()
        self.reset_button = QPushButton("恢复建议")
        self.reset_button.setObjectName("subtle")
        self.reset_button.clicked.connect(self._reset_override)
        self.polish_button = QPushButton("润色预览")
        self.polish_button.setObjectName("subtle")
        self.polish_button.setEnabled(False)
        self.polish_button.clicked.connect(self._preview_polish)
        self.save_button = QPushButton("保存并确认")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self._save_record)
        actions.addWidget(self.reset_button)
        actions.addWidget(self.polish_button)
        actions.addStretch(1)
        actions.addWidget(self.save_button)
        layout.addLayout(actions)
        return editor

    # ------------------------------------------------------------------ 刷新
    def refresh(self) -> None:
        self._items = {}
        try:
            pack = self.controller.pack or self.controller.load_pack()
            self._items = {
                item.seq: item
                for item in pack.items_for_level(self.controller.project.level)
            }
        except Exception:  # noqa: BLE001 - 规则包不可用时页面仍需展示空状态
            pass

        result = self.controller.run_result
        if result is None:
            self._diagnostic_entries = []
            self.diagnostic_banner.hide()
            self._domain_runs = []
            self.asset_tree.clear()
            self.asset_stack.setCurrentWidget(self.asset_empty)
            self.asset_empty.set_text("当前领域暂无资产", "前往「材料与资产」导入现场材料并生成记录草稿。")
            self._clear_record_list()
            self._clear_editor()
            self.summary.setText("尚未生成记录草稿")
            self.page_stack.setCurrentWidget(self.page_empty)
            return

        self.page_stack.setCurrentWidget(self.workspace)
        diagnostics = [
            (run.asset.device_name, diagnostic)
            for run in result.asset_runs
            for diagnostic in run.diagnostics
        ]
        self._diagnostic_entries = diagnostics
        if diagnostics:
            self.diagnostic_summary.setText(
                f"当前有 {len(diagnostics)} 条提示，涉及材料映射、系统适用性或规则覆盖。"
                "自动结论仅适用于已映射且已实现的规则。"
            )
            self.diagnostic_banner.show()
        else:
            self.diagnostic_banner.hide()

        preferred = self.domain_tabs.current_key() or self._domain_key
        self._update_domain_tabs(result, preferred)
        self._rebuild_tree(preserve=True, select_first=True)
        self._populate_records(auto_select=True)

        checked = total = 0
        for run in result.asset_runs:
            total += len(run.items)
            checked += sum(1 for item in run.items if item.verdict != Verdict.UNCOLLECTED)
        self.summary.setText(f"设备 {len(result.asset_runs)} · 已核查 {checked}/{total}")

    def _update_domain_tabs(self, result, preferred: str) -> None:
        domains = []
        for key, label in DOMAINS:
            runs = self._runs_for_domain(result, key)
            total = sum(len(run.items) for run in runs)
            checked = sum(
                1
                for run in runs
                for item in run.items
                if item.verdict != Verdict.UNCOLLECTED
            )
            domains.append((key, label, checked, total))
        keys = [key for key, _label in DOMAINS]
        if preferred not in keys:
            preferred = keys[0]
        self._domain_key = preferred
        self.domain_tabs.blockSignals(True)
        self.domain_tabs.set_domains(domains)
        self.domain_tabs.setCurrentIndex(keys.index(preferred))
        self.domain_tabs.blockSignals(False)

    @staticmethod
    def _runs_for_domain(result, key: str) -> list:
        if key == "general":
            return list(result.asset_runs)
        allowed = DOMAIN_ASSET_TYPES.get(key, set())
        return [
            run
            for run in result.asset_runs
            if run.asset.asset_type.value in allowed
        ]

    def _rebuild_tree(self, preserve: bool, select_first: bool) -> None:
        result = self.controller.run_result
        if result is None:
            self._domain_runs = []
            self._tree_signals_blocked = True
            self.asset_tree.blockSignals(True)
            self.asset_tree.clear()
            self.asset_tree.blockSignals(False)
            self._tree_signals_blocked = False
            self.asset_stack.setCurrentWidget(self.asset_empty)
            return

        previous = self._selected_device() if preserve else ""
        keyword = self.asset_search.text().strip().lower()
        runs = self._runs_for_domain(result, self._domain_key)
        if keyword:
            runs = [run for run in runs if keyword in self._asset_haystack(run)]
        self._domain_runs = runs

        groups: dict[str, QTreeWidgetItem] = {}
        group_counts: dict[str, list[int]] = {}
        for run in runs:
            type_name = run.asset.asset_type.value
            counts = group_counts.setdefault(type_name, [0, 0])
            counts[0] += sum(1 for item in run.items if item.verdict != Verdict.UNCOLLECTED)
            counts[1] += len(run.items)

        self._tree_signals_blocked = True
        self.asset_tree.blockSignals(True)
        self.asset_tree.clear()
        for index, run in enumerate(runs):
            type_name = run.asset.asset_type.value
            group = groups.get(type_name)
            if group is None:
                checked, total = group_counts[type_name]
                group = QTreeWidgetItem([f"{type_name}  ({checked}/{total})"])
                group.setFlags(group.flags() & ~Qt.ItemIsSelectable)
                groups[type_name] = group
                self.asset_tree.addTopLevelItem(group)
            checked = sum(1 for item in run.items if item.verdict != Verdict.UNCOLLECTED)
            child = QTreeWidgetItem([f"{run.asset.device_name}  ({checked}/{len(run.items)})"])
            child.setData(0, Qt.UserRole, index)
            child.setToolTip(0, run.asset.device_name)
            group.addChild(child)
            group.setExpanded(True)

        target = None
        if previous:
            for top in range(self.asset_tree.topLevelItemCount()):
                group = self.asset_tree.topLevelItem(top)
                for child_index in range(group.childCount()):
                    if group.child(child_index).toolTip(0) == previous:
                        target = group.child(child_index)
                        break
                if target is not None:
                    break
        if target is None and select_first and self.asset_tree.topLevelItemCount():
            first_group = self.asset_tree.topLevelItem(0)
            if first_group.childCount():
                target = first_group.child(0)
        if target is not None:
            self.asset_tree.setCurrentItem(target)
        else:
            self.asset_tree.setCurrentItem(None)
        self.asset_tree.blockSignals(False)
        self._tree_signals_blocked = False

        if runs:
            self.asset_stack.setCurrentWidget(self.asset_tree)
        else:
            if keyword:
                self.asset_empty.set_text("没有匹配的资产", "调整资产搜索关键词后重试。")
            else:
                self.asset_empty.set_text(
                    "当前领域暂无资产",
                    "切换领域页签或前往「材料与资产」导入材料。",
                )
            self.asset_stack.setCurrentWidget(self.asset_empty)

    @staticmethod
    def _asset_haystack(run) -> str:
        asset = run.asset
        return f"{asset.device_name} {asset.ip} {asset.asset_type.value}".lower()

    def _on_asset_search(self, *_args) -> None:
        self._rebuild_tree(preserve=True, select_first=True)
        self._populate_records(auto_select=True)

    def _selected_device(self) -> str:
        current = self.asset_tree.currentItem()
        if current is not None and current.parent() is not None:
            return current.toolTip(0)
        return ""

    def _on_asset_selected(self, current, _previous=None) -> None:
        if self._tree_signals_blocked:
            return
        if current is not None and current.data(0, Qt.UserRole) is not None:
            self._populate_records(auto_select=True)

    def _on_domain_changed(self, key: str) -> None:
        if not key:
            return
        self._domain_key = key
        self.current_result = None
        self.current_advice = None
        self._clear_editor()
        self._rebuild_tree(preserve=False, select_first=True)
        self._populate_records(auto_select=False)

    # ------------------------------------------------------------------ 记录目录
    def _populate_records(self, *_args, auto_select: bool = True) -> None:
        selected_seq = self.current_result.seq if self.current_result else None
        run = self._current_run()
        self.record_list.clear()
        self._visible_results = []

        if run is None:
            self.row_count.setText("0 / 0 项")
            self.record_stack.setCurrentWidget(self.record_empty)
            self._clear_editor()
            return

        keyword = self.search.text().strip().lower()
        filter_verdict = FILTER_VERDICTS.get(self._filter_key)
        for result in run.items:
            item = self._items.get(result.seq)
            control_item = item.control_item if item else result.control_point
            haystack = (
                f"{result.control_point} {control_item} "
                f"{result.result_text} {result.note}"
            ).lower()
            if keyword and keyword not in haystack:
                continue
            if filter_verdict is not None and result.verdict != filter_verdict:
                continue
            self._visible_results.append(result)

        total = len(run.items)
        self.row_count.setText(f"{len(self._visible_results)} / {total} 项")
        for result in self._visible_results:
            item = self._items.get(result.seq)
            self._append_record_item(result, item)

        if self._visible_results:
            self.record_stack.setCurrentWidget(self.record_list)
            if auto_select:
                target = next(
                    (
                        index
                        for index, value in enumerate(self._visible_results)
                        if value.seq == selected_seq
                    ),
                    0,
                )
                self.record_list.setCurrentRow(target)
            else:
                self.record_list.setCurrentRow(-1)
                self._clear_editor()
        else:
            if self._filter_key != "all" or self.search.text().strip():
                self.record_empty.set_text("当前筛选无结果", "调整搜索关键词或恢复「全部」符合情况筛选。")
            else:
                self.record_empty.set_text("暂无核查记录", "该设备没有可展示的核查记录。")
            self.record_stack.setCurrentWidget(self.record_empty)
            self._clear_editor()

    def _append_record_item(self, result: ItemResult, item: Item | None) -> None:
        control_item = item.control_item if item else result.control_point
        if item is not None and ("扩展" in control_item or "扩展" in item.check_content):
            scope = "扩展"
        else:
            scope = "通用"

        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(8, 5, 8, 5)
        row.setSpacing(8)
        label = QLabel(f"{result.seq:02d}　{result.control_point}")
        label.setObjectName("record_list_label")
        label.setToolTip(f"{scope} · {control_item}")
        badge = ComplianceBadge(result.verdict.value)
        badge.setToolTip(f"{result.verdict.value} · {'已确认' if result.reviewed else '待核对'}")
        row.addWidget(label, 1)
        row.addWidget(badge, 0, Qt.AlignVCenter)

        list_item = QListWidgetItem(self.record_list)
        list_item.setData(Qt.UserRole, result.seq)
        list_item.setSizeHint(host.sizeHint())
        self.record_list.setItemWidget(list_item, host)

    def _on_record_selected(self, current, _previous=None) -> None:
        if current is None:
            return
        seq = current.data(Qt.UserRole)
        result = next(
            (entry for entry in self._visible_results if entry.seq == seq), None
        )
        if result is None:
            return
        self.current_result = result
        self._load_reading(result)
        self._load_editor(result)

    def _clear_record_list(self) -> None:
        self.record_list.clear()
        self._visible_results = []
        self.row_count.setText("0 / 0 项")
        self.record_stack.setCurrentWidget(self.record_empty)

    # ------------------------------------------------------------------ 阅读区
    def _load_reading(self, result: ItemResult) -> None:
        run = self._current_run()
        item = self._items.get(result.seq)
        self.reading_stack.setCurrentIndex(1)
        self.selected_title.setText(f"{result.seq:02d}　{result.control_point}")
        meta = f"{result.item_id}　·　重要程度 {result.importance}"
        if run is not None:
            meta += f"　·　{run.asset.device_name}"
            if run.os_family:
                meta += f"　·　{run.os_family}"
        self.record_meta.setText(meta)

        if item is not None:
            self.check_content_label.setText(item.check_content or "（该测评项未配置检查内容）")
            references = standard_references(item)
            criteria = item.criteria or ""
            if references:
                criteria = f"{criteria}\n标准依据：{'；'.join(references)}".strip()
            self.criteria_label.setText(criteria or "（该测评项未配置判断标准）")
        else:
            self.check_content_label.setText("—")
            self.criteria_label.setText("—")

        self.evidence_browser.setPlainText(self._evidence_text(result))

    @staticmethod
    def _evidence_text(result: ItemResult) -> str:
        lines: list[str] = []
        for point in result.points:
            for anchor in point.anchors:
                if not anchor.file:
                    continue
                lines.append(f"# {anchor.file}:{anchor.line}")
                if anchor.snippet:
                    lines.append(anchor.snippet)
                lines.append("")
        files = sorted(
            {
                anchor.file
                for point in result.points
                for anchor in point.anchors
                if anchor.file
            }
        )
        if files:
            lines.append("附件文件：" + "、".join(files))
        return "\n".join(lines) if lines else "暂无证据锚点；请依据现场材料人工核查。"

    # ------------------------------------------------------------------ 编辑区
    def _load_editor(self, result: ItemResult) -> None:
        run = self._current_run()
        index = next(
            (i for i, value in enumerate(VERDICT_ORDER) if value == result.verdict),
            0,
        )
        self.verdict.setCurrentIndex(index)
        self.record_text.setPlainText(result.result_text)
        self.note_text.setPlainText(result.note)
        self.reason.setText(result.override_reason)
        self.record_badge.set_text(
            "已确认" if result.reviewed else "待核对",
            "ok" if result.reviewed else VERDICT_TONES.get(result.verdict, "neutral"),
        )
        self.reset_button.setEnabled(result.manual_override)
        self._load_advice(run, result)

    def _clear_editor(self) -> None:
        self.current_result = None
        self.current_advice = None
        self.reading_stack.setCurrentIndex(0)
        self.record_badge.set_text("待核对", "neutral")
        self.selected_title.setText("—")
        self.record_meta.setText("")
        self.check_content_label.setText("")
        self.criteria_label.setText("")
        self.evidence_browser.clear()
        self.verdict.setCurrentIndex(0)
        self.record_text.clear()
        self.note_text.clear()
        self.reason.clear()
        self.reset_button.setEnabled(False)
        self.polish_button.setEnabled(False)
        self.remediation_body.setText("选择一条记录查看整改建议")

    def _load_advice(self, run, result: ItemResult) -> None:
        """按当前记录取整改建议；未命中也明确说明，不虚构条款。"""
        self.current_advice = None
        try:
            advice = self.controller.remediation_advice(run.asset.device_name, result.seq)
        except ControllerError as exc:
            self.remediation_body.setText(f"整改建议不可用：{exc}")
            self.polish_button.setEnabled(False)
            return
        if advice is None:
            self.remediation_body.setText("规则库无对应建议")
            self.polish_button.setEnabled(False)
            return
        self.current_advice = advice
        self.remediation_body.setText(
            f"{advice.title}\n"
            f"优先级：{advice.priority}　条款：{advice.clause}\n"
            f"规则：{advice.rule_id}\n"
            f"整改动作：{advice.action}"
        )
        self.polish_button.setEnabled(True)

    def _apply_filter(self, key: str) -> None:
        self._filter_key = key
        for name, chip in self.filter_chips.items():
            chip.blockSignals(True)
            chip.setChecked(name == key)
            chip.blockSignals(False)
        self._populate_records(auto_select=True)

    def restore_all_filters(self) -> None:
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self._apply_filter("all")

    # ------------------------------------------------------------------ 记录动作
    def _current_run(self):
        current = self.asset_tree.currentItem()
        if current is None or current.data(0, Qt.UserRole) is None:
            return None
        index = int(current.data(0, Qt.UserRole))
        return self._domain_runs[index] if 0 <= index < len(self._domain_runs) else None

    def _current_asset_key(self) -> str:
        run = self._current_run()
        return run.asset.device_name if run is not None else ""

    def _show_diagnostics(self) -> None:
        if not self._diagnostic_entries:
            return
        details = "\n".join(
            f"【{device}】{message}"
            for device, message in self._diagnostic_entries
        )
        TextDetailsDialog("判定范围与规则覆盖提示", details, self).exec()

    def _preview_record(self) -> None:
        asset_key = self._current_asset_key()
        if not asset_key:
            QMessageBox.information(
                self,
                "记录表预览",
                "当前没有可预览的记录。请先运行核查并在左侧选择设备。",
            )
            return
        try:
            sheet = self.controller.record_sheet(asset_key)
        except ControllerError as exc:
            QMessageBox.warning(self, "无法预览记录表", str(exc))
            return
        RecordPreviewDialog(sheet, self).exec()

    def _generate_record(self) -> None:
        try:
            target = self.controller.generate_record_book()
        except ControllerError as exc:
            QMessageBox.warning(self, "生成记录表失败", str(exc))
            return
        QMessageBox.information(self, "已生成记录表", f"记录表已生成：\n{target}")

    def _preview_polish(self) -> None:
        if self.current_advice is None:
            return
        PolishPreviewDialog(build_payload(self.current_advice), self).exec()

    def _save_record(self) -> None:
        run, result = self._current_run(), self.current_result
        if run is None or result is None:
            return
        verdict_text = str(self.verdict.currentData())
        result_text = self.record_text.toPlainText().strip()
        note = self.note_text.toPlainText().strip()
        selected_verdict = next(value for value in Verdict if value.value == verdict_text)
        if (
            not result.manual_override
            and result_text == (result.auto_result_text or "")
            and note == (result.auto_note or "")
            and selected_verdict == (result.auto_verdict or Verdict.UNCOLLECTED)
        ):
            try:
                result.reviewed_at = self.controller.confirm_record(
                    result.item_id, run.asset.device_name
                )
            except ControllerError as exc:
                QMessageBox.warning(self, "未能确认", str(exc))
                return
            result.reviewed = True
        else:
            try:
                reviewed_at = self.controller.save_record_override(
                    result.item_id,
                    run.asset.device_name,
                    result_text,
                    selected_verdict.value,
                    note,
                    self.reason.text().strip(),
                )
            except (ControllerError, ValueError) as exc:
                QMessageBox.warning(self, "未能保存", str(exc))
                return
            result.result_text, result.verdict, result.note = result_text, selected_verdict, note
            result.manual_override = True
            result.override_reason = self.reason.text().strip()
            result.reviewed_at = reviewed_at
            result.reviewed = True
        self._refresh_after_record_change()

    def _reset_override(self) -> None:
        run, result = self._current_run(), self.current_result
        if run is None or result is None or not result.manual_override:
            return
        try:
            self.controller.clear_record_override(result.item_id, run.asset.device_name)
        except ControllerError as exc:
            QMessageBox.warning(self, "无法恢复", str(exc))
            return
        result.result_text = result.auto_result_text or ""
        result.verdict = result.auto_verdict or Verdict.UNCOLLECTED
        result.note = result.auto_note or ""
        result.manual_override = result.reviewed = False
        result.override_reason = result.reviewed_at = ""
        self._refresh_after_record_change()

    def _refresh_after_record_change(self) -> None:
        result = self.controller.run_result
        if result is not None:
            self._update_domain_tabs(result, self._domain_key)
            checked = total = 0
            for run in result.asset_runs:
                total += len(run.items)
                checked += sum(
                    1 for item in run.items if item.verdict != Verdict.UNCOLLECTED
                )
            self.summary.setText(f"设备 {len(result.asset_runs)} · 已核查 {checked}/{total}")
        self._rebuild_tree(preserve=True, select_first=True)
        self._populate_records(auto_select=True)
