"""⑤ 风险与结论：高风险候选、三维评分与重大隐患确认。

拆分自「问题与重大」页：本页只负责重大隐患的评分展示与确认/撤销，
问题清单与整改建议仍留在「问题与整改」页。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.controller import AppController, ControllerError, MajorReview
from app.widgets import Badge, Card, EmptyState, PageHeader, StatCard

RISK_COLUMNS = (
    "问题编号",
    "资产类型",
    "安全控制点",
    "问题概述",
    "可降风险",
    "三维得分",
    "加权总分",
    "确认状态",
)


class RiskScreen(QWidget):
    navigate = Signal(str)

    def __init__(self, controller: AppController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._rows: list[tuple] = []
        self._reviews: dict[tuple[str, str], MajorReview] = {}
        self.setObjectName("page")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        self.header = PageHeader(
            "风险与结论",
            "独立确认高风险候选与重大隐患；未确认或已失效的候选会阻断导出。",
        )
        refresh_button = QPushButton("刷新")
        refresh_button.setObjectName("subtle")
        refresh_button.clicked.connect(self.refresh)
        self.header.add_action(refresh_button)
        layout.addWidget(self.header)

        self.stat_high = StatCard("高风险候选", "0", "命中高风险规则")
        self.stat_major = StatCard("重大候选", "0", "加权总分达阈值")
        self.stat_confirmed = StatCard("已确认", "0", "版本与指纹一致")
        stat_row = QHBoxLayout()
        stat_row.setSpacing(12)
        for card in (self.stat_high, self.stat_major, self.stat_confirmed):
            stat_row.addWidget(card, 1)
        layout.addLayout(stat_row)

        body = QHBoxLayout()
        body.setSpacing(12)

        table_card = Card("重大隐患候选", "按加权总分排序；选中行在右侧查看明细并确认")
        self.table = QTableWidget(0, len(RISK_COLUMNS))
        self.table.setHorizontalHeaderLabels(RISK_COLUMNS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setMinimumSectionSize(56)
        for column, width in (
            (0, 56),
            (1, 64),
            (2, 88),
            (3, 170),
            (4, 120),
            (5, 160),
            (6, 110),
            (7, 100),
        ):
            self.table.setColumnWidth(column, width)

        self.empty = EmptyState(
            "尚未生成核查结果",
            "完成现场核查后，这里会列出高风险候选、三维评分与重大隐患确认状态。",
        )
        self.stack = QStackedWidget()
        self.stack.addWidget(self.table)
        self.stack.addWidget(self.empty)
        table_card.add(self.stack, 1)

        batch_row = QHBoxLayout()
        batch_row.setSpacing(6)
        batch_hint = QLabel("多选后可批量处理：")
        batch_hint.setObjectName("muted")
        batch_row.addWidget(batch_hint)
        self.batch_confirm_button = QPushButton("确认选中")
        self.batch_confirm_button.setObjectName("subtle")
        self.batch_confirm_button.clicked.connect(lambda: self._batch_confirm(True))
        self.batch_undo_button = QPushButton("撤销选中")
        self.batch_undo_button.setObjectName("subtle")
        self.batch_undo_button.clicked.connect(lambda: self._batch_confirm(False))
        batch_row.addWidget(self.batch_confirm_button)
        batch_row.addWidget(self.batch_undo_button)
        batch_row.addStretch(1)
        table_card.body.addLayout(batch_row)

        self.count = QLabel("尚未生成核查结果")
        self.count.setObjectName("muted")
        table_card.add(self.count)
        body.addWidget(table_card, 1)

        body.addWidget(self._build_detail())
        layout.addLayout(body, 1)

        self.refresh()

    def _build_detail(self) -> Card:
        card = Card("确认明细", "选择左侧候选查看三维评分与确认状态")
        card.setFixedWidth(340)
        self.detail_empty = EmptyState("未选择候选", "在左侧表格选择一行后，这里显示评分明细与确认操作。")
        self.detail_form = QWidget()
        form = QVBoxLayout(self.detail_form)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(8)

        self.detail_title = QLabel("—")
        self.detail_title.setObjectName("section_title")
        self.detail_title.setWordWrap(True)
        form.addWidget(self.detail_title)

        self.detail_meta = QLabel("")
        self.detail_meta.setObjectName("muted")
        self.detail_meta.setWordWrap(True)
        form.addWidget(self.detail_meta)

        self.score_label = QLabel("")
        self.score_label.setWordWrap(True)
        form.addWidget(self.score_label)

        self.total_label = QLabel("")
        self.total_label.setObjectName("reading_text")
        self.total_label.setWordWrap(True)
        form.addWidget(self.total_label)

        self.reducible_label = QLabel("")
        self.reducible_label.setWordWrap(True)
        form.addWidget(self.reducible_label)

        self.rule_label = QLabel("")
        self.rule_label.setObjectName("muted")
        self.rule_label.setWordWrap(True)
        form.addWidget(self.rule_label)

        self.version_label = QLabel("")
        self.version_label.setObjectName("muted")
        self.version_label.setWordWrap(True)
        form.addWidget(self.version_label)

        self.status_badge = Badge("—", "neutral")
        form.addWidget(self.status_badge, 0, Qt.AlignLeft)

        self.reason_label = QLabel("")
        self.reason_label.setObjectName("muted")
        self.reason_label.setWordWrap(True)
        form.addWidget(self.reason_label)

        self.confirm_button = QPushButton("确认重大隐患")
        self.confirm_button.setObjectName("primary")
        self.confirm_button.clicked.connect(self._confirm_selected)
        form.addWidget(self.confirm_button)

        self.gate_label = QLabel("")
        self.gate_label.setObjectName("muted")
        self.gate_label.setWordWrap(True)
        form.addWidget(self.gate_label)

        self.go_export_button = QPushButton("前往导出")
        self.go_export_button.setObjectName("subtle")
        self.go_export_button.clicked.connect(lambda: self.navigate.emit("export"))
        form.addWidget(self.go_export_button)
        form.addStretch(1)

        self.detail_stack = QStackedWidget()
        self.detail_stack.addWidget(self.detail_empty)
        self.detail_stack.addWidget(self.detail_form)
        card.add(self.detail_stack, 1)
        return card

    # ------------------------------------------------------------------ 数据
    def _issue_map(self) -> dict[tuple[str, str], object]:
        return {
            (issue.item_id, issue.asset_type): issue
            for issue in self.controller.issue_rows()
        }

    def refresh(self) -> None:
        self.table.setRowCount(0)
        self._rows = []
        self._reviews = {}
        self._show_detail(None)
        if self.controller.run_result is None:
            self.stack.setCurrentWidget(self.empty)
            self.count.setText("尚未生成核查结果：先在「证据与资产」页导入证据并运行核查")
            self._set_stats(0, 0, 0)
            return

        try:
            reviews = self.controller.major_reviews()
        except ControllerError as exc:
            self.empty.set_text("风险统计暂不可用", str(exc))
            self.stack.setCurrentWidget(self.empty)
            self.count.setText(f"风险统计暂不可用：{exc}")
            self._set_stats(0, 0, 0)
            return

        self._reviews = reviews
        issues = self._issue_map()
        ordered = sorted(
            reviews.items(),
            key=lambda pair: (-pair[1].is_candidate, -pair[1].total, pair[0][0]),
        )
        for (item_id, asset_type), review in ordered:
            issue = issues.get((item_id, asset_type))
            self._rows.append((issue, review))
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = (
                issue.issue_no if issue else item_id,
                asset_type,
                issue.values.get("安全控制点", "") if issue else "",
                issue.values.get("问题概述", "") if issue else "",
                self._reducible_text(review),
                self._score_text(review),
                f"{review.total:.2f} / {review.threshold:.2f}",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(self._score_tip(review) if column == 5 else value)
                self.table.setItem(row, column, item)
            self.table.setCellWidget(row, len(RISK_COLUMNS) - 1, self._status_cell(review))

        if self._rows:
            self.stack.setCurrentWidget(self.table)
        else:
            self.empty.set_text(
                "无高风险候选",
                "当前批次没有命中高风险规则；仍可在「问题与整改」页查看全部问题。",
            )
            self.stack.setCurrentWidget(self.empty)

        high = len(reviews)
        major = sum(1 for review in reviews.values() if review.is_candidate)
        confirmed = sum(1 for review in reviews.values() if review.confirmed)
        self._set_stats(high, major, confirmed)
        self.count.setText(
            f"共 {high} 条高风险候选，其中 {major} 条达到重大隐患阈值，"
            f"{confirmed} 条已确认有效"
        )

    def _set_stats(self, high: int, major: int, confirmed: int) -> None:
        self.stat_high.set_value(str(high))
        self.stat_major.set_value(str(major))
        self.stat_confirmed.set_value(str(confirmed))

    # ------------------------------------------------------------------ 文案
    @staticmethod
    def _reducible_text(review: MajorReview) -> str:
        if not review.reducible:
            return "可降风险：否"
        basis = "；".join(review.reduction_basis) or "未填写前提"
        return f"可降风险：是\n前提：{basis}"

    @staticmethod
    def _score_text(review: MajorReview) -> str:
        if not review.scores:
            return "未命中重大隐患规则"
        return " · ".join(f"{name} {score}" for name, score in review.scores)

    @staticmethod
    def _score_tip(review: MajorReview) -> str:
        lines = [f"{name} {score}" for name, score in review.scores]
        lines.append(f"加权总分 {review.total:.2f} / 阈值 {review.threshold:.2f}")
        lines.append("候选" if review.is_candidate else "未达阈值")
        return "\n".join(lines)

    @staticmethod
    def _status_cell(review: MajorReview) -> QWidget:
        host = QWidget()
        layout = QHBoxLayout(host)
        layout.setContentsMargins(8, 3, 8, 3)
        layout.setSpacing(6)
        if review.confirmed:
            badge = Badge("已确认", "ok")
            badge.setToolTip("规则版本与判定依据指纹一致")
        elif review.reason == "未确认":
            badge = Badge("待确认", "warn")
        else:
            badge = Badge("已失效", "bad")
            badge.setToolTip(review.reason)
        layout.addWidget(badge)
        layout.addStretch(1)
        return host

    # ------------------------------------------------------------------ 明细
    def _on_selection_changed(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._rows):
            self._show_detail(None)
            return
        issue, review = self._rows[row]
        self._show_detail((issue, review))

    def _show_detail(self, pair) -> None:
        if pair is None:
            self.detail_stack.setCurrentWidget(self.detail_empty)
            return
        issue, review = pair
        self.detail_stack.setCurrentWidget(self.detail_form)
        title = issue.issue_no if issue else "—"
        self.detail_title.setText(f"{title}　{review.threshold and '重大隐患候选' or '高风险'}")
        self.detail_meta.setText(
            "　·　".join(
                part
                for part in (
                    issue.values.get("安全控制点", "") if issue else "",
                    issue.asset_type if issue else "",
                )
                if part
            )
        )
        dimensions = "　".join(f"{name} {score}" for name, score in review.scores)
        self.score_label.setText(f"三维得分：{dimensions or '—'}")
        self.total_label.setText(
            f"加权总分 {review.total:.2f} / 阈值 {review.threshold:.2f} "
            f"（{'候选' if review.is_candidate else '未达阈值'}）"
        )
        if review.reducible:
            self.reducible_label.setText(
                "可降风险：是\n前提：" + ("；".join(review.reduction_basis) or "未填写")
            )
        else:
            self.reducible_label.setText("可降风险：否")
        self.rule_label.setText("规则：" + "、".join(review.rule_ids) if review.rule_ids else "规则：—")
        try:
            version = self.controller.major_rule_version()
        except ControllerError:
            version = "—"
        self.version_label.setText(f"规则版本：{version}　·　判定依据：运行批次指纹")

        if review.confirmed:
            self.status_badge.set_text("已确认", "ok")
            self.reason_label.setText("规则版本与判定依据指纹一致。")
            self.gate_label.setText("")
            self.go_export_button.setVisible(True)
        elif review.reason == "未确认":
            self.status_badge.set_text("待确认", "warn")
            self.reason_label.setText("尚未完成人工确认。")
            self.gate_label.setText("导出阻断：未确认的重大隐患候选会阻断导出。")
            self.go_export_button.setVisible(True)
        else:
            self.status_badge.set_text("已失效", "bad")
            self.reason_label.setText(f"失效原因：{review.reason}")
            self.gate_label.setText("导出阻断：确认已失效，需重新确认后放行。")
            self.go_export_button.setVisible(True)
        self.confirm_button.setText("撤销确认" if review.confirmed else "确认重大隐患")
        self._current_review = review
        self._current_issue = issue

    def _batch_confirm(self, confirmed: bool) -> None:
        selected = sorted(
            index.row() for index in self.table.selectionModel().selectedRows()
        )
        targets = [
            self._rows[row]
            for row in selected
            if 0 <= row < len(self._rows)
            and self._rows[row][0] is not None
            and self._rows[row][1].confirmed != confirmed
        ]
        if not targets:
            QMessageBox.information(
                self,
                "没有可处理项",
                "请先多选候选；已处于目标状态的行会被跳过。",
            )
            return
        action = "确认" if confirmed else "撤销"
        if (
            QMessageBox.question(
                self,
                f"批量{action}",
                f"确定对选中的 {len(targets)} 条候选执行「{action}」？",
            )
            != QMessageBox.Yes
        ):
            return
        failed = []
        for issue, _review in targets:
            try:
                self.controller.set_major_confirmed(
                    issue.item_id, issue.asset_type, confirmed
                )
            except ControllerError as exc:
                failed.append(str(exc))
        self.refresh()
        if failed:
            QMessageBox.warning(self, "部分候选未处理", "\n".join(failed))

    def _confirm_selected(self) -> None:
        if not getattr(self, "_current_review", None) or not getattr(self, "_current_issue", None):
            return
        issue, review = self._current_issue, self._current_review
        try:
            self.controller.set_major_confirmed(
                issue.item_id, issue.asset_type, not review.confirmed
            )
        except ControllerError as exc:
            QMessageBox.warning(self, "未能确认重大隐患", str(exc))
            return
        self.refresh()
