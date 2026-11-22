"""② 材料与资产：项目信息、材料拖入解析、设备资产清单与核查入口。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.controller import AppController, ControllerError
from app.screens.dialogs import AssetDialog, EvidenceReviewDialog
from app.widgets import Badge, Card, DropZone, EmptyState, PageHeader, Toolbar, scrollable
from core.contracts.columns import ASSET_COLUMNS as ASSET_CORE_COLUMNS
from core.contracts.enums import AssetType
from core.model.entities import Asset

# 界面资产表：序号 + 18 列资产记录（冻结顺序）+ 证据识别 + 操作。列契约不得改动。
ASSET_COLUMNS = ("序号",) + ASSET_CORE_COLUMNS + ("证据识别", "操作")

EVIDENCE_COLUMN = len(ASSET_COLUMNS) - 2
ACTION_COLUMN = len(ASSET_COLUMNS) - 1

# 18 列资产记录在 Asset 模型上的字段映射（相对 18 列的索引，0 为设备名称）。
ASSET_FIELD_ORDER = (
    "device_name",
    "is_virtual",
    "business_system",
    "os_version",
    "db_version",
    "middleware_version",
    "ip",
    "count",
    "hot_standby",
    "zone",
    "importance",
    "guide",
    "test_object",
    "note",
    "scan_object_type",
    "row_color",
    "scan_address",
    "is_test_env",
)

# 左列宽度：在 1280 窗口下仍给右侧表格留出可读空间。
LEFT_MIN_WIDTH = 360
LEFT_MAX_WIDTH = 420
LEFT_START_WIDTH = 400

PENDING_LIMIT = 5


class EvidenceScreen(QWidget):
    """材料与资产页：左侧项目与拖拽，右侧设备清单，顶部材料就绪度。"""

    project_loaded = Signal()
    assets_changed = Signal()
    run_requested = Signal()

    def __init__(self, controller: AppController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setObjectName("page")
        self._asset_rows: list[tuple[Asset, str, str, str, str, str]] = []
        self._visible_assets: list[Asset] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        self.header = PageHeader(
            "材料与资产",
            "导入现场采集材料，确认设备与证据识别状态。",
        )
        refresh_button = QPushButton("刷新")
        refresh_button.setObjectName("subtle")
        refresh_button.clicked.connect(self.refresh)
        self.header.add_action(refresh_button)
        self.remove_remediation_button = QPushButton("删除整改材料")
        self.remove_remediation_button.setObjectName("subtle")
        self.remove_remediation_button.clicked.connect(self._remove_remediation)
        self.header.add_action(self.remove_remediation_button)
        layout.addWidget(self.header)

        # ---- 双栏主体 ----
        self.body = QSplitter(Qt.Horizontal)
        self.body.setObjectName("workbench_splitter")
        self.body.setChildrenCollapsible(False)
        self.body.setHandleWidth(1)

        self.left_panel = scrollable(self._build_left_column())
        self.left_panel.setMinimumWidth(LEFT_MIN_WIDTH)
        self.left_panel.setMaximumWidth(LEFT_MAX_WIDTH)
        self.left_panel.setWidgetResizable(True)
        self.left_panel.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.body.addWidget(self.left_panel)

        self.right_panel = self._build_right_column()
        self.right_panel.setMinimumWidth(0)
        self.body.addWidget(self.right_panel)

        self.body.setStretchFactor(0, 0)
        self.body.setStretchFactor(1, 1)
        self.body.setSizes([LEFT_START_WIDTH, 900])
        layout.addWidget(self.body, 1)

        self.refresh()

    # ---- 左列 ----
    def _build_left_column(self) -> QWidget:
        host = QWidget()
        host.setObjectName("page")
        column = QVBoxLayout(host)
        column.setContentsMargins(0, 0, 4, 0)
        column.setSpacing(12)

        project_card = Card("项目信息", "决定规则包与指导书")
        grid = QGridLayout()
        grid.setContentsMargins(0, 2, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)

        self.project_code = QLineEdit()
        self.project_code.setPlaceholderText("可留空")
        self.system_name = QLineEdit()
        self.system_name.setPlaceholderText("例如：示例系统A")
        self.level = QComboBox()
        self.level.addItems(["三级", "二级"])
        self.check_date = QDateEdit(QDate.currentDate())
        self.check_date.setCalendarPopup(True)
        self.evidence_root = self._path_label()
        self.evidence_root_button = QPushButton("选择…")
        self.evidence_root_button.setObjectName("subtle")
        self.evidence_root_button.clicked.connect(self._pick_evidence_root)

        evidence_row = QWidget()
        evidence_layout = QHBoxLayout(evidence_row)
        evidence_layout.setContentsMargins(0, 0, 0, 0)
        evidence_layout.setSpacing(6)
        evidence_layout.addWidget(self.evidence_root, 1)
        evidence_layout.addWidget(self.evidence_root_button, 0)

        rows = (
            ("项目编号", self.project_code),
            ("系统名称", self.system_name),
            ("等保等级", self.level),
            ("检查日期", self.check_date),
            ("证据根目录", evidence_row),
        )
        for row, (caption, widget) in enumerate(rows):
            grid.addWidget(self._caption(caption), row, 0)
            grid.addWidget(widget, row, 1)
        project_card.add(self._grid_host(grid))

        project_actions = QHBoxLayout()
        project_actions.setSpacing(8)
        self.save_button = QPushButton("保存项目")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self.save_project)
        self.load_button = QPushButton("加载项目")
        self.load_button.setObjectName("subtle")
        self.load_button.clicked.connect(self.load_project)
        project_actions.addWidget(self.save_button)
        project_actions.addWidget(self.load_button)
        project_actions.addStretch(1)
        project_card.body.addLayout(project_actions)
        column.addWidget(project_card)

        import_card = Card("证据提交", "先选定资产类型，再拖入 / 上传 / 粘贴证据内容")
        type_row = QHBoxLayout()
        type_row.setSpacing(8)
        type_caption = self._caption("资产类型")
        self.asset_type_selector = QComboBox()
        self.asset_type_selector.addItems([item.value for item in AssetType])
        self.asset_type_selector.setToolTip(
            "上传前必须先选定资产类型；系统据此套用对应测评项清单，"
            "上传材料只做证据识别，不自动改判类型。"
        )
        type_row.addWidget(type_caption)
        type_row.addWidget(self.asset_type_selector, 1)
        import_card.body.addLayout(type_row)

        self.dropzone = DropZone()
        self.dropzone.title.setText("把测评证据拖到这里")
        self.dropzone.title.setWordWrap(True)
        self.dropzone.hint.setText(
            "支持拖拽目录/日志/资产表；也可点击下方按钮上传文件、上传整改文件或粘贴文字"
        )
        self.dropzone.hint.setWordWrap(True)
        self.dropzone.hint.setMinimumWidth(0)
        pick_dir = QPushButton("选择采集目录…")
        pick_dir.clicked.connect(lambda: self._add_asset(pick_directory=True))
        pick_file = QPushButton("上传文件…")
        pick_file.clicked.connect(lambda: self._add_asset(pick_log=True))
        paste_text = QPushButton("粘贴文字…")
        paste_text.clicked.connect(self._paste_text)
        remediation = QPushButton("上传整改文件…")
        remediation.clicked.connect(self._upload_remediation)
        for button in (pick_dir, pick_file, paste_text, remediation):
            self.dropzone.add_action(button)
        self.dropzone.path_dropped.connect(self._on_dropped)
        import_card.add(self.dropzone)
        column.addWidget(import_card)

        readiness_card = Card("材料就绪度", f"需处理项最多显示 {PENDING_LIMIT} 条")
        readiness_row = QHBoxLayout()
        readiness_row.setSpacing(8)
        self.readiness_badge = Badge("待导入", "neutral")
        self.readiness_summary = QLabel("")
        self.readiness_summary.setObjectName("secondary")
        self.readiness_summary.setWordWrap(True)
        readiness_row.addWidget(self.readiness_badge)
        readiness_row.addWidget(self.readiness_summary, 1)
        readiness_card.body.addLayout(readiness_row)
        self.readiness_pending = QLabel("")
        self.readiness_pending.setObjectName("muted")
        self.readiness_pending.setWordWrap(True)
        readiness_card.body.addWidget(self.readiness_pending)
        column.addWidget(readiness_card)

        column.addStretch(1)
        return host

    # ---- 右列 ----
    def _build_right_column(self) -> QWidget:
        asset_card = Card("设备与材料表", "证据识别列显示可核查块数或不可用原因")

        self.toolbar = Toolbar()
        self.search = self.toolbar.add_search("搜索设备名称或 IP…")
        self.search.textChanged.connect(self._apply_filter)

        self.add_button = QPushButton("新增设备")
        self.add_button.setObjectName("subtle")
        self.add_button.clicked.connect(lambda: self._add_asset())
        self.import_button = QPushButton("导入材料")
        self.import_button.setObjectName("subtle")
        self.import_button.clicked.connect(lambda: self._add_asset(pick_directory=True))
        self.run_button = QPushButton("生成记录草稿")
        self.run_button.setObjectName("primary")
        self.run_button.clicked.connect(self.run_requested.emit)
        for button in (self.add_button, self.import_button, self.run_button):
            self.toolbar.add_right(button)
        asset_card.add(self.toolbar)

        self.table_hint = QLabel("")
        self.table_hint.setObjectName("muted")
        self.table_hint.setWordWrap(True)
        asset_card.add(self.table_hint)

        self.table = QTableWidget(0, len(ASSET_COLUMNS))
        self.table.setObjectName("records_table")
        self.table.setHorizontalHeaderLabels(ASSET_COLUMNS)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setMinimumWidth(0)
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setMinimumSectionSize(48)
        widths = (
            48, 140, 72, 160, 140, 130, 110, 120, 64, 72, 90, 72, 150, 90,
            110, 90, 70, 120, 90, 150, 200,
        )
        for column, width in enumerate(widths):
            header.setSectionResizeMode(column, QHeaderView.Interactive)
            self.table.setColumnWidth(column, width)
        self.table.setHorizontalScrollMode(QTableWidget.ScrollPerPixel)
        self.table.cellDoubleClicked.connect(self._on_row_double_clicked)

        self.empty_state = EmptyState(
            "尚未添加设备",
            "拖入采集目录或单个日志文件，或点击「新增设备」开始。",
        )
        self.table_stack = QStackedWidget()
        self.table_stack.addWidget(self.table)
        self.table_stack.addWidget(self.empty_state)
        asset_card.add(self.table_stack, 1)
        return asset_card

    # ---- 小工具 ----
    @staticmethod
    def _caption(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("secondary")
        return label

    @staticmethod
    def _path_label() -> QLabel:
        label = QLabel("—")
        label.setObjectName("mono")
        label.setWordWrap(True)
        label.setMinimumWidth(0)
        return label

    @staticmethod
    def _grid_host(grid: QGridLayout) -> QWidget:
        host = QWidget()
        host.setLayout(grid)
        return host

    @staticmethod
    def _status_cell(text: str, tone: str, tooltip: str = "") -> QWidget:
        host = QWidget()
        host.setToolTip(tooltip)
        row = QHBoxLayout(host)
        row.setContentsMargins(8, 0, 8, 0)
        row.setSpacing(0)
        badge = Badge(text, tone)
        badge.setToolTip(tooltip)
        row.addWidget(badge)
        row.addStretch(1)
        return host

    def _action_cell(self, asset: Asset) -> QWidget:
        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(4, 0, 4, 0)
        row.setSpacing(2)
        for text, handler in (
            ("查看材料", self._review_evidence),
            ("编辑", self._edit_asset),
            ("删除", self._remove_asset),
        ):
            button = QPushButton(text)
            button.setObjectName("ghost")
            button.setToolTip(f"{text}：{asset.device_name}")
            button.clicked.connect(
                lambda _checked=False, name=asset.device_name, action=handler: self._row_action(
                    name, action
                )
            )
            row.addWidget(button)
        row.addStretch(1)
        return host

    def _row_action(self, device_name: str, handler) -> None:
        self._select_asset(device_name)
        handler()

    def _select_asset(self, device_name: str) -> None:
        for row, asset in enumerate(self._visible_assets):
            if asset.device_name == device_name:
                self.table.selectRow(row)
                return

    def _on_row_double_clicked(self, row: int, _column: int = 0) -> None:
        self.table.selectRow(row)
        self._edit_asset()

    def _current_asset(self) -> Asset | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._visible_assets):
            return None
        return self._visible_assets[row]

    # ---- 表单 / 刷新 ----
    def apply_form(self):
        data = self.controller.project.model_dump()
        data.update(
            {
                "project_code": self.project_code.text().strip(),
                "system_name": self.system_name.text().strip(),
                "level": 3 if self.level.currentIndex() == 0 else 2,
                "check_date": self.check_date.date().toPython(),
            }
        )
        project = self.controller.project.model_validate(data)
        self.controller.project = project
        return project

    def refresh(self) -> None:
        project = self.controller.project
        self.project_code.setText(project.project_code)
        self.system_name.setText(project.system_name)
        self.level.setCurrentIndex(0 if project.level == 3 else 1)
        self.check_date.setDate(
            QDate(project.check_date.year, project.check_date.month, project.check_date.day)
        )
        evidence_root = str(self.controller.evidence_root_path())
        self.evidence_root.setText(evidence_root)
        self.evidence_root.setToolTip(evidence_root)

        self._asset_rows = []
        linked = 0
        pending: list[str] = []
        for asset in project.assets:
            package = asset.evidence_package or ""
            preview = self.controller.inspect_evidence(package or None, asset.device_name)
            material_count = "—"
            if not package:
                text, tone = "未关联证据", "neutral"
                pending.append(f"{asset.device_name}（未关联证据）")
            elif preview.ok:
                text, tone = f"可核查：{preview.blocks} 块", "ok"
                material_count = str(preview.files)
                linked += 1
            elif preview.images:
                text, tone = f"仅附件：{preview.images} 张图片", "warn"
                material_count = str(preview.files)
                pending.append(f"{asset.device_name}（仅附件）")
            else:
                text, tone = "不可用", "bad"
                material_count = str(preview.files)
                pending.append(f"{asset.device_name}（材料不可用）")
            self._asset_rows.append(
                (asset, package, text, tone, preview.message, material_count)
            )

        self._update_readiness(len(project.assets), linked, pending)
        self._apply_filter()

    def _update_readiness(self, total: int, linked: int, pending: list[str]) -> None:
        if total == 0:
            self.readiness_badge.set_text("待导入", "neutral")
            self.readiness_summary.setText("尚未导入设备材料")
            self.readiness_pending.setText("拖入采集目录或选择日志后开始识别。")
            self.table_hint.setText(
                "尚未导入设备；拖入材料或点击「新增设备」建立第一条记录。"
            )
            return

        warning_count = total - linked
        if warning_count == 0:
            self.readiness_badge.set_text("材料就绪", "ok")
        else:
            self.readiness_badge.set_text(f"{warning_count} 台需处理", "warn")
        self.readiness_summary.setText(
            f"设备 {total} 台 / 已识别材料 {linked} 台 / 需处理 {warning_count} 台"
        )
        if pending:
            shown = "；".join(pending[:PENDING_LIMIT])
            suffix = f" 等 {len(pending)} 台" if len(pending) > PENDING_LIMIT else ""
            self.readiness_pending.setText(f"需处理：{shown}{suffix}")
        else:
            self.readiness_pending.setText("")
        self.table_hint.setText("双击行可编辑；选中设备后可上传整改材料，操作列可查看材料、编辑或删除设备。")

    def _asset_field_value(self, asset: Asset, field: str) -> str:
        value = getattr(asset, field)
        if field == "importance":
            return value.value
        return "" if value is None else str(value)

    def _apply_filter(self, *_args) -> None:
        needle = self.search.text().strip().lower()
        visible = [
            row
            for row in self._asset_rows
            if not needle
            or needle in row[0].device_name.lower()
            or needle in (row[0].ip or "").lower()
            or needle in (row[0].business_system or "").lower()
        ]
        self.table.setRowCount(0)
        self._visible_assets = []
        for asset, package, text, tone, tooltip, _material_count in visible:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            for offset, field in enumerate(ASSET_FIELD_ORDER, start=1):
                value = self._asset_field_value(asset, field)
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.table.setItem(row, offset, item)

            remediation = self.controller.remediation_files(asset)
            status_text = f"{text} · 整改 {len(remediation)} 份" if remediation else text
            status_tip = tooltip
            if remediation:
                names = "、".join(path.name for path in remediation)
                status_tip = f"{tooltip}\n整改材料（{len(remediation)} 份）：{names}"
            status = QTableWidgetItem(status_text)
            status.setToolTip(status_tip)
            self.table.setItem(row, EVIDENCE_COLUMN, status)
            self.table.setCellWidget(
                row, EVIDENCE_COLUMN, self._status_cell(status_text, tone, status_tip)
            )
            self.table.setCellWidget(row, ACTION_COLUMN, self._action_cell(asset))
            self._visible_assets.append(asset)

        if not self._asset_rows:
            self.empty_state.set_text(
                "尚未添加设备",
                "拖入采集目录或单个日志文件，或点击「新增设备」开始。",
            )
            self.table_stack.setCurrentWidget(self.empty_state)
        elif not visible:
            self.empty_state.set_text(
                "没有匹配的设备",
                "调整搜索关键词，或清空搜索框查看全部设备。",
            )
            self.table_stack.setCurrentWidget(self.empty_state)
        else:
            self.table_stack.setCurrentWidget(self.table)

    # ---- 设备动作 ----
    def _pick_evidence_root(self) -> None:
        start = str(self.controller.evidence_root_path())
        path = QFileDialog.getExistingDirectory(self, "选择证据根目录", start)
        if not path:
            return
        self.controller.project = self.controller.project.model_copy(
            update={"evidence_root": Path(path)}
        )
        self.refresh()

    def _on_dropped(self, path: str) -> None:
        relative = self.controller.display_package_path(Path(path))
        self._add_asset(initial_evidence=relative)

    def _paste_text(self) -> None:
        text, ok = QInputDialog.getMultiLineText(
            self, "粘贴证据文字", "把现场采集的命令输出 / 日志片段粘贴到这里：", ""
        )
        if not ok or not text.strip():
            return
        root = self.controller.evidence_root_path()
        pasted_dir = root / "pasted"
        pasted_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = pasted_dir / f"pasted-{stamp}-{uuid4().hex[:4]}.txt"
        target.write_text(text, encoding="utf-8")
        self._add_asset(initial_evidence=self.controller.display_package_path(target))

    def _upload_remediation(self) -> None:
        asset = self._current_asset()
        if asset is None:
            QMessageBox.information(
                self, "提示", "请先在资产表选择设备，再上传该设备的整改材料"
            )
            return
        none_label = "不关联具体问题"
        issue_nos = sorted(
            {
                issue.issue_no
                for issue in self.controller.issue_rows()
                if asset.device_name in issue.values.get("关联资产", "")
            }
        )
        choice, accepted = QInputDialog.getItem(
            self,
            "关联问题",
            f"{asset.device_name} 的整改材料对应哪个问题编号？",
            [none_label] + issue_nos,
            0,
            False,
        )
        if not accepted:
            return
        issue_no = "" if choice == none_label else choice
        start = str(self.controller.evidence_root_path())
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择整改文件",
            start,
            "整改/证据文件 (*.txt *.md *.log *.out *.json *.csv *.xlsx *.docx *.pdf);;所有文件 (*)",
        )
        if not paths:
            return
        failed: list[str] = []
        for path in paths:
            try:
                self.controller.attach_remediation(
                    asset.device_name, Path(path), issue_no
                )
            except ControllerError as exc:
                failed.append(f"{Path(path).name}：{exc}")
        self.refresh()
        self.assets_changed.emit()
        if failed:
            QMessageBox.warning(self, "部分整改材料未上传", "\n".join(failed))

    def _remove_remediation(self) -> None:
        asset = self._current_asset()
        if asset is None:
            QMessageBox.information(self, "提示", "请先在资产表选择设备")
            return
        files = self.controller.remediation_files(asset)
        if not files:
            QMessageBox.information(self, "提示", "该设备暂无整改材料")
            return
        labels = [path.name for path in files]
        choice, accepted = QInputDialog.getItem(
            self, "删除整改材料", f"{asset.device_name} 的整改材料", labels, 0, False
        )
        if not accepted:
            return
        if (
            QMessageBox.question(
                self,
                "确认删除",
                f"确定删除整改材料「{choice}」？该操作不可撤销。",
            )
            != QMessageBox.Yes
        ):
            return
        try:
            self.controller.detach_remediation(asset.device_name, choice)
        except ControllerError as exc:
            QMessageBox.warning(self, "删除失败", str(exc))
            return
        self.refresh()
        self.assets_changed.emit()

    def _add_asset(
        self,
        initial_evidence: str = "",
        *,
        pick_directory: bool = False,
        pick_log: bool = False,
    ) -> None:
        if pick_directory:
            start = str(self.controller.evidence_root_path())
            path = QFileDialog.getExistingDirectory(self, "选择采集目录", start)
            if not path:
                return
            initial_evidence = self.controller.display_package_path(Path(path))
        elif pick_log:
            start = str(self.controller.evidence_root_path())
            path, _ = QFileDialog.getOpenFileName(
                self, "选择日志或命令输出", start, "证据文件 (*.log *.txt *.out *.cmd *.json);;所有文件 (*)"
            )
            if not path:
                return
            initial_evidence = self.controller.display_package_path(Path(path))

        dialog = AssetDialog(
            self.controller,
            parent=self,
            initial_evidence=initial_evidence,
            default_asset_type=self.asset_type_selector.currentText(),
        )
        if dialog.exec() != QDialog.Accepted or dialog.asset is None:
            return
        try:
            self.controller.add_asset(dialog.asset)
        except ControllerError as exc:
            QMessageBox.warning(self, "无法添加设备", str(exc))
            return
        self.refresh()
        self.assets_changed.emit()

    def _edit_asset(self, *_args) -> None:
        asset = self._current_asset()
        if asset is None:
            QMessageBox.information(self, "提示", "请先选择一行设备")
            return
        dialog = AssetDialog(self.controller, asset, parent=self)
        if dialog.exec() != QDialog.Accepted or dialog.asset is None:
            return
        try:
            self.controller.update_asset(asset.device_name, dialog.asset)
        except ControllerError as exc:
            QMessageBox.warning(self, "无法保存设备", str(exc))
            return
        self.refresh()
        self.assets_changed.emit()

    def _review_evidence(self) -> None:
        asset = self._current_asset()
        if asset is None:
            QMessageBox.information(self, "提示", "请先选择一行设备")
            return
        if not asset.evidence_package:
            QMessageBox.information(self, "提示", f"设备「{asset.device_name}」尚未关联材料")
            return
        try:
            dialog = EvidenceReviewDialog(self.controller, asset, self)
        except ControllerError as exc:
            QMessageBox.warning(self, "材料不可用", str(exc))
            return
        dialog.exec()

    def _remove_asset(self) -> None:
        asset = self._current_asset()
        if asset is None:
            QMessageBox.information(self, "提示", "请先选择一行设备")
            return
        answer = QMessageBox.question(
            self,
            "删除设备",
            f"删除设备「{asset.device_name}」？\n只删除项目里的设备记录，不会删除证据包文件。",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.controller.remove_asset(asset.device_name)
        self.refresh()
        self.assets_changed.emit()

    # ---- 项目文件 ----
    def load_project(self) -> None:
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
        self.refresh()
        self.project_loaded.emit()

    def save_project(self) -> bool:
        try:
            project = self.apply_form()
        except Exception as exc:
            QMessageBox.warning(self, "项目信息有误", str(exc))
            return False
        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存项目",
            str(self.controller.base_dir / "project.yaml"),
            "YAML (*.yaml *.yml)",
        )
        if not path:
            return False
        target = Path(path)
        if not target.suffix:
            target = target.with_suffix(".yaml")
        try:
            self.controller.save_project(project, target)
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return False
        QMessageBox.information(self, "已保存", str(target))
        return True
