"""③ 问题与重大：汇总预览 + 人工确认重大判定原则。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.controller import AppController

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
        layout = QVBoxLayout(self)
        title = QLabel("问题与重大隐患")
        title.setObjectName("title")
        layout.addWidget(title)
        hint = QLabel(
            "列出所有「不符合 / 部分符合」的测评项，按测评项 × 资产类型汇总；"
            "勾选「符合重大判定原则」后，该问题才会进入重大安全隐患表。"
        )
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.table = QTableWidget(0, len(PREVIEW_COLUMNS))
        self.table.setHorizontalHeaderLabels(PREVIEW_COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemChanged.connect(self._toggle_major)
        layout.addWidget(self.table, 1)
        self.count = QLabel("")
        layout.addWidget(self.count)

    def refresh(self) -> None:
        self._loading = True
        self.table.setRowCount(0)
        rows = self.controller.issue_rows()
        if self.controller.run_result is None:
            self.count.setText("尚未运行判定")
            self._loading = False
            return
        confirmed = self.controller.confirmations()
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
                self.table.setItem(row, column, QTableWidgetItem(value))
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            check.setCheckState(
                Qt.Checked
                if (issue.item_id, issue.asset_type) in confirmed
                else Qt.Unchecked
            )
            check.setData(Qt.UserRole, (issue.item_id, issue.asset_type))
            self.table.setItem(row, len(values), check)
        self.count.setText(
            f"共 {len(rows)} 行待汇总，其中 {len(confirmed)} 行已确认重大判定原则"
        )
        self._loading = False

    def _toggle_major(self, item: QTableWidgetItem) -> None:
        if self._loading or item.column() != len(PREVIEW_COLUMNS) - 1:
            return
        key = item.data(Qt.UserRole)
        if not key:
            return
        self.controller.set_major_confirmed(*key, item.checkState() == Qt.Checked)
        self.count.setText(
            f"共 {self.table.rowCount()} 行待汇总，其中 "
            f"{len(self.controller.confirmations())} 行已确认重大判定原则"
        )
