"""③ 问题与重大：不符合/部分符合汇总，人工确认重大安全隐患。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.controller import AppController
from app.widgets import Card, EmptyState, PageHeader, StatCard, hbox

PREVIEW_COLUMNS = (
    "问题编号",
    "资产类型",
    "关联资产",
    "安全控制点",
    "测评项",
    "问题概述",
    "符合重大判定原则",
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
            "所有「不符合 / 部分符合」项按测评项 × 资产类型汇总；勾选后才会进入重大安全隐患表。",
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
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(len(PREVIEW_COLUMNS) - 1, QHeaderView.ResizeToContents)
        self.table.itemChanged.connect(self._toggle_major)

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
            self._set_stats(0, 0, 0)
            self._loading = False
            return

        self.stack.setCurrentWidget(self.table)
        confirmed = self.controller.confirmations()
        assets: set[str] = set()
        for issue in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = (
                issue.issue_no,
                issue.asset_type,
                issue.values["关联资产"],
                issue.values["安全控制点"],
                issue.values["测评项"],
                issue.values["问题概述"],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.table.setItem(row, column, item)
            assets.add(issue.values["关联资产"])
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            check.setCheckState(
                Qt.Checked
                if (issue.item_id, issue.asset_type) in confirmed
                else Qt.Unchecked
            )
            check.setData(Qt.UserRole, (issue.item_id, issue.asset_type))
            self.table.setItem(row, len(values), check)

        self._set_stats(len(rows), len(confirmed), len(assets))
        self.count.setText(
            f"共 {len(rows)} 行待汇总，其中 {len(confirmed)} 行已确认符合重大判定原则"
        )
        self._loading = False

    def _set_stats(self, total: int, confirmed: int, assets: int) -> None:
        self.stat_total.set_value(str(total))
        self.stat_confirmed.set_value(str(confirmed))
        self.stat_pending.set_value(str(max(total - confirmed, 0)))
        self.stat_assets.set_value(str(assets))

    def _toggle_major(self, item: QTableWidgetItem) -> None:
        if self._loading or item.column() != len(PREVIEW_COLUMNS) - 1:
            return
        key = item.data(Qt.UserRole)
        if not key:
            return
        self.controller.set_major_confirmed(*key, item.checkState() == Qt.Checked)
        confirmed = len(self.controller.confirmations())
        self._set_stats(self.table.rowCount(), confirmed, int(self.stat_assets.value_label.text() or 0))
        self.count.setText(
            f"共 {self.table.rowCount()} 行待汇总，其中 {confirmed} 行已确认符合重大判定原则"
        )
