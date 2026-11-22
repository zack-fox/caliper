"""③ 问题与重大：不符合/部分符合汇总，人工确认重大安全隐患。"""

from __future__ import annotations

from PySide6.QtCore import Qt
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

PREVIEW_COLUMNS = (
    "问题编号",
    "资产类型",
    "关联资产",
    "安全控制点",
    "测评项",
    "问题概述",
    "高风险降风险",
    "重大隐患评分",
    "确认状态",
)


class IssuesScreen(QWidget):
    def __init__(self, controller: AppController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._loading = False
        self.setObjectName("page")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        self.header = PageHeader(
            "问题与重大",
            "自动归集的不符合 / 部分符合项仅作问题草稿；记录人工复核后，勾选的重大隐患才可导出。",
        )
        refresh_button = QPushButton("刷新")
        refresh_button.setObjectName("subtle")
        refresh_button.clicked.connect(self.refresh)
        self.header.add_action(refresh_button)
        layout.addWidget(self.header)

        self.stat_total = StatCard("问题总数", "0", "待汇总行数")
        self.stat_confirmed = StatCard("已确认重大", "0", "将进入 19 列表")
        self.stat_pending = StatCard("待确认", "0", "需人工判断")
        self.stat_assets = StatCard("涉及资产", "0", "问题覆盖的设备")
        stat_row = QHBoxLayout()
        stat_row.setSpacing(12)
        for card in (self.stat_total, self.stat_confirmed, self.stat_pending, self.stat_assets):
            stat_row.addWidget(card, 1)
        layout.addLayout(stat_row)

        card = Card("安全问题汇总", "预览列；导出为 25 列冻结顺序")
        self.table = QTableWidget(0, len(PREVIEW_COLUMNS))
        self.table.setHorizontalHeaderLabels(PREVIEW_COLUMNS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(5, QHeaderView.Stretch)
        for column, width in (
            (0, 62),
            (1, 74),
            (2, 100),
            (3, 84),
            (4, 116),
            (6, 286),
            (7, 248),
            (8, 152),
        ):
            self.table.setColumnWidth(column, width)

        self.empty = EmptyState(
            "尚未运行核查",
            "先在「证据与资产」页导入设备证据并开始核查，问题清单会自动生成。",
        )
        self.stack = QStackedWidget()
        self.stack.addWidget(self.table)
        self.stack.addWidget(self.empty)
        card.add(self.stack, 1)

        self.count = QLabel("尚未运行核查")
        self.count.setObjectName("muted")
        card.add(self.count)
        layout.addWidget(card, 1)

        self.refresh()

    def refresh(self) -> None:
        self._loading = True
        self.table.setRowCount(0)
        rows = self.controller.issue_rows()
        if self.controller.run_result is None:
            self.stack.setCurrentWidget(self.empty)
            self.count.setText("尚未运行核查：先在「证据与资产」页导入证据并开始核查")
            self._set_stats(0, 0, 0, 0)
            self._loading = False
            return

        self.stack.setCurrentWidget(self.table)
        reviews = self._reviews()
        assets: set[str] = set()
        for issue in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            review = reviews.get((issue.item_id, issue.asset_type))
            values = (
                issue.issue_no,
                issue.asset_type,
                issue.values["关联资产"],
                issue.values["安全控制点"],
                issue.values["测评项"],
                issue.values["问题概述"],
                self._risk_text(review),
                self._score_text(review),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(
                    self._risk_tip(review) if column == 6 else value
                )
                self.table.setItem(row, column, item)
            assets.add(issue.values["关联资产"])
            self.table.setCellWidget(
                row, len(PREVIEW_COLUMNS) - 1, self._review_cell(issue, review)
            )

        self.table.resizeRowsToContents()
        confirmed = sum(1 for review in reviews.values() if review.confirmed)
        pending = sum(1 for review in reviews.values() if not review.confirmed)
        self._set_stats(len(rows), confirmed, len(assets), pending)
        self.count.setText(
            f"共 {len(rows)} 行待汇总，其中 {confirmed} 行重大确认有效，"
            f"{pending} 行待确认或已失效"
        )
        self._loading = False

    def _reviews(self) -> dict[tuple[str, str], MajorReview]:
        try:
            return self.controller.major_reviews()
        except ControllerError as exc:
            self.count.setText(f"重大隐患规则上下文不可用：{exc}")
            return {}

    def _risk_text(self, review: MajorReview | None) -> str:
        if review is None:
            return "无高风险命中"
        if not review.reducible:
            return "可降风险：否"
        basis = "；".join(review.reduction_basis) or "未填写前提"
        first = basis.split("；")[0]
        if len(first) > 46:
            first = f"{first[:46]}…"
        extra = f"（共 {len(review.reduction_basis)} 项前提）" if len(review.reduction_basis) > 1 else ""
        return f"可降风险：是{extra}\n前提：{first}"

    def _risk_tip(self, review: MajorReview | None) -> str:
        if review is None:
            return "无高风险命中"
        if not review.reducible:
            return "可降风险：否"
        basis = "；".join(review.reduction_basis) or "未填写前提"
        return f"可降风险：是\n前提：{basis}"

    def _score_text(self, review: MajorReview | None) -> str:
        if review is None:
            return "—"
        if not review.scores:
            return "未命中重大隐患规则"
        dimensions = " · ".join(f"{name} {score}" for name, score in review.scores)
        state = "候选" if review.is_candidate else "未达阈值"
        return (
            f"{dimensions}\n总分 {review.total:.2f} / 阈值 {review.threshold:.2f}"
            f"（{state}）"
        )

    def _review_cell(self, issue, review: MajorReview | None) -> QWidget:
        host = QWidget()
        layout = QHBoxLayout(host)
        layout.setContentsMargins(8, 3, 8, 3)
        layout.setSpacing(6)
        if review is None:
            layout.addWidget(Badge("无高风险", "neutral"))
            layout.addStretch(1)
            return host

        if review.confirmed:
            badge = Badge("已确认", "ok")
            badge.setToolTip("规则版本与判定依据指纹一致")
        elif review.reason == "未确认":
            badge = Badge("待确认", "warn")
            badge.setToolTip("尚未完成人工确认")
        else:
            badge = Badge("已失效", "bad")
            badge.setToolTip(review.reason)
        layout.addWidget(badge)

        button = QPushButton(
            "撤销"
            if review.confirmed
            else "重新确认"
            if review.reason and review.reason != "未确认"
            else "确认"
        )
        button.setObjectName("subtle")
        button.clicked.connect(
            lambda _checked=False, item=issue, reviewed=review: self._confirm(
                item, reviewed
            )
        )
        layout.addWidget(button)
        layout.addStretch(1)
        return host

    def _confirm(self, issue, review: MajorReview) -> None:
        try:
            self.controller.set_major_confirmed(
                issue.item_id, issue.asset_type, not review.confirmed
            )
        except ControllerError as exc:
            QMessageBox.warning(self, "未能确认重大隐患", str(exc))
            return
        self.refresh()

    def _set_stats(self, total: int, confirmed: int, assets: int, pending: int) -> None:
        self.stat_total.set_value(str(total))
        self.stat_confirmed.set_value(str(confirmed))
        self.stat_pending.set_value(str(pending))
        self.stat_assets.set_value(str(assets))
