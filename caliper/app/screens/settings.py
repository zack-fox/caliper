"""设置：证据根目录、输出目录与规则包目录。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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


class SettingsDialog(QDialog):
    def __init__(self, controller: AppController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("设置")
        self.setMinimumWidth(640)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(12)
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
            "规则包目录决定判定规则，一般不需要修改；"
            "输出目录用于保存导出的四张表。相对路径按项目文件所在目录解析。"
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
