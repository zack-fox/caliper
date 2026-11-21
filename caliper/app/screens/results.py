"""Workbench-style measurement record review and editing screen."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QStackedWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from app.controller import AppController, ControllerError
from app.widgets import Badge, EmptyState
from core.contracts.verdict import Verdict, from_text, to_text
from core.model.entities import Item, ItemResult

VERDICT_TONES = {
    Verdict.COMPLIANT: "ok", Verdict.PARTIAL: "warn", Verdict.NON_COMPLIANT: "bad",
    Verdict.NOT_APPLICABLE: "neutral", Verdict.UNCOLLECTED: "info",
}
VERDICT_COLORS = {
    "符合": ("#168447", "#e9f8ef"), "部分符合": ("#b87908", "#fff6df"),
    "不符合": ("#cf4545", "#fff0f0"), "不适用": ("#687587", "#f1f3f6"),
    "未采集": ("#3473c8", "#eef5ff"),
}


class ResultsScreen(QWidget):
    """Project and asset context beside a spreadsheet-like record table."""

    def __init__(self, controller: AppController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.current_result: ItemResult | None = None
        self._items: dict[int, Item] = {}
        self._visible_results: list[ItemResult] = []
        self.setObjectName("page")

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)

        heading = QHBoxLayout()
        title_box = QVBoxLayout()
        self.heading = QLabel("现场核查记录")
        self.heading.setObjectName("page_title")
        self.subheading = QLabel("按设备核对测评结果，编辑记录并留存人工确认")
        self.subheading.setObjectName("page_sub")
        title_box.addWidget(self.heading)
        title_box.addWidget(self.subheading)
        heading.addLayout(title_box)
        heading.addStretch(1)
        self.summary = QLabel("尚未生成记录")
        self.summary.setObjectName("muted")
        heading.addWidget(self.summary)
        root.addLayout(heading)

        domain_row = QHBoxLayout()
        domain_row.setSpacing(8)
        self.domain_tab = QPushButton("安全计算环境")
        self.domain_tab.setObjectName("domain_tab_active")
        self.domain_tab.setFixedHeight(38)
        self.domain_tab.setEnabled(False)
        domain_row.addWidget(self.domain_tab)
        domain_row.addStretch(1)
        self.domain_count = QLabel("0 项")
        self.domain_count.setObjectName("muted")
        domain_row.addWidget(self.domain_count)
        root.addLayout(domain_row)

        main = QSplitter(Qt.Horizontal)
        main.setChildrenCollapsible(False)
        main.setObjectName("workbench_splitter")

        self.project_panel = QFrame()
        self.project_panel.setObjectName("context_panel")
        self.project_panel.setMinimumWidth(205)
        self.project_panel.setMaximumWidth(275)
        project_layout = QVBoxLayout(self.project_panel)
        project_layout.setContentsMargins(14, 15, 14, 14)
        project_layout.setSpacing(9)
        project_title = QLabel("项目信息")
        project_title.setObjectName("section_title")
        project_layout.addWidget(project_title)
        self.project_fields: dict[str, QLabel] = {}
        for key, label in (("code", "项目编号"), ("name", "系统名称"), ("unit", "测评对象"), ("level", "安全等级"), ("date", "核查日期")):
            caption = QLabel(label)
            caption.setObjectName("muted")
            value = QLabel("—")
            value.setObjectName("project_value")
            value.setWordWrap(True)
            project_layout.addWidget(caption)
            project_layout.addWidget(value)
            self.project_fields[key] = value
        project_layout.addStretch(1)
        self.project_status = QLabel("等待导入现场材料")
        self.project_status.setObjectName("context_hint")
        self.project_status.setWordWrap(True)
        project_layout.addWidget(self.project_status)
        main.addWidget(self.project_panel)

        self.work_area = QWidget()
        work_layout = QVBoxLayout(self.work_area)
        work_layout.setContentsMargins(0, 0, 0, 0)
        work_layout.setSpacing(8)
        tools = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索控制点、控制项或设备")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._populate_table)
        self.filter = QComboBox()
        self.filter.addItems(["全部状态", "符合", "部分符合", "不符合", "不适用", "未采集"])
        self.filter.currentIndexChanged.connect(self._populate_table)
        self.asset_count = QLabel("设备 0")
        self.asset_count.setObjectName("muted")
        tools.addWidget(self.search, 1)
        tools.addWidget(self.filter)
        tools.addWidget(self.asset_count)
        work_layout.addLayout(tools)

        records = QSplitter(Qt.Horizontal)
        records.setChildrenCollapsible(False)
        records.setObjectName("records_splitter")

        tree_panel = QFrame()
        tree_panel.setObjectName("tree_panel")
        tree_layout = QVBoxLayout(tree_panel)
        tree_layout.setContentsMargins(10, 10, 8, 8)
        tree_layout.setSpacing(8)
        tree_title = QLabel("设备与资产")
        tree_title.setObjectName("section_title")
        tree_layout.addWidget(tree_title)
        self.asset_tree = QTreeWidget()
        self.asset_tree.setHeaderHidden(True)
        self.asset_tree.setIndentation(16)
        self.asset_tree.currentItemChanged.connect(self._on_asset_selected)
        tree_layout.addWidget(self.asset_tree, 1)
        records.addWidget(tree_panel)

        table_panel = QWidget()
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(7)
        table_toolbar = QHBoxLayout()
        table_label = QLabel("核查记录表")
        table_label.setObjectName("section_title")
        table_toolbar.addWidget(table_label)
        table_toolbar.addStretch(1)
        self.table_hint = QLabel("选择记录行查看依据并编辑")
        self.table_hint.setObjectName("muted")
        table_toolbar.addWidget(self.table_hint)
        table_layout.addLayout(table_toolbar)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["序号", "通用/扩展", "控制点", "控制项", "结果记录", "符合情况", "备注"])
        self.table.setObjectName("record_table")
        self.table.setAlternatingRowColors(False)
        self.table.setWordWrap(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setMinimumSectionSize(70)
        self.table.setColumnWidth(0, 58)
        self.table.setColumnWidth(1, 92)
        self.table.setColumnWidth(2, 130)
        self.table.setColumnWidth(3, 245)
        self.table.setColumnWidth(4, 360)
        self.table.setColumnWidth(5, 115)
        self.table.itemSelectionChanged.connect(self._on_table_selection)

        self.editor = QFrame()
        self.editor.setObjectName("record_editor")
        editor_layout = QVBoxLayout(self.editor)
        editor_layout.setContentsMargins(12, 10, 12, 10)
        editor_layout.setSpacing(8)
        editor_head = QHBoxLayout()
        self.selected_title = QLabel("选择一条记录")
        self.selected_title.setObjectName("section_title")
        self.record_badge = Badge("待核对", "neutral")
        editor_head.addWidget(self.selected_title, 1)
        editor_head.addWidget(self.record_badge)
        editor_layout.addLayout(editor_head)
        self.record_meta = QLabel("")
        self.record_meta.setObjectName("muted")
        editor_layout.addWidget(self.record_meta)
        fields = QGridLayout()
        fields.setHorizontalSpacing(10)
        fields.setVerticalSpacing(6)
        result_label = QLabel("结果记录")
        result_label.setObjectName("secondary")
        self.record_text = QPlainTextEdit()
        self.record_text.setPlaceholderText("记录现场核查过程、发现和支撑事实")
        self.record_text.setFixedHeight(86)
        verdict_label = QLabel("符合情况")
        verdict_label.setObjectName("secondary")
        self.verdict = QComboBox()
        self._verdict_values: list[str] = []
        for value in Verdict:
            text = to_text(value)
            self.verdict.addItem(text or "未采集（空）", text)
            self._verdict_values.append(text)
        note_label = QLabel("备注")
        note_label.setObjectName("secondary")
        self.note_text = QPlainTextEdit()
        self.note_text.setPlaceholderText("可选")
        self.note_text.setFixedHeight(52)
        reason_label = QLabel("修改理由")
        reason_label.setObjectName("secondary")
        self.reason = QLineEdit()
        self.reason.setPlaceholderText("人工修改或补录时说明理由")
        fields.addWidget(result_label, 0, 0)
        fields.addWidget(self.record_text, 1, 0, 1, 3)
        fields.addWidget(verdict_label, 0, 3)
        fields.addWidget(self.verdict, 1, 3)
        fields.addWidget(note_label, 2, 0)
        fields.addWidget(self.note_text, 3, 0, 1, 2)
        fields.addWidget(reason_label, 2, 2)
        fields.addWidget(self.reason, 3, 2, 1, 2)
        fields.setColumnStretch(0, 2)
        fields.setColumnStretch(1, 1)
        fields.setColumnStretch(2, 1)
        fields.setColumnStretch(3, 1)
        editor_layout.addLayout(fields)
        edit_actions = QHBoxLayout()
        self.evidence = QLabel("选择记录后显示判定依据、检查内容和判断标准。")
        self.evidence.setObjectName("evidence_summary")
        self.evidence.setWordWrap(True)
        edit_actions.addWidget(self.evidence, 1)
        self.reset_button = QPushButton("恢复建议")
        self.reset_button.setObjectName("subtle")
        self.reset_button.clicked.connect(self._reset_override)
        self.save_button = QPushButton("保存并确认")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self._save_record)
        edit_actions.addWidget(self.reset_button)
        edit_actions.addWidget(self.save_button)
        editor_layout.addLayout(edit_actions)
        self.table_page = QWidget()
        table_page_layout = QVBoxLayout(self.table_page)
        table_page_layout.setContentsMargins(0, 0, 0, 0)
        table_page_layout.setSpacing(7)
        table_page_layout.addWidget(self.table, 1)
        table_page_layout.addWidget(self.editor)
        self.empty = EmptyState("等待生成记录", "导入现场材料并生成记录草稿后，设备和核查记录会显示在这里。")
        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self.empty)
        self.content_stack.addWidget(self.table_page)
        table_layout.addWidget(self.content_stack, 1)
        records.addWidget(table_panel)
        records.setStretchFactor(0, 1)
        records.setStretchFactor(1, 4)
        records.setSizes([220, 1120])
        work_layout.addWidget(records, 1)
        main.addWidget(self.work_area)
        main.setStretchFactor(0, 0)
        main.setStretchFactor(1, 1)
        main.setSizes([235, 1290])
        root.addWidget(main, 1)
        self.refresh()

    def refresh(self) -> None:
        self._items = {}
        try:
            pack = self.controller.pack or self.controller.load_pack()
            self._items = {item.seq: item for item in pack.items_for_level(self.controller.project.level)}
        except Exception:
            pass
        project = self.controller.project
        self.project_fields["code"].setText(project.project_code or "未编号")
        self.project_fields["name"].setText(project.system_name or "未命名系统")
        self.project_fields["unit"].setText(next((a.test_object for a in project.assets if a.test_object), "—"))
        self.project_fields["level"].setText({2: "第二级", 3: "第三级"}.get(project.level, f"第{project.level}级"))
        self.project_fields["date"].setText(str(project.check_date))
        result = self.controller.run_result
        self.asset_tree.blockSignals(True)
        previous = self._current_asset_name()
        self.asset_tree.clear()
        if result:
            groups: dict[str, QTreeWidgetItem] = {}
            for index, run in enumerate(result.asset_runs):
                group_name = getattr(run.asset.asset_type, "value", str(run.asset.asset_type))
                group = groups.get(group_name)
                if group is None:
                    group = QTreeWidgetItem([group_name])
                    group.setFlags(group.flags() & ~Qt.ItemIsSelectable)
                    groups[group_name] = group
                    self.asset_tree.addTopLevelItem(group)
                reviewed = sum(1 for item in run.items if item.reviewed)
                child = QTreeWidgetItem([f"{run.asset.device_name}  ({reviewed}/{len(run.items)})"])
                child.setData(0, Qt.UserRole, index)
                child.setToolTip(0, f"{run.asset.device_name} · {run.asset.ip}")
                group.addChild(child)
                group.setExpanded(True)
            self.asset_count.setText(f"设备 {len(result.asset_runs)}")
            self.domain_count.setText(f"{sum(len(r.items) for r in result.asset_runs)} 项")
            self.project_status.setText("材料已解析 · 可逐项核对并编辑记录")
            for idx in range(self.asset_tree.topLevelItemCount()):
                group = self.asset_tree.topLevelItem(idx)
                for child_idx in range(group.childCount()):
                    child = group.child(child_idx)
                    if child.toolTip(0).startswith(previous) and previous:
                        self.asset_tree.setCurrentItem(child)
            if self.asset_tree.currentItem() is None:
                first_group = self.asset_tree.topLevelItem(0)
                if first_group and first_group.childCount():
                    self.asset_tree.setCurrentItem(first_group.child(0))
        else:
            self.asset_count.setText("设备 0")
            self.domain_count.setText("0 项")
            self.project_status.setText("等待导入现场材料")
        self.asset_tree.blockSignals(False)
        self._populate_table()

    def _current_asset_name(self) -> str:
        current = self.asset_tree.currentItem()
        if current and current.parent():
            return current.toolTip(0).split(" · ", 1)[0]
        return ""

    def _current_run(self):
        result = self.controller.run_result
        current = self.asset_tree.currentItem()
        if result is None or current is None or current.data(0, Qt.UserRole) is None:
            return None
        index = int(current.data(0, Qt.UserRole))
        return result.asset_runs[index] if 0 <= index < len(result.asset_runs) else None

    def _on_asset_selected(self, current, _previous=None) -> None:
        if current is not None and current.data(0, Qt.UserRole) is not None:
            self._populate_table()

    def _populate_table(self, *_args) -> None:
        selected_seq = self.current_result.seq if self.current_result else None
        run = self._current_run()
        self.table.setRowCount(0)
        self._visible_results = []
        if run is None:
            self.content_stack.setCurrentWidget(self.empty)
            return
        self.content_stack.setCurrentWidget(self.table_page)
        keyword = self.search.text().strip().lower()
        chosen = self.filter.currentText()
        for result in run.items:
            item = self._items.get(result.seq)
            control_item = item.control_item if item else result.control_point
            haystack = f"{result.seq} {result.control_point} {control_item} {result.item_id} {run.asset.device_name}".lower()
            if keyword and keyword not in haystack:
                continue
            if chosen != "全部状态" and chosen != result.verdict.value:
                continue
            self._visible_results.append(result)
        self.table.setRowCount(len(self._visible_results))
        for row, result in enumerate(self._visible_results):
            item = self._items.get(result.seq)
            control_text = item.control_item if item else result.control_point
            scope = "扩展" if item and item.optional_clause else "通用"
            values = [str(result.seq), scope, result.control_point, control_text, result.result_text, result.verdict.value, result.note]
            for col, text in enumerate(values):
                cell = QTableWidgetItem(text)
                cell.setData(Qt.UserRole, result.seq)
                cell.setToolTip(text)
                cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                if col == 5:
                    fg, bg = VERDICT_COLORS.get(result.verdict.value, ("#687587", "#f1f3f6"))
                    cell.setForeground(QColor(fg))
                    cell.setBackground(QColor(bg))
                    cell.setText(f"●  {text}" + (" · 已确认" if result.reviewed else " · 待核对"))
                    cell.setToolTip(f"{fg} · {text} · {'已确认' if result.reviewed else '待核对'}")
                self.table.setItem(row, col, cell)
            self.table.setRowHeight(row, 62 if len(result.result_text) < 100 else 86)
        self.summary.setText(f"{run.asset.device_name}　{len(run.items)} 项 · 显示 {len(self._visible_results)} 项")
        self.table_hint.setText("已确认项可继续编辑；保存后保留修改历史")
        if self._visible_results:
            target = next((i for i, value in enumerate(self._visible_results) if value.seq == selected_seq), 0)
            self.table.selectRow(target)
        else:
            self.current_result = None
            self.selected_title.setText("没有匹配记录")

    def _on_table_selection(self) -> None:
        selected = self.table.selectedItems()
        if not selected:
            return
        seq = selected[0].data(Qt.UserRole)
        result = next((entry for entry in self._visible_results if entry.seq == seq), None)
        if result is None:
            return
        self.current_result = result
        run = self._current_run()
        item = self._items.get(result.seq)
        self.selected_title.setText(f"{result.seq:02d}　{result.control_point} · {item.control_item if item else ''}")
        self.record_meta.setText(f"{result.item_id}　·　重要程度 {result.importance}　·　{run.asset.device_name if run else ''}　·　{run.os_family if run else ''}")
        self.verdict.setCurrentIndex(self._verdict_values.index(to_text(result.verdict)))
        self.record_text.setPlainText(result.result_text)
        self.note_text.setPlainText(result.note)
        self.reason.setText(result.override_reason)
        self.record_badge.set_text("已确认" if result.reviewed else result.verdict.value, "ok" if result.reviewed else VERDICT_TONES[result.verdict])
        self.reset_button.setEnabled(result.manual_override)
        self.evidence.setText(self._evidence_summary(result, item))

    @staticmethod
    def _evidence_summary(result: ItemResult, item: Item | None) -> str:
        details: list[str] = []
        for point in result.points[:2]:
            anchor = point.anchors[0] if point.anchors else None
            location = f"{anchor.file}:{anchor.line}" if anchor else "无原文锚点"
            details.append(f"实施点 {point.point}：{point.reason}（{location}）")
        if item:
            details.extend((f"检查内容：{item.check_content[:110]}", f"判断标准：{item.criteria[:110]}"))
        return "　|　".join(details) or "当前没有自动判定依据；请依据现场材料人工填写。"

    def _save_record(self) -> None:
        run, result = self._current_run(), self.current_result
        if run is None or result is None:
            return
        verdict_text = str(self.verdict.currentData())
        result_text = self.record_text.toPlainText().strip()
        note = self.note_text.toPlainText().strip()
        selected_verdict = from_text(verdict_text)
        if not result.manual_override and result_text == (result.auto_result_text or "") and note == (result.auto_note or "") and selected_verdict == (result.auto_verdict or Verdict.UNCOLLECTED):
            try:
                result.reviewed_at = self.controller.confirm_record(result.item_id, run.asset.device_name)
            except ControllerError as exc:
                QMessageBox.warning(self, "未能确认", str(exc))
                return
            result.reviewed = True
        else:
            try:
                reviewed_at = self.controller.save_record_override(result.item_id, run.asset.device_name, result_text, selected_verdict.value, note, self.reason.text().strip())
            except (ControllerError, ValueError) as exc:
                QMessageBox.warning(self, "未能保存", str(exc))
                return
            result.result_text, result.verdict, result.note = result_text, selected_verdict, note
            result.manual_override = True
            result.override_reason = self.reason.text().strip()
            result.reviewed_at = reviewed_at
            result.reviewed = True
        self._update_asset_tree_count(run)
        self._populate_table()

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
        self._update_asset_tree_count(run)
        self._populate_table()

    def _update_asset_tree_count(self, run) -> None:
        current = self.asset_tree.currentItem()
        if current is None:
            return
        reviewed = sum(1 for item in run.items if item.reviewed)
        current.setText(0, f"{run.asset.device_name}  ({reviewed}/{len(run.items)})")
