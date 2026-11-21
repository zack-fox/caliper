"""④ 导出：结果记录表、资产记录表、问题汇总与重大隐患。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.controller import AppController


class ExportScreen(QWidget):
    def __init__(self, controller: AppController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        layout = QVBoxLayout(self)

        title = QLabel("导出")
        title.setObjectName("title")
        layout.addWidget(title)

        box = QGroupBox("输出目录")
        box_layout = QHBoxLayout(box)
        self.output = QLineEdit()
        box_layout.addWidget(self.output, 1)
        browse = QPushButton("选择")
        browse.clicked.connect(self._pick_dir)
        box_layout.addWidget(browse)
        layout.addWidget(box)

        info = QLabel(
            "结果记录表由判定结果生成；资产记录表读取人工维护的 18 列原表，"
            "只补空白、不覆盖人工值；问题汇总取不符合/部分符合项，"
            "重大隐患只收「问题与重大」页勾选确认的行。"
        )
        info.setObjectName("muted")
        info.setWordWrap(True)
        layout.addWidget(info)

        asset_box = QGroupBox("资产记录表补全")
        asset_layout = QHBoxLayout(asset_box)
        self.asset_source = QLineEdit()
        self.asset_source.setPlaceholderText("选择人工维护的资产记录表（18 列）")
        asset_layout.addWidget(self.asset_source, 1)
        pick_asset = QPushButton("选择")
        pick_asset.clicked.connect(self._pick_asset)
        asset_layout.addWidget(pick_asset)
        self.asset_button = QPushButton("导出资产记录表")
        self.asset_button.clicked.connect(self._export_asset)
        asset_layout.addWidget(self.asset_button)
        layout.addWidget(asset_box)

        sheet_box = QGroupBox("安全问题与重大隐患")
        sheet_layout = QHBoxLayout(sheet_box)
        issue_button = QPushButton("导出安全问题汇总")
        issue_button.clicked.connect(self._export_issue)
        sheet_layout.addWidget(issue_button)
        major_button = QPushButton("导出重大安全隐患")
        major_button.clicked.connect(self._export_major)
        sheet_layout.addWidget(major_button)
        sheet_layout.addStretch(1)
        layout.addWidget(sheet_box)

        actions = QHBoxLayout()
        self.export_button = QPushButton("导出结果记录表")
        self.export_button.setObjectName("primary")
        self.export_button.clicked.connect(self._export)
        actions.addWidget(self.export_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log, 1)

        self.refresh()

    def refresh(self) -> None:
        self.output.setText(str(self.controller.export_dir()))

    def _pick_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择输出目录", self.output.text())
        if path:
            self.output.setText(path)

    def _pick_asset(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择资产记录表", "", "Excel 文件 (*.xlsx)"
        )
        if path:
            self.asset_source.setText(path)

    def _apply_output(self) -> bool:
        if not self.output.text().strip():
            self.log.append("请先选择输出目录")
            return False
        self.controller.project = self.controller.project.model_copy(
            update={"output_dir": Path(self.output.text().strip())}
        )
        return True

    def _export_asset(self) -> None:
        source = self.asset_source.text().strip()
        if not source:
            self.log.append("请先选择人工维护的资产记录表")
            return
        if not self._apply_output():
            return
        try:
            target, errors, warnings = self.controller.export_asset(Path(source))
        except Exception as exc:
            self.log.append(f"[失败] {exc}")
            return
        for warning in warnings:
            self.log.append(f"[提示] {warning}")
        if errors:
            for error in errors:
                self.log.append(f"[失败] {error}")
            return
        self.log.append(f"[完成] {target}")
        self.log.append("[自检] 必填 / IP / 作业指导书 全部通过")

    def _export_issue(self) -> None:
        if not self._apply_output():
            return
        try:
            target, problems = self.controller.export_issue()
        except Exception as exc:
            self.log.append(f"[失败] {exc}")
            return
        self.log.append(f"[完成] {target}")
        for problem in problems:
            self.log.append(f"[自检失败] {problem}")

    def _export_major(self) -> None:
        if not self._apply_output():
            return
        try:
            target, problems = self.controller.export_major()
        except Exception as exc:
            self.log.append(f"[失败] {exc}")
            return
        self.log.append(f"[完成] {target}")
        for problem in problems:
            self.log.append(f"[自检失败] {problem}")

    def _export(self) -> None:
        if not self._apply_output():
            return
        try:
            target, problems = self.controller.export_result()
        except Exception as exc:
            self.log.append(f"[失败] {exc}")
            return
        self.log.append(f"[完成] {target}")
        if problems:
            for problem in problems:
                self.log.append(f"[自检] {problem}")
        else:
            self.log.append("[自检] 行数 / 序号 / 符合情况文本 / 列宽 全部通过")
