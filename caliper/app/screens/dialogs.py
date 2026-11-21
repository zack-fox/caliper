"""对话框：设备 / 证据录入，运行设置。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
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
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.controller import AppController
from core.contracts.enums import AssetType, Importance
from core.model.entities import Asset


class EvidenceReviewDialog(QDialog):
    """逐个审阅已登记材料；这里只展示来源内容，不会自行改变判定。"""

    KIND_LABELS = {
        "image": "截图 / 图片",
        "spreadsheet": "表格",
        "configuration": "配置文件",
        "code": "代码片段",
        "text": "文本 / 命令日志",
        "file": "其他附件",
    }

    def __init__(self, controller: AppController, asset: Asset, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.asset = asset
        self.package = controller.evidence_details(asset.evidence_package or "", asset.device_name)
        self.setWindowTitle(f"材料审阅 · {asset.device_name}")
        self.resize(1080, 690)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)
        intro = QLabel(
            f"共登记 {len(self.package.evidence_files)} 个文件；只有已解析为检查块的材料参与当前自动判定。"
        )
        intro.setObjectName("muted")
        layout.addWidget(intro)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.file_list = QListWidget()
        self.file_list.setMinimumWidth(270)
        splitter.addWidget(self.file_list)

        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(8, 0, 0, 0)
        self.filename = QLabel("选择左侧文件")
        self.filename.setObjectName("section_title")
        self.filename.setWordWrap(True)
        self.metadata = QLabel("")
        self.metadata.setObjectName("muted")
        self.metadata.setWordWrap(True)
        detail_layout.addWidget(self.filename)
        detail_layout.addWidget(self.metadata)

        self.preview_stack = QStackedWidget()
        self.text_preview = QPlainTextEdit()
        self.text_preview.setReadOnly(True)
        self.text_preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.image_preview = QLabel("图片无法预览")
        self.image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_preview.setMinimumSize(300, 240)
        self.preview_note = QLabel("")
        self.preview_note.setObjectName("muted")
        self.preview_note.setWordWrap(True)
        self.preview_stack.addWidget(self.text_preview)
        self.preview_stack.addWidget(self.image_preview)
        detail_layout.addWidget(self.preview_stack, 1)
        detail_layout.addWidget(self.preview_note)
        splitter.addWidget(detail)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter, 1)

        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        close.button(QDialogButtonBox.StandardButton.Close).setText("关闭")
        layout.addWidget(close)

        for entry in self.package.evidence_files:
            state = "已解析" if entry.analyzed else "仅登记"
            label = f"{entry.path}  ·  {state}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, entry.path)
            item.setToolTip(f"{self.KIND_LABELS.get(entry.kind, entry.kind)} · {entry.size} B")
            self.file_list.addItem(item)
        self.file_list.currentRowChanged.connect(self._show_file)
        if self.package.evidence_files:
            self.file_list.setCurrentRow(0)
        else:
            self.preview_note.setText("没有可审阅的文件材料。")

    def _show_file(self, row: int) -> None:
        if row < 0 or row >= len(self.package.evidence_files):
            return
        entry = self.package.evidence_files[row]
        root = self.package.root
        path = root if root.is_file() else root / entry.path
        state = "已解析并参与自动判定" if entry.analyzed else "已登记；尚未参与自动判定"
        self.filename.setText(entry.path)
        self.metadata.setText(
            f"类型：{self.KIND_LABELS.get(entry.kind, entry.kind)}　·　大小：{entry.size:,} B　·　状态：{state}\n"
            f"SHA-256：{entry.sha256}"
        )
        self.preview_note.clear()
        if entry.kind == "image":
            pixmap = QPixmap(str(path))
            if pixmap.isNull():
                self.image_preview.setText("图片文件无法读取")
            else:
                self.image_preview.setPixmap(
                    pixmap.scaled(
                        self.image_preview.size(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
            self.preview_stack.setCurrentWidget(self.image_preview)
        elif entry.kind in {"text", "configuration", "code"}:
            if entry.size > 2 * 1024 * 1024:
                self.text_preview.setPlainText("文件超过 2 MB，暂不在审阅窗口内载入全文。")
            else:
                self.text_preview.setPlainText(path.read_text(encoding="utf-8-sig", errors="replace"))
            self.preview_stack.setCurrentWidget(self.text_preview)
            if not entry.analyzed:
                self.preview_note.setText("当前版本仅登记并展示该材料；需人工核对，不能据此自动形成测评结论。")
        else:
            self.text_preview.setPlainText(
                f"该文件已登记并完成 SHA-256 校验。当前版本不支持此类型的内容预览。\n\n路径：{path}"
            )
            self.preview_stack.setCurrentWidget(self.text_preview)
            self.preview_note.setText("该附件不会自动参与测评判定。")


class TextDetailsDialog(QDialog):
    """可滚动查看较长的诊断信息。"""

    def __init__(self, title: str, text: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(860, 580)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)
        body = QPlainTextEdit()
        body.setReadOnly(True)
        body.setPlainText(text)
        layout.addWidget(body, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("关闭")
        layout.addWidget(buttons)


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
