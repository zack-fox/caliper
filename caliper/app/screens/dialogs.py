"""对话框：设备 / 证据录入，运行设置。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app.controller import AppController
from core.contracts.enums import AssetType, Importance
from core.model.entities import Asset


class AssetDialog(QDialog):
    """新增 / 编辑设备：可直接选择证据包目录并即时解析。"""

    def __init__(
        self,
        controller: AppController,
        asset: Asset | None = None,
        parent=None,
        initial_evidence: str = "",
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self.original = asset
        self.asset: Asset | None = None
        self.setWindowTitle("编辑设备" if asset is not None else "导入设备证据")
        self.setMinimumWidth(700)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        self.device_name = QLineEdit(asset.device_name if asset else "")
        self.device_name.setPlaceholderText("例如：示例系统A-应用服务器")
        self.ip = QLineEdit(asset.ip if asset else "")
        self.ip.setPlaceholderText("例如：192.0.2.10")
        self.importance = QComboBox()
        self.importance.addItems([item.value for item in Importance])
        self.importance.setCurrentText(
            asset.importance.value if asset is not None else Importance.NORMAL.value
        )
        self.guide = QComboBox()
        self.guide.setEditable(True)
        guides = controller.guides() or ["三级-安全通用要求", "二级-安全通用要求"]
        self.guide.addItems(guides)
        if asset is not None:
            self.guide.setCurrentText(asset.guide)
        else:
            preferred = "三级-安全通用要求" if controller.project.level == 3 else "二级-安全通用要求"
            if preferred in guides:
                self.guide.setCurrentText(preferred)
        self.asset_type = QComboBox()
        self.asset_type.addItems([item.value for item in AssetType])
        if asset is not None:
            self.asset_type.setCurrentText(asset.asset_type.value)

        package_row = QHBoxLayout()
        package_row.setSpacing(6)
        self.evidence = QLineEdit(asset.evidence_package if asset else "")
        self.evidence.setPlaceholderText("采集日志 / 命令输出 / 截图所在的目录或单个日志文件")
        pick = QPushButton("选择目录…")
        pick.clicked.connect(self._pick_package)
        pick_file = QPushButton("选择日志…")
        pick_file.clicked.connect(self._pick_log)
        clear = QPushButton("清除")
        clear.clicked.connect(self._clear_package)
        package_row.addWidget(self.evidence, 1)
        package_row.addWidget(pick)
        package_row.addWidget(pick_file)
        package_row.addWidget(clear)

        form.addRow("设备名称 *", self.device_name)
        form.addRow("IP 地址 *", self.ip)
        form.addRow("重要程度 *", self.importance)
        form.addRow("作业指导书 *", self.guide)
        form.addRow("资产类型", self.asset_type)
        form.addRow("证据目录", package_row)
        layout.addLayout(form)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        hint = QLabel(
            "拖入或选择采集目录、单个日志文件均可；有 manifest.json 时走结构化校验，"
            "没有则按原始日志解析。截图、照片只作证据附件，不参与自动判定。"
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

        if initial_evidence and not self.evidence.text().strip():
            self.evidence.setText(initial_evidence)
        self.evidence.editingFinished.connect(self._update_status)
        self._update_status()

    # ---- 证据选择 ----
    def _pick_package(self) -> None:
        current = self.evidence.text().strip()
        start = (
            str(self.controller.evidence_path(current))
            if current
            else str(self.controller.evidence_root_path())
        )
        path = QFileDialog.getExistingDirectory(self, "选择证据目录", start)
        if not path:
            return
        self.evidence.setText(self.controller.display_package_path(Path(path)))
        self._update_status()

    def _pick_log(self) -> None:
        current = self.evidence.text().strip()
        start = (
            str(self.controller.evidence_path(current))
            if current
            else str(self.controller.evidence_root_path())
        )
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择日志或命令输出",
            start,
            "证据文件 (*.log *.txt *.out *.cmd *.json);;所有文件 (*)",
        )
        if not path:
            return
        self.evidence.setText(self.controller.display_package_path(Path(path)))
        self._update_status()

    def _clear_package(self) -> None:
        self.evidence.clear()
        self._update_status()

    def _update_status(self) -> None:
        preview = self.controller.inspect_evidence(
            self.evidence.text().strip() or None,
            self.device_name.text().strip(),
        )
        self.status.setText(preview.message)
        self.status.setObjectName(
            "success" if preview.ok else "warning" if preview.images else "muted"
        )
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


class SettingsDialog(QDialog):
    """运行设置：证据根目录、输出目录、规则包目录。"""

    def __init__(self, controller: AppController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("运行设置")
        self.setMinimumWidth(660)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        self.evidence_root = QLineEdit()
        self.output_dir = QLineEdit()
        self.pack_dir = QLineEdit()
        form.addRow(
            "证据根目录",
            self._path_row(self.evidence_root, "选择证据根目录", self._pick_evidence),
        )
        form.addRow(
            "输出目录",
            self._path_row(self.output_dir, "选择输出目录", self._pick_output),
        )
        form.addRow(
            "规则包目录",
            self._path_row(self.pack_dir, "选择规则包目录", self._pick_pack),
        )
        layout.addLayout(form)

        hint = QLabel(
            "规则包目录决定判定规则，一般不需要修改；输出目录用于保存导出的四张表。"
            "相对路径按项目文件所在目录解析。"
        )
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        project = controller.project
        self.evidence_root.setText(str(project.evidence_root))
        self.output_dir.setText(str(project.output_dir))
        self.pack_dir.setText(str(project.pack_dir or ""))

    @staticmethod
    def _path_row(field: QLineEdit, title: str, handler) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)
        field.setPlaceholderText(title)
        row.addWidget(field, 1)
        button = QPushButton("选择…")
        button.clicked.connect(handler)
        row.addWidget(button)
        return row

    def _browse(self, field: QLineEdit, title: str) -> None:
        start = field.text().strip() or str(self.controller.base_dir)
        path = QFileDialog.getExistingDirectory(self, title, start)
        if path:
            field.setText(path)

    def _pick_evidence(self) -> None:
        self._browse(self.evidence_root, "选择证据根目录")

    def _pick_output(self) -> None:
        self._browse(self.output_dir, "选择输出目录")

    def _pick_pack(self) -> None:
        self._browse(self.pack_dir, "选择规则包目录")

    def accept(self) -> None:
        data = self.controller.project.model_dump()
        data.update(
            {
                "evidence_root": self.evidence_root.text().strip()
                or self.controller.project.evidence_root,
                "output_dir": self.output_dir.text().strip()
                or self.controller.project.output_dir,
                "pack_dir": self.pack_dir.text().strip()
                or self.controller.project.pack_dir,
            }
        )
        try:
            project = self.controller.project.model_validate(data)
        except Exception as exc:
            QMessageBox.warning(self, "设置不合法", str(exc))
            return
        self.controller.project = project
        super().accept()
