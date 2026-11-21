"""① 项目与资产。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDate, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
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

from app.controller import AppController
from core.contracts.enums import AssetType, Importance
from core.model.entities import Asset, ProjectConfig

ASSET_COLUMNS = ("设备名称", "IP 地址", "重要程度", "作业指导书", "资产类型", "证据包")


class AssetDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("添加资产")
        form = QFormLayout(self)
        self.device_name = QLineEdit()
        self.ip = QLineEdit()
        self.ip.setPlaceholderText("例如 192.0.2.10")
        self.importance = QComboBox()
        self.importance.addItems([item.value for item in Importance])
        self.guide = QLineEdit("三级-安全通用要求")
        self.asset_type = QComboBox()
        self.asset_type.addItems([item.value for item in AssetType])
        self.evidence_package = QLineEdit()
        self.evidence_package.setPlaceholderText("fixtures/evidence 下的目录名，可留空")
        form.addRow("设备名称*", self.device_name)
        form.addRow("IP 地址*", self.ip)
        form.addRow("重要程度*", self.importance)
        form.addRow("作业指导书*", self.guide)
        form.addRow("资产类型", self.asset_type)
        form.addRow("证据包目录", self.evidence_package)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def to_asset(self) -> Asset:
        return Asset(
            device_name=self.device_name.text().strip(),
            ip=self.ip.text().strip(),
            importance=Importance(self.importance.currentText()),
            guide=self.guide.text().strip(),
            asset_type=AssetType(self.asset_type.currentText()),
            evidence_package=self.evidence_package.text().strip() or None,
        )


class ProjectScreen(QWidget):
    project_loaded = Signal()

    def __init__(self, controller: AppController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        layout = QVBoxLayout(self)

        info_box = QGroupBox("项目信息（可留空，导出时为空只提示不阻止）")
        form = QFormLayout(info_box)
        self.project_code = QLineEdit()
        self.system_name = QLineEdit()
        self.level = QComboBox()
        self.level.addItems(["三级", "二级"])
        self.check_date = QDateEdit(QDate.currentDate())
        self.check_date.setCalendarPopup(True)
        self.evidence_root = QLineEdit()
        self.output_dir = QLineEdit()
        self.pack_dir = QLineEdit()
        for field, label in (
            (self.project_code, "项目编号"),
            (self.system_name, "系统名称"),
        ):
            form.addRow(label, field)
        form.addRow("等级", self.level)
        form.addRow("核查日期", self.check_date)
        for field, label, dialog in (
            (self.evidence_root, "证据根目录", self._pick_evidence),
            (self.output_dir, "输出目录", self._pick_output),
            (self.pack_dir, "规则包目录", self._pick_pack),
        ):
            row = QHBoxLayout()
            row.addWidget(field)
            button = QPushButton("选择")
            button.clicked.connect(dialog)
            row.addWidget(button)
            form.addRow(label, row)
        layout.addWidget(info_box)

        asset_box = QGroupBox("资产列表")
        asset_layout = QVBoxLayout(asset_box)
        self.table = QTableWidget(0, len(ASSET_COLUMNS))
        self.table.setHorizontalHeaderLabels(ASSET_COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        asset_layout.addWidget(self.table)

        buttons = QHBoxLayout()
        self.add_button = QPushButton("添加资产")
        self.add_button.clicked.connect(self._add_asset)
        self.remove_button = QPushButton("删除选中")
        self.remove_button.setObjectName("danger")
        self.remove_button.clicked.connect(self._remove_asset)
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.remove_button)
        buttons.addStretch(1)
        self.hint = QLabel("资产与证据包一一对应；没有证据包的资产会整体按未采集处理。")
        self.hint.setObjectName("muted")
        buttons.addWidget(self.hint)
        asset_layout.addLayout(buttons)
        layout.addWidget(asset_box, 1)

        actions = QHBoxLayout()
        self.load_button = QPushButton("加载项目…")
        self.load_button.clicked.connect(self._load_project)
        self.save_button = QPushButton("保存项目…")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self._save_project)
        actions.addWidget(self.load_button)
        actions.addWidget(self.save_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.refresh()

    # ---- 表单 ----
    def apply_form(self) -> ProjectConfig:
        data = self.controller.project.model_dump()
        data.update(
            {
                "project_code": self.project_code.text().strip(),
                "system_name": self.system_name.text().strip(),
                "level": 3 if self.level.currentIndex() == 0 else 2,
                "check_date": self.check_date.date().toPython(),
                "evidence_root": self.evidence_root.text().strip(),
                "output_dir": self.output_dir.text().strip(),
                "pack_dir": self.pack_dir.text().strip() or None,
            }
        )
        project = ProjectConfig.model_validate(data)
        self.controller.project = project
        return project

    def refresh(self) -> None:
        project = self.controller.project
        self.project_code.setText(project.project_code)
        self.system_name.setText(project.system_name)
        self.level.setCurrentIndex(0 if project.level == 3 else 1)
        self.check_date.setDate(QDate(project.check_date.year, project.check_date.month, project.check_date.day))
        self.evidence_root.setText(str(project.evidence_root))
        self.output_dir.setText(str(project.output_dir))
        self.pack_dir.setText(str(project.pack_dir or ""))

        self.table.setRowCount(0)
        for asset in project.assets:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = (
                asset.device_name,
                asset.ip,
                asset.importance.value,
                asset.guide,
                asset.asset_type.value,
                asset.evidence_package or "",
            )
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))

    # ---- 动作 ----
    def _add_asset(self) -> None:
        dialog = AssetDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            self.controller.add_asset(dialog.to_asset())
        except Exception as exc:  # pydantic 校验信息原样展示给现场人员
            QMessageBox.warning(self, "资产校验失败", str(exc))
            return
        self.refresh()

    def _remove_asset(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        name = self.table.item(row, 0).text()
        self.controller.remove_asset(name)
        self.refresh()

    def _load_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "加载项目", str(self.controller.base_dir), "YAML (*.yaml *.yml)")
        if not path:
            return
        try:
            self.controller.load_project(path)
        except Exception as exc:
            QMessageBox.critical(self, "加载失败", str(exc))
            return
        self.refresh()
        self.project_loaded.emit()

    def _save_project(self) -> None:
        try:
            project = self.apply_form()
        except Exception as exc:
            QMessageBox.warning(self, "项目信息有误", str(exc))
            return
        path, _ = QFileDialog.getSaveFileName(self, "保存项目", str(self.controller.base_dir / "project.yaml"), "YAML (*.yaml *.yml)")
        if not path:
            return
        try:
            self.controller.save_project(project, self._ensure_suffix(path))
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        QMessageBox.information(self, "已保存", path)

    @staticmethod
    def _ensure_suffix(path: str) -> Path:
        target = Path(path)
        return target if target.suffix else target.with_suffix(".yaml")

    # ---- 目录选择 ----
    def _pick_dir(self, field: QLineEdit, title: str) -> None:
        path = QFileDialog.getExistingDirectory(self, title, field.text() or str(self.controller.base_dir))
        if path:
            field.setText(path)

    def _pick_evidence(self) -> None:
        self._pick_dir(self.evidence_root, "选择证据根目录")

    def _pick_output(self) -> None:
        self._pick_dir(self.output_dir, "选择输出目录")

    def _pick_pack(self) -> None:
        self._pick_dir(self.pack_dir, "选择规则包目录")
