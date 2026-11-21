"""④ 导出与设置：四张表独立导出 + 运行设置。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.controller import AppController
from app.widgets import Badge, Card, PageHeader, hbox

EXPORT_HINT = "逐项人工确认后方可导出结果表、问题表和重大隐患表；未确认内容只保留为工作草稿。"


class ExportScreen(QWidget):
    settings_changed = Signal()

    def __init__(self, controller: AppController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setObjectName("page")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        self.header = PageHeader("导出记录表", EXPORT_HINT)
        pick_dir = QPushButton("选择输出目录…")
        pick_dir.setObjectName("subtle")
        pick_dir.clicked.connect(self._pick_dir)
        self.header.add_action(pick_dir)
        layout.addWidget(self.header)

        # ---- 四张表 ----
        cards = QGridLayout()
        cards.setHorizontalSpacing(12)
        cards.setVerticalSpacing(12)
        self.status_asset = Badge("待导出", "neutral")
        self.status_result = Badge("待导出", "neutral")
        self.status_issue = Badge("待导出", "neutral")
        self.status_major = Badge("待导出", "neutral")
        self.asset_source = QLineEdit()
        self.asset_source.setPlaceholderText("选择人工维护的资产记录表（18 列）")
        pick_asset = QPushButton("选择…")
        pick_asset.setObjectName("subtle")
        pick_asset.clicked.connect(self._pick_asset)

        asset_card = self._export_card(
            "资产记录表",
            "读取人工维护的 18 列原表，只补空白字段并做自检。",
            "导出资产记录表",
            self._export_asset,
            self.status_asset,
        )
        asset_card.body.addLayout(hbox(self.asset_source, pick_asset))
        result_card = self._export_card(
            "结果记录表",
            "使用已确认并可编辑的记录内容，按设备 × 指导书生成工作表。",
            "导出结果记录表",
            self._export,
            self.status_result,
        )
        issue_card = self._export_card(
            "安全问题汇总",
            "取不符合 / 部分符合项，导出 25 列冻结顺序。",
            "导出问题汇总",
            self._export_issue,
            self.status_issue,
        )
        major_card = self._export_card(
            "重大安全隐患",
            "只收已确认「符合重大判定原则」的行，19 列。",
            "导出重大隐患表",
            self._export_major,
            self.status_major,
        )
        for index, card in enumerate((asset_card, result_card, issue_card, major_card)):
            cards.addWidget(card, index // 2, index % 2)
        cards.setColumnStretch(0, 1)
        cards.setColumnStretch(1, 1)
        layout.addLayout(cards)

        # ---- 设置 ----
        settings_card = Card("运行设置", "相对路径按项目文件所在目录解析")
        self.output_dir = QLineEdit()
        self.evidence_root = QLineEdit()
        self.pack_dir = QLineEdit()
        settings_card.body.addLayout(
            self._path_row("输出目录", self.output_dir, self._pick_dir)
        )
        settings_card.body.addLayout(
            self._path_row("证据根目录", self.evidence_root, self._pick_evidence)
        )
        settings_card.body.addLayout(
            self._path_row("规则包目录", self.pack_dir, self._pick_pack)
        )
        save_settings = QPushButton("保存设置")
        save_settings.setObjectName("primary")
        save_settings.clicked.connect(self._save_settings)
        settings_card.add_action(save_settings)
        layout.addWidget(settings_card)

        # ---- 日志 ----
        log_card = Card("导出日志", "每次导出都会记录路径与自检结果")
        self.log = QTextEdit()
        self.log.setObjectName("log")
        self.log.setReadOnly(True)
        log_card.add(self.log, 1)
        clear = QPushButton("清空")
        clear.setObjectName("subtle")
        clear.clicked.connect(self.log.clear)
        log_card.add_action(clear)
        layout.addWidget(log_card, 1)

        self.refresh()

    # ---- 构建 ----
    def _export_card(self, title: str, desc: str, button_text: str, handler, badge: Badge) -> Card:
        card = Card(title)
        badge_row = QHBoxLayout()
        badge_row.addWidget(badge)
        badge_row.addStretch(1)
        card.body.addLayout(badge_row)
        hint = QLabel(desc)
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        card.add(hint)
        button = QPushButton(button_text)
        button.clicked.connect(handler)
        card.add_action(button)
        return card

    def _path_row(self, caption: str, field: QLineEdit, handler) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        label = QLabel(caption)
        label.setObjectName("secondary")
        label.setFixedWidth(84)
        browse = QPushButton("选择…")
        browse.setObjectName("subtle")
        browse.clicked.connect(handler)
        row.addWidget(label)
        row.addWidget(field, 1)
        row.addWidget(browse)
        return row

    # ---- 刷新 ----
    def refresh(self) -> None:
        project = self.controller.project
        self.output_dir.setText(str(self.controller.export_dir()))
        self.evidence_root.setText(str(project.evidence_root))
        self.pack_dir.setText(str(project.pack_dir or ""))
        has_run = self.controller.run_result is not None
        pending = self.controller.pending_review_records() if has_run else []
        if not has_run:
            self.status_result.set_text("待核查", "neutral")
        elif pending:
            self.status_result.set_text(f"待确认 {len(pending)}", "warn")
        else:
            self.status_result.set_text("可导出", "ok")
        rows = len(self.controller.issue_rows()) if has_run else 0
        confirmed = len(self.controller.confirmations()) if has_run else 0
        if not has_run:
            self.status_issue.set_text("待核查", "neutral")
            self.status_major.set_text("待核查", "neutral")
        elif pending:
            self.status_issue.set_text(f"待复核 {len(pending)}", "warn")
            self.status_major.set_text("待记录复核", "warn")
        else:
            self.status_issue.set_text(f"{rows} 行可导出", "info" if rows else "neutral")
            self.status_major.set_text(
                f"已确认 {confirmed} 行" if confirmed else "无重大确认行",
                "info" if confirmed else "neutral",
            )

    # ---- 选择 ----
    def _pick_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择输出目录", self.output_dir.text() or "")
        if path:
            self.output_dir.setText(path)

    def _pick_evidence(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择证据根目录", self.evidence_root.text() or "")
        if path:
            self.evidence_root.setText(path)

    def _pick_pack(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择规则包目录", self.pack_dir.text() or "")
        if path:
            self.pack_dir.setText(path)

    def _pick_asset(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择资产记录表", "", "Excel 文件 (*.xlsx)"
        )
        if path:
            self.asset_source.setText(path)

    # ---- 设置 ----
    def _save_settings(self) -> None:
        data = self.controller.project.model_dump()
        data.update(
            {
                "output_dir": self.output_dir.text().strip() or self.controller.project.output_dir,
                "evidence_root": self.evidence_root.text().strip()
                or self.controller.project.evidence_root,
                "pack_dir": self.pack_dir.text().strip() or self.controller.project.pack_dir,
            }
        )
        try:
            self.controller.project = self.controller.project.model_validate(data)
        except Exception as exc:
            self.log.append(f"[失败] 设置不合法：{exc}")
            return
        self.refresh()
        self.settings_changed.emit()
        self.log.append("[完成] 运行设置已更新")

    def _apply_output(self) -> bool:
        if not self.output_dir.text().strip():
            self.log.append("请先选择输出目录")
            return False
        self.controller.project = self.controller.project.model_copy(
            update={"output_dir": Path(self.output_dir.text().strip())}
        )
        return True

    def _mark(self, badge: Badge, text: str, tone: str) -> None:
        badge.set_text(text, tone)

    # ---- 导出动作 ----
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
            self._mark(self.status_asset, "失败", "bad")
            return
        for warning in warnings:
            self.log.append(f"[提示] {warning}")
        if errors:
            for error in errors:
                self.log.append(f"[失败] {error}")
            self._mark(self.status_asset, "有错误", "bad")
            return
        self.log.append(f"[完成] {target}")
        self.log.append("[自检] 必填 / IP / 作业指导书 全部通过")
        self._mark(self.status_asset, "已完成", "ok")

    def _export_issue(self) -> None:
        if not self._apply_output():
            return
        try:
            target, problems = self.controller.export_issue()
        except Exception as exc:
            self.log.append(f"[失败] {exc}")
            self._mark(self.status_issue, "失败", "bad")
            return
        self.log.append(f"[完成] {target}")
        for problem in problems:
            self.log.append(f"[自检失败] {problem}")
        self._mark(self.status_issue, "已完成" if not problems else "有告警", "ok" if not problems else "warn")

    def _export_major(self) -> None:
        if not self._apply_output():
            return
        try:
            target, problems = self.controller.export_major()
        except Exception as exc:
            self.log.append(f"[失败] {exc}")
            self._mark(self.status_major, "失败", "bad")
            return
        self.log.append(f"[完成] {target}")
        for problem in problems:
            self.log.append(f"[自检失败] {problem}")
        self._mark(self.status_major, "已完成" if not problems else "有告警", "ok" if not problems else "warn")

    def _export(self) -> None:
        if not self._apply_output():
            return
        try:
            target, problems = self.controller.export_result()
        except Exception as exc:
            self.log.append(f"[失败] {exc}")
            self._mark(self.status_result, "失败", "bad")
            return
        self.log.append(f"[完成] {target}")
        if problems:
            for problem in problems:
                self.log.append(f"[自检] {problem}")
            self._mark(self.status_result, "有告警", "warn")
        else:
            self.log.append("[自检] 行数 / 序号 / 符合情况文本 / 列宽 全部通过")
            self._mark(self.status_result, "已完成", "ok")
