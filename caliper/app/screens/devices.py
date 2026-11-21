"""① 设备与证据：项目信息、设备资产、证据包导入与核查入口。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
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
from core.contracts.enums import AssetType, Importance
from core.model.entities import Asset

ASSET_COLUMNS = ("设备名称", "IP 地址", "重要程度", "作业指导书", "资产类型", "证据包", "证据识别")

OK_COLOR = "#1f9d55"
ERROR_COLOR = "#d64545"
MUTED_COLOR = "#6b7785"


class AssetDialog(QDialog):
    """新增 / 编辑设备：可直接选择证据包目录并即时解析。"""

    def __init__(
        self, controller: AppController, asset: Asset | None = None, parent=None
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self.original = asset
        self.asset: Asset | None = None
        self.setWindowTitle("编辑设备" if asset is not None else "导入设备证据")
        self.setMinimumWidth(680)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        self.device_name = QLineEdit(asset.device_name if asset else "")
        self.device_name.setPlaceholderText("例如：示例系统A-应用服务器")
        self.ip = QLineEdit(asset.ip if asset else "")
        self.ip.setPlaceholderText("例如：192.0.2.10")
        self.importance = QComboBox()
        self.importance.addItems([item.value for item in Importance])
        if asset is not None:
            self.importance.setCurrentText(asset.importance.value)
        else:
            self.importance.setCurrentText(Importance.NORMAL.value)
        self.guide = QComboBox()
        self.guide.setEditable(True)
        guides = controller.guides() or ["三级-安全通用要求", "二级-安全通用要求"]
        self.guide.addItems(guides)
        if asset is not None:
            self.guide.setCurrentText(asset.guide)
        else:
            preferred = (
                "三级-安全通用要求" if controller.project.level == 3 else "二级-安全通用要求"
            )
            if preferred in guides:
                self.guide.setCurrentText(preferred)
        self.asset_type = QComboBox()
        self.asset_type.addItems([item.value for item in AssetType])
        if asset is not None:
            self.asset_type.setCurrentText(asset.asset_type.value)

        package_row = QHBoxLayout()
        package_row.setSpacing(6)
        self.evidence = QLineEdit(asset.evidence_package if asset else "")
        self.evidence.setPlaceholderText("选择采集输出目录（含 manifest.json），可留空")
        pick = QPushButton("选择目录…")
        pick.clicked.connect(self._pick_package)
        clear = QPushButton("清除")
        clear.clicked.connect(self._clear_package)
        package_row.addWidget(self.evidence, 1)
        package_row.addWidget(pick)
        package_row.addWidget(clear)

        form.addRow("设备名称 *", self.device_name)
        form.addRow("IP 地址 *", self.ip)
        form.addRow("重要程度 *", self.importance)
        form.addRow("作业指导书 *", self.guide)
        form.addRow("资产类型", self.asset_type)
        form.addRow("证据包目录", package_row)
        layout.addLayout(form)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        hint = QLabel(
            "证据包是采集脚本输出的目录，需包含 manifest.json，"
            "以及 raw/*.log 或 checks/*.json。"
        )
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("确定")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.evidence.editingFinished.connect(self._update_status)
        self._update_status()

    def _pick_package(self) -> None:
        current = self.evidence.text().strip()
        start = (
            str(self.controller.evidence_path(current))
            if current
            else str(self.controller.evidence_root_path())
        )
        path = QFileDialog.getExistingDirectory(self, "选择证据包目录", start)
        if not path:
            return
        self.evidence.setText(self.controller.display_package_path(Path(path)))
        self._update_status()

    def _clear_package(self) -> None:
        self.evidence.clear()
        self._update_status()

    def _update_status(self) -> None:
        preview = self.controller.inspect_evidence(
            self.evidence.text().strip() or None
        )
        self.status.setText(preview.message)
        self.status.setObjectName("success" if preview.ok else "warning")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        if preview.ok and not self.device_name.text().strip():
            self.device_name.setText(preview.host)

    def accept(self) -> None:
        data = self.original.model_dump() if self.original is not None else {}
        data.update(
            {
                "device_name": self.device_name.text().strip(),
                "ip": self.ip.text().strip(),
                "importance": self.importance.currentText(),
                "guide": self.guide.currentText().strip(),
                "asset_type": self.asset_type.currentText(),
                "evidence_package": self.evidence.text().strip() or None,
            }
        )
        try:
            self.asset = Asset.model_validate(data)
        except Exception as exc:  # pydantic 校验信息原样展示
            QMessageBox.warning(self, "请检查输入", str(exc))
            return
        super().accept()


class DevicesScreen(QWidget):
    """主界面：项目信息 + 设备/证据包列表 + 核查入口。"""

    project_loaded = Signal()
    run_requested = Signal()

    def __init__(self, controller: AppController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        project_box = QGroupBox("项目")
        grid = QGridLayout(project_box)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        self.project_code = QLineEdit()
        self.project_code.setPlaceholderText("可留空")
        self.system_name = QLineEdit()
        self.system_name.setPlaceholderText("可留空")
        self.level = QComboBox()
        self.level.addItems(["三级", "二级"])
        self.check_date = QDateEdit(QDate.currentDate())
        self.check_date.setCalendarPopup(True)
        grid.addWidget(QLabel("项目编号"), 0, 0)
        grid.addWidget(self.project_code, 0, 1)
        grid.addWidget(QLabel("系统名称"), 0, 2)
        grid.addWidget(self.system_name, 0, 3)
        grid.addWidget(QLabel("等级"), 1, 0)
        grid.addWidget(self.level, 1, 1)
        grid.addWidget(QLabel("核查日期"), 1, 2)
        grid.addWidget(self.check_date, 1, 3)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        layout.addWidget(project_box)

        evidence_box = QGroupBox("设备与证据包")
        evidence_layout = QVBoxLayout(evidence_box)
        evidence_layout.setSpacing(8)
        hint = QLabel(
            "主流程：导入设备证据包 → 核对识别结果 → 开始核查。"
            "证据包目录需包含 manifest.json；双击表格行可编辑设备。"
        )
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        evidence_layout.addWidget(hint)

        self.table = QTableWidget(0, len(ASSET_COLUMNS))
        self.table.setHorizontalHeaderLabels(ASSET_COLUMNS)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, len(ASSET_COLUMNS) - 1):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(len(ASSET_COLUMNS) - 1, QHeaderView.Stretch)
        self.table.cellDoubleClicked.connect(self._edit_asset)
        evidence_layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        self.import_button = QPushButton("导入设备证据")
        self.import_button.setObjectName("primary")
        self.import_button.clicked.connect(self._add_asset)
        self.edit_button = QPushButton("编辑选中")
        self.edit_button.clicked.connect(self._edit_asset)
        self.remove_button = QPushButton("删除设备")
        self.remove_button.setObjectName("danger")
        self.remove_button.clicked.connect(self._remove_asset)
        self.run_button = QPushButton("开始核查")
        self.run_button.setObjectName("primary")
        self.run_button.clicked.connect(self.run_requested.emit)
        buttons.addWidget(self.import_button)
        buttons.addWidget(self.edit_button)
        buttons.addWidget(self.remove_button)
        buttons.addStretch(1)
        buttons.addWidget(self.run_button)
        evidence_layout.addLayout(buttons)
        layout.addWidget(evidence_box, 1)

        self.refresh()

    # ---- 表单 ----
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

        self.table.setRowCount(0)
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

            preview = self.controller.inspect_evidence(package or None)
            if not package:
                text, colour = "未关联证据包", MUTED_COLOR
            elif preview.ok:
                text, colour = f"可核查：{preview.blocks} 块", OK_COLOR
            else:
                text, colour = "不可用", ERROR_COLOR
            status = QTableWidgetItem(text)
            status.setForeground(QColor(colour))
            status.setToolTip(preview.message)
            self.table.setItem(row, len(ASSET_COLUMNS) - 1, status)

    # ---- 动作 ----
    def _current_asset(self) -> Asset | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.controller.project.assets):
            return None
        return self.controller.project.assets[row]

    def _add_asset(self) -> None:
        dialog = AssetDialog(self.controller, parent=self)
        if dialog.exec() != QDialog.Accepted or dialog.asset is None:
            return
        try:
            self.controller.add_asset(dialog.asset)
        except ControllerError as exc:
            QMessageBox.warning(self, "无法添加设备", str(exc))
            return
        self.refresh()

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

    def save_project(self) -> None:
        try:
            project = self.apply_form()
        except Exception as exc:
            QMessageBox.warning(self, "项目信息有误", str(exc))
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存项目",
            str(self.controller.base_dir / "project.yaml"),
            "YAML (*.yaml *.yml)",
        )
        if not path:
            return
        target = Path(path)
        if not target.suffix:
            target = target.with_suffix(".yaml")
        try:
            self.controller.save_project(project, target)
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        QMessageBox.information(self, "已保存", str(target))
