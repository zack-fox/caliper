"""① 证据与资产：项目信息、证据拖入解析、设备资产清单、核查入口。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.controller import AppController, ControllerError
from app.screens.dialogs import AssetDialog
from app.widgets import Card, DropZone, PageHeader, StatCard, divider, hbox, vbox
from core.model.entities import Asset

ASSET_COLUMNS = ("设备名称", "IP 地址", "重要程度", "作业指导书", "资产类型", "证据目录", "证据识别")

# 表格单元格状态色（与 design tokens 语义色一致）
OK_COLOR = "#12a76a"
ERROR_COLOR = "#d94040"
WARN_COLOR = "#d98300"
MUTED_COLOR = "#6b7a90"


class EvidenceScreen(QWidget):
    """证据与资产页：把"上传 → 解析 → 资产清单"串成一条主线。"""

    project_loaded = Signal()
    assets_changed = Signal()
    run_requested = Signal()

    def __init__(self, controller: AppController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setObjectName("page")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        self.header = PageHeader(
            "项目与材料",
            "导入现场日志，检查识别结果并维护设备信息；解析完成后即可生成记录草稿。",
        )
        refresh_button = QPushButton("刷新")
        refresh_button.setObjectName("subtle")
        refresh_button.clicked.connect(self.refresh)
        self.header.add_action(refresh_button)
        layout.addWidget(self.header)

        # ---- 统计卡 ----
        self.stat_assets = StatCard("设备总数", "0", "已纳入本次核查")
        self.stat_linked = StatCard("已关联材料", "0", "可生成记录草稿")
        self.stat_blocks = StatCard("可核查块", "0", "解析出的检查块")
        self.stat_warn = StatCard("需处理", "0", "仅附件 / 不可用")
        stat_row = QHBoxLayout()
        stat_row.setSpacing(12)
        for card in (self.stat_assets, self.stat_linked, self.stat_blocks, self.stat_warn):
            stat_row.addWidget(card, 1)
        layout.addLayout(stat_row)

        # ---- 项目信息 ----
        project_card = Card("项目信息", "决定规则包与指导书")
        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 2, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        self.project_code = QLineEdit()
        self.project_code.setPlaceholderText("可留空")
        self.system_name = QLineEdit()
        self.system_name.setPlaceholderText("例如：示例系统A")
        self.level = QComboBox()
        self.level.addItems(["三级", "二级"])
        self.check_date = QDateEdit(QDate.currentDate())
        self.check_date.setCalendarPopup(True)
        self.output_dir = QLabel("—")
        self.output_dir.setObjectName("mono")
        self.pack_dir = QLabel("—")
        self.pack_dir.setObjectName("mono")
        for column, (caption, widget) in enumerate(
            (
                ("项目编号", self.project_code),
                ("系统名称", self.system_name),
                ("等级", self.level),
                ("核查日期", self.check_date),
            )
        ):
            grid.addWidget(self._caption(caption), 0, column * 2)
            grid.addWidget(widget, 0, column * 2 + 1)
        grid.addWidget(self._caption("输出目录"), 1, 0)
        grid.addWidget(self.output_dir, 1, 1, 1, 3)
        grid.addWidget(self._caption("规则包"), 1, 4)
        grid.addWidget(self.pack_dir, 1, 5, 1, 3)
        for column in (1, 3, 5, 7):
            grid.setColumnStretch(column, 1)
        project_card.add(grid_host)
        layout.addWidget(project_card)

        # ---- 拖拽上传 ----
        self.dropzone = DropZone()
        pick_dir = QPushButton("选择采集目录…")
        pick_dir.clicked.connect(lambda: self._add_asset(pick_directory=True))
        pick_log = QPushButton("选择日志文件…")
        pick_log.clicked.connect(lambda: self._add_asset(pick_log=True))
        self.dropzone.add_action(pick_dir)
        self.dropzone.add_action(pick_log)
        self.dropzone.path_dropped.connect(self._on_dropped)
        layout.addWidget(self.dropzone)

        # ---- 资产表 ----
        asset_card = Card("设备与证据包", "双击行可编辑")
        import_button = QPushButton("导入设备证据")
        import_button.setObjectName("primary")
        import_button.clicked.connect(lambda: self._add_asset())
        self.edit_button = QPushButton("编辑选中")
        self.edit_button.clicked.connect(self._edit_asset)
        self.remove_button = QPushButton("删除设备")
        self.remove_button.setObjectName("danger")
        self.remove_button.clicked.connect(self._remove_asset)
        self.run_button = QPushButton("生成记录草稿")
        self.run_button.setObjectName("primary")
        self.run_button.clicked.connect(self.run_requested.emit)
        asset_card.add_action(import_button)
        asset_card.add_action(self.edit_button)
        asset_card.add_action(self.remove_button)
        asset_card.add_action(self.run_button)

        self.table = QTableWidget(0, len(ASSET_COLUMNS))
        self.table.setHorizontalHeaderLabels(ASSET_COLUMNS)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, len(ASSET_COLUMNS) - 1):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(len(ASSET_COLUMNS) - 1, QHeaderView.Stretch)
        self.table.cellDoubleClicked.connect(self._edit_asset)
        asset_card.add(self.table, 1)
        layout.addWidget(asset_card, 1)

        self.refresh()

    # ---- 小工具 ----
    @staticmethod
    def _caption(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("secondary")
        return label

    def _current_asset(self) -> Asset | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.controller.project.assets):
            return None
        return self.controller.project.assets[row]

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
        self.output_dir.setText(str(self.controller.export_dir()))
        self.pack_dir.setText(str(self.controller.project.pack_dir or "默认规则包"))

        self.table.setRowCount(0)
        linked = 0
        blocks = 0
        warnings = 0
        for asset in project.assets:
            row = self.table.rowCount()
            self.table.insertRow(row)
            package = asset.evidence_package or ""
            values = (
                asset.device_name,
                asset.ip,
                asset.importance.value,
                asset.guide,
                asset.asset_type.value,
                Path(package).name if package else "",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(package if column == 5 else value)
                self.table.setItem(row, column, item)

            preview = self.controller.inspect_evidence(package or None, asset.device_name)
            if not package:
                text, colour = "未关联证据", MUTED_COLOR
            elif preview.ok:
                text, colour = f"可核查：{preview.blocks} 块", OK_COLOR
                linked += 1
                blocks += preview.blocks
            elif preview.images:
                text, colour = f"仅附件：{preview.images} 张图片", WARN_COLOR
                warnings += 1
            else:
                text, colour = "不可用", ERROR_COLOR
                warnings += 1
            status = QTableWidgetItem(text)
            status.setForeground(QColor(colour))
            status.setToolTip(preview.message)
            self.table.setItem(row, len(ASSET_COLUMNS) - 1, status)

        self.stat_assets.set_value(str(len(project.assets)))
        self.stat_linked.set_value(str(linked))
        self.stat_blocks.set_value(str(blocks))
        self.stat_warn.set_value(str(warnings))

    # ---- 设备动作 ----
    def _on_dropped(self, path: str) -> None:
        relative = self.controller.display_package_path(Path(path))
        self._add_asset(initial_evidence=relative)

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

        dialog = AssetDialog(self.controller, parent=self, initial_evidence=initial_evidence)
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
