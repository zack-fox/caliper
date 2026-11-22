"""现场核查工作区：领域页签 + 资产树 + 记录表 + 可折叠检查器。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QListWidget, QMessageBox, QPlainTextEdit, QPushButton, QStackedWidget,
    QTabBar, QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from adapters.llm import build_payload
from app.controller import AppController, ControllerError
from app.screens.dialogs import PolishPreviewDialog, RecordPreviewDialog, TextDetailsDialog
from app.theme.tokens import TABLE_HEADER_HEIGHT, TABLE_ROW_HEIGHT
from app.widgets import (
    Badge, ComplianceBadge, DomainTabs, EmptyState, FilterChip, InspectorDrawer,
)
from core.contracts.verdict import Verdict
from core.model.entities import Item, ItemResult
from core.remediation import Advice
from core.traceability import standard_references

VERDICT_TONES = {
    Verdict.COMPLIANT: "ok", Verdict.PARTIAL: "warn", Verdict.NON_COMPLIANT: "bad",
    Verdict.NOT_APPLICABLE: "neutral", Verdict.UNCOLLECTED: "info",
}

RESULT_COLUMNS = (
    "序号", "通用/扩展", "控制点", "控制项", "结果记录", "符合情况", "备注", "附件",
)
RESULT_COLUMN_WIDTHS = (52, 88, 148, 240, 320, 100, 170, 76)

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
INSPECTOR_VIEWS = ("detail", "remediation", "evidence")
ATTACHMENT_COLUMN = 7


class ResultsScreen(QWidget):
    """三栏现场核查工作台，逐项编辑并确认记录。"""

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
        self.subheading = QLabel("按设备核对测评结果，编辑记录并留存人工确认")
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

        self.diagnostic_banner = QFrame()
        self.diagnostic_banner.setObjectName("context_panel")
        diagnostic_layout = QHBoxLayout(self.diagnostic_banner)
        diagnostic_layout.setContentsMargins(12, 7, 10, 7)
        diagnostic_layout.setSpacing(10)
        diagnostic_title = QLabel("判定范围提示")
        diagnostic_title.setObjectName("secondary")
        self.diagnostic_summary = QLabel("")
        self.diagnostic_summary.setObjectName("muted")
        self.diagnostic_summary.setWordWrap(True)
        self.diagnostic_details = QPushButton("查看明细")
        self.diagnostic_details.setObjectName("subtle")
        self.diagnostic_details.clicked.connect(self._show_diagnostics)
        diagnostic_layout.addWidget(diagnostic_title)
        diagnostic_layout.addWidget(self.diagnostic_summary, 1)
        diagnostic_layout.addWidget(self.diagnostic_details)
        self.diagnostic_banner.hide()
        column.addWidget(self.diagnostic_banner)

        self.domain_tabs = DomainTabs()
        self.domain_tabs.setFixedHeight(40)
        self.domain_tabs.set_domains([(key, label, 0, 0) for key, label in DOMAINS])
        self.domain_tabs.domain_changed.connect(self._on_domain_changed)
        column.addWidget(self.domain_tabs)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(10)
        body.addWidget(self._build_tree_panel())
        body.addWidget(self._build_center(), 1)
        self.inspector = self._build_inspector()
        body.addWidget(self.inspector)
        column.addLayout(body, 1)
        return host

    def _build_tree_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("tree_panel")
        panel.setFixedWidth(232)
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
        layout.addWidget(self.asset_stack, 1)
        return panel

    def _build_center(self) -> QWidget:
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self._build_toolbar())

        self.table_stack = QStackedWidget()
        self.table_page = QWidget()
        table_layout = QVBoxLayout(self.table_page)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(0)
        self.table = QTableWidget(0, len(RESULT_COLUMNS))
        self.table.setObjectName("records_table")
        self.table.setHorizontalHeaderLabels(list(RESULT_COLUMNS))
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setHorizontalScrollMode(QTableWidget.ScrollPerPixel)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(TABLE_ROW_HEIGHT)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.table.horizontalHeader().setFixedHeight(TABLE_HEADER_HEIGHT)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.horizontalHeader().setMinimumSectionSize(50)
        self.table.horizontalHeader().setStretchLastSection(False)
        for column, width in enumerate(RESULT_COLUMN_WIDTHS):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.Interactive)
            self.table.setColumnWidth(column, width)
        table_font = self.table.font()
        table_font.setPixelSize(12)
        self.table.setFont(table_font)
        self.table.itemSelectionChanged.connect(self._on_table_selection)
        self.table.cellClicked.connect(self._on_cell_clicked)
        table_layout.addWidget(self.table, 1)
        self.table_stack.addWidget(self.table_page)

        self.filtered_empty = EmptyState("当前筛选无结果", "调整搜索关键词或恢复「全部」符合情况筛选。")
        empty_page = QWidget()
        empty_layout = QVBoxLayout(empty_page)
        empty_layout.setContentsMargins(0, 0, 0, 0)
        empty_layout.setSpacing(8)
        empty_layout.addWidget(self.filtered_empty, 1)
        action_row = QHBoxLayout()
        action_row.addStretch(1)
        self.restore_filter_button = QPushButton("恢复全部筛选")
        self.restore_filter_button.setObjectName("subtle")
        self.restore_filter_button.clicked.connect(self.restore_all_filters)
        action_row.addWidget(self.restore_filter_button)
        action_row.addStretch(1)
        empty_layout.addLayout(action_row)
        self.table_stack.addWidget(empty_page)
        layout.addWidget(self.table_stack, 1)
        return host

    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("workspace_toolbar")
        column = QVBoxLayout(bar)
        column.setContentsMargins(10, 7, 10, 7)
        column.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)
        self.search = QLineEdit()
        self.search.setObjectName("toolbar_search")
        self.search.setPlaceholderText("搜索控制点、控制项、结果记录或备注")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._populate_table)
        top.addWidget(self.search, 1)
        self.row_count = QLabel("0 / 0 行")
        self.row_count.setObjectName("muted")
        top.addWidget(self.row_count)

        self.record_preview_button = QPushButton("记录表预览")
        self.record_preview_button.setObjectName("subtle")
        self.record_preview_button.clicked.connect(self._preview_record)
        self.generate_record_button = QPushButton("生成记录表")
        self.generate_record_button.setObjectName("subtle")
        self.generate_record_button.clicked.connect(self._generate_record)
        self.refresh_button = QPushButton("刷新")
        self.refresh_button.setObjectName("subtle")
        self.refresh_button.clicked.connect(self.refresh)
        self.inspector_toggle = QPushButton("检查器")
        self.inspector_toggle.setObjectName("subtle")
        self.inspector_toggle.setCheckable(True)
        self.inspector_toggle.setChecked(True)
        self.inspector_toggle.toggled.connect(self._set_inspector_visible)
        top.addWidget(self.record_preview_button)
        top.addWidget(self.generate_record_button)
        top.addWidget(self.refresh_button)
        top.addWidget(self.inspector_toggle)
        column.addLayout(top)

        chip_row = QHBoxLayout()
        chip_row.setSpacing(6)
        self.filter_chips: dict[str, FilterChip] = {}
        for key, label in FILTERS:
            chip = FilterChip(label, key)
            if key == self._filter_key:
                chip.setChecked(True)
            chip.clicked.connect(lambda _checked=False, name=key: self._apply_filter(name))
            self.filter_chips[key] = chip
            chip_row.addWidget(chip)
        chip_row.addStretch(1)
        column.addLayout(chip_row)
        return bar

    def _build_inspector(self) -> InspectorDrawer:
        drawer = InspectorDrawer("详情")
        self.inspector_tabs = QTabBar()
        self.inspector_tabs.setObjectName("domain_tabs")
        self.inspector_tabs.setDrawBase(False)
        self.inspector_tabs.setExpanding(False)
        for key, label in zip(INSPECTOR_VIEWS, ("详情", "整改", "证据")):
            self.inspector_tabs.addTab(label)
        self.inspector_tabs.currentChanged.connect(self._on_inspector_tab)
        drawer.layout().insertWidget(1, self.inspector_tabs)
        drawer.closed.connect(self._on_inspector_closed)

        drawer.add_view("detail", "详情", self._build_detail_view())
        drawer.add_view("remediation", "整改", self._build_remediation_view())
        drawer.add_view("evidence", "证据", self._build_evidence_view())
        return drawer

    def _build_detail_view(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        self.detail_placeholder = QLabel("选择一条记录查看详情")
        self.detail_placeholder.setObjectName("secondary")
        self.detail_placeholder.setWordWrap(True)
        layout.addWidget(self.detail_placeholder)

        self.detail_form = QWidget()
        form = QVBoxLayout(self.detail_form)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(8)

        head = QHBoxLayout()
        self.selected_title = QLabel("—")
        self.selected_title.setObjectName("section_title")
        self.selected_title.setWordWrap(True)
        self.record_badge = Badge("待核对", "neutral")
        head.addWidget(self.selected_title, 1)
        head.addWidget(self.record_badge)
        form.addLayout(head)
        self.record_meta = QLabel("")
        self.record_meta.setObjectName("muted")
        self.record_meta.setWordWrap(True)
        form.addWidget(self.record_meta)

        fields = QGridLayout()
        fields.setHorizontalSpacing(8)
        fields.setVerticalSpacing(5)
        fields.setColumnStretch(1, 1)
        record_label = QLabel("结果记录")
        record_label.setObjectName("secondary")
        self.record_text = QPlainTextEdit()
        self.record_text.setPlaceholderText("记录现场核查过程、发现和支撑事实")
        self.record_text.setFixedHeight(112)
        verdict_label = QLabel("符合情况")
        verdict_label.setObjectName("secondary")
        self.verdict = QComboBox()
        for value in Verdict:
            self.verdict.addItem(value.value, value.value)
        note_label = QLabel("备注")
        note_label.setObjectName("secondary")
        self.note_text = QPlainTextEdit()
        self.note_text.setPlaceholderText("可选")
        self.note_text.setFixedHeight(58)
        reason_label = QLabel("修改理由")
        reason_label.setObjectName("secondary")
        self.reason = QLineEdit()
        self.reason.setPlaceholderText("人工修改或补录时说明理由")
        fields.addWidget(record_label, 0, 0)
        fields.addWidget(self.record_text, 1, 0, 1, 2)
        fields.addWidget(verdict_label, 0, 2)
        fields.addWidget(self.verdict, 1, 2)
        fields.addWidget(note_label, 2, 0)
        fields.addWidget(self.note_text, 3, 0, 1, 2)
        fields.addWidget(reason_label, 2, 2)
        fields.addWidget(self.reason, 3, 2)
        form.addLayout(fields)

        self.detail_basis = QLabel("")
        self.detail_basis.setObjectName("evidence_summary")
        self.detail_basis.setWordWrap(True)
        form.addWidget(self.detail_basis)

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
        form.addLayout(actions)
        form.addStretch(1)

        self.detail_form.hide()
        layout.addWidget(self.detail_form, 1)
        return page

    def _build_remediation_view(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        title = QLabel("整改建议")
        title.setObjectName("section_title")
        layout.addWidget(title)
        self.remediation_body = QLabel("选择一条记录查看详情")
        self.remediation_body.setObjectName("secondary")
        self.remediation_body.setWordWrap(True)
        self.remediation_body.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        layout.addWidget(self.remediation_body, 1)
        return page

    def _build_evidence_view(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        record_title = QLabel("结果记录")
        record_title.setObjectName("secondary")
        layout.addWidget(record_title)
        self.evidence_text = QPlainTextEdit()
        self.evidence_text.setReadOnly(True)
        self.evidence_text.setFixedHeight(96)
        layout.addWidget(self.evidence_text)

        anchor_title = QLabel("证据锚点")
        anchor_title.setObjectName("secondary")
        layout.addWidget(anchor_title)
        self.anchor_tree = QTreeWidget()
        self.anchor_tree.setColumnCount(3)
        self.anchor_tree.setHeaderLabels(["文件", "行号", "片段"])
        self.anchor_tree.setRootIsDecorated(False)
        self.anchor_tree.setFixedHeight(170)
        self.anchor_tree.setColumnWidth(0, 120)
        self.anchor_tree.setColumnWidth(1, 44)
        self.anchor_tree.hide()
        layout.addWidget(self.anchor_tree)
        self.anchor_empty = QLabel("选择一条记录查看详情")
        self.anchor_empty.setObjectName("muted")
        self.anchor_empty.setWordWrap(True)
        layout.addWidget(self.anchor_empty)

        self.attachment_label = QLabel("附件文件（0）")
        self.attachment_label.setObjectName("secondary")
        layout.addWidget(self.attachment_label)
        self.attachment_list = QListWidget()
        self.attachment_list.setFixedHeight(110)
        layout.addWidget(self.attachment_list)
        layout.addStretch(1)
        return page

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
            self.table.setRowCount(0)
            self._visible_results = []
            self.row_count.setText("0 / 0 行")
            self.summary.setText("尚未生成记录草稿")
            self._clear_inspector()
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
        self._populate_table(auto_select=True)

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
            runs = [
                run
                for run in runs
                if keyword in self._asset_haystack(run)
            ]
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
        self._populate_table(auto_select=True)

    def _selected_device(self) -> str:
        current = self.asset_tree.currentItem()
        if current is not None and current.parent() is not None:
            return current.toolTip(0)
        return ""

    def _on_asset_selected(self, current, _previous=None) -> None:
        if self._tree_signals_blocked:
            return
        if current is not None and current.data(0, Qt.UserRole) is not None:
            self._populate_table(auto_select=True)

    def _on_domain_changed(self, key: str) -> None:
        if not key:
            return
        self._domain_key = key
        self.current_result = None
        self.current_advice = None
        self._clear_inspector()
        self._rebuild_tree(preserve=False, select_first=True)
        self._populate_table(auto_select=False)

    # ------------------------------------------------------------------ 表格
    def _populate_table(self, *_args, auto_select: bool = True) -> None:
        selected_seq = self.current_result.seq if self.current_result else None
        run = self._current_run()
        self.table.setRowCount(0)
        self.table_stack.setCurrentWidget(self.table_page)
        self._visible_results = []

        if run is None:
            self.row_count.setText("0 / 0 行")
            self._show_table_empty()
            self._clear_inspector()
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
        self.row_count.setText(f"{len(self._visible_results)} / {total} 行")
        self.table.setRowCount(len(self._visible_results))
        for row, result in enumerate(self._visible_results):
            self._fill_table_row(row, result)
            self.table.setRowHeight(row, TABLE_ROW_HEIGHT)

        if self._visible_results:
            self.table_stack.setCurrentWidget(self.table_page)
            if auto_select:
                target = next(
                    (
                        index
                        for index, value in enumerate(self._visible_results)
                        if value.seq == selected_seq
                    ),
                    0,
                )
                self.table.selectRow(target)
            else:
                self.table.clearSelection()
                self._clear_inspector()
        else:
            self._show_table_empty()
            self._clear_inspector()

    def _fill_table_row(self, row: int, result: ItemResult) -> None:
        item = self._items.get(result.seq)
        control_item = item.control_item if item else result.control_point
        if item is not None and ("扩展" in control_item or "扩展" in item.check_content):
            scope = "扩展"
        else:
            scope = "通用"
        files = self._attachment_files(result)
        values = (
            str(result.seq),
            scope,
            result.control_point,
            control_item,
            result.result_text,
            result.verdict.value,
            result.note,
            f"{len(files)} 个" if files else "—",
        )
        for column, text in enumerate(values):
            cell = QTableWidgetItem(text)
            cell.setData(Qt.UserRole, result.seq)
            cell.setToolTip(text)
            cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
            if column == ATTACHMENT_COLUMN and files:
                cell.setToolTip("\n".join(sorted(files)))
            self.table.setItem(row, column, cell)

        badge_host = QWidget()
        badge_host.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        badge_layout = QHBoxLayout(badge_host)
        badge_layout.setContentsMargins(8, 0, 8, 0)
        badge_layout.setSpacing(0)
        badge = ComplianceBadge(result.verdict.value)
        badge.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        badge.setToolTip(
            f"{result.verdict.value} · {'已确认' if result.reviewed else '待核对'}"
        )
        badge_layout.addWidget(badge)
        badge_layout.addStretch(1)
        self.table.setCellWidget(row, 5, badge_host)

    def _show_table_empty(self) -> None:
        if self._filter_key != "all" or self.search.text().strip():
            self.filtered_empty.set_text(
                "当前筛选无结果", "调整搜索关键词或恢复「全部」符合情况筛选。"
            )
            self.restore_filter_button.show()
        elif not self._domain_runs:
            self.filtered_empty.set_text(
                "当前领域暂无记录", "切换领域页签，或前往「材料与资产」导入材料。"
            )
            self.restore_filter_button.hide()
        else:
            self.filtered_empty.set_text("当前资产暂无记录", "该资产没有可展示的核查记录。")
            self.restore_filter_button.hide()
        self.table_stack.setCurrentWidget(self.table_stack.widget(1))

    def _apply_filter(self, key: str) -> None:
        self._filter_key = key
        for name, chip in self.filter_chips.items():
            chip.blockSignals(True)
            chip.setChecked(name == key)
            chip.blockSignals(False)
        self._populate_table(auto_select=True)

    def restore_all_filters(self) -> None:
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self._apply_filter("all")

    def _on_cell_clicked(self, row: int, column: int) -> None:
        if column == ATTACHMENT_COLUMN and 0 <= row < len(self._visible_results):
            self._set_inspector_view("evidence", reveal=True)

    @staticmethod
    def _attachment_files(result: ItemResult) -> set[str]:
        return {
            anchor.file
            for point in result.points
            for anchor in point.anchors
            if anchor.file
        }

    # ------------------------------------------------------------------ 检查器
    def _on_table_selection(self) -> None:
        selected = self.table.selectedItems()
        if not selected:
            return
        seq = selected[0].data(Qt.UserRole)
        result = next(
            (entry for entry in self._visible_results if entry.seq == seq), None
        )
        if result is None:
            return
        self.current_result = result
        self._set_inspector_view("detail")
        run = self._current_run()
        item = self._items.get(result.seq)
        self.detail_placeholder.hide()
        self.detail_form.show()
        self.selected_title.setText(
            f"{result.seq:02d}　{result.control_point}"
        )
        self.record_meta.setText(
            f"{result.item_id}　·　重要程度 {result.importance}"
            f"　·　{run.asset.device_name if run else ''}"
            f"　·　{run.os_family if run else ''}"
        )
        index = list(Verdict).index(result.verdict)
        self.verdict.setCurrentIndex(index)
        self.record_text.setPlainText(result.result_text)
        self.note_text.setPlainText(result.note)
        self.reason.setText(result.override_reason)
        self.record_badge.set_text(
            "已确认" if result.reviewed else "待核对",
            "ok" if result.reviewed else VERDICT_TONES.get(result.verdict, "neutral"),
        )
        self.reset_button.setEnabled(result.manual_override)
        self.detail_basis.setText(self._evidence_summary(result, item))
        self._load_advice(run, result)
        self._load_evidence(result)

    def _clear_inspector(self) -> None:
        self.current_result = None
        self.current_advice = None
        self.detail_placeholder.show()
        self.detail_form.hide()
        self.record_badge.set_text("待核对", "neutral")
        self.selected_title.setText("—")
        self.record_meta.setText("")
        self.record_text.clear()
        self.note_text.clear()
        self.reason.clear()
        self.detail_basis.setText("")
        self.reset_button.setEnabled(False)
        self.polish_button.setEnabled(False)
        self.remediation_body.setText("选择一条记录查看详情")
        self.evidence_text.clear()
        self.anchor_tree.clear()
        self.anchor_tree.hide()
        self.anchor_empty.setText("选择一条记录查看详情")
        self.anchor_empty.show()
        self.attachment_label.setText("附件文件（0）")
        self.attachment_list.clear()
        self._set_inspector_view("detail")

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

    def _load_evidence(self, result: ItemResult) -> None:
        self.evidence_text.setPlainText(result.result_text or "—")
        anchors = [
            (anchor.file, anchor.line, anchor.snippet)
            for point in result.points
            for anchor in point.anchors
            if anchor.file
        ]
        self.anchor_tree.clear()
        for file, line, snippet in anchors:
            node = QTreeWidgetItem([file, str(line), snippet])
            node.setToolTip(2, snippet)
            self.anchor_tree.addTopLevelItem(node)
        if anchors:
            self.anchor_tree.show()
            self.anchor_empty.hide()
        else:
            self.anchor_tree.hide()
            self.anchor_empty.setText("暂无证据锚点")
            self.anchor_empty.show()
        files = sorted(self._attachment_files(result))
        self.attachment_label.setText(f"附件文件（{len(files)}）")
        self.attachment_list.clear()
        self.attachment_list.addItems(files)

    def _on_inspector_tab(self, index: int) -> None:
        if 0 <= index < len(INSPECTOR_VIEWS):
            self.inspector.set_view(INSPECTOR_VIEWS[index])

    def _set_inspector_view(self, key: str, reveal: bool = False) -> None:
        if key not in INSPECTOR_VIEWS:
            return
        index = INSPECTOR_VIEWS.index(key)
        self.inspector_tabs.blockSignals(True)
        self.inspector_tabs.setCurrentIndex(index)
        self.inspector_tabs.blockSignals(False)
        self.inspector.set_view(key)
        if reveal and self.inspector.isHidden():
            self._set_inspector_visible(True)

    def _on_inspector_closed(self) -> None:
        self._set_inspector_visible(False)

    def _set_inspector_visible(self, visible: bool) -> None:
        if self.inspector_toggle.isChecked() != visible:
            self.inspector_toggle.blockSignals(True)
            self.inspector_toggle.setChecked(visible)
            self.inspector_toggle.blockSignals(False)
        self.inspector.setVisible(visible)

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

    @staticmethod
    def _evidence_summary(result: ItemResult, item: Item | None) -> str:
        details: list[str] = []
        if item:
            details.append("标准依据：" + "；".join(standard_references(item)))
        for point in result.points[:2]:
            anchor = point.anchors[0] if point.anchors else None
            location = f"{anchor.file}:{anchor.line}" if anchor else "无原文锚点"
            rules = "、".join(point.rule_refs) if point.rule_refs else "无规则编号"
            details.append(
                f"实施点 {point.point}：{point.reason}（{location}；规则 {rules}）"
            )
        if item:
            details.extend(
                (f"检查内容：{item.check_content[:110]}", f"判断标准：{item.criteria[:110]}")
            )
        return "　|　".join(details) or "当前没有自动判定依据；请依据现场材料人工填写。"

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
        self._populate_table(auto_select=True)
