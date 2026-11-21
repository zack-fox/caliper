"""⑤ 规则库：只读浏览控制项、判例与采集映射。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.controller import AppController, ControllerError
from app.widgets import Card, Chip, EmptyState, PageHeader, StatCard, hbox

ITEM_COLUMNS = ("序号", "编号", "安全控制点", "检查内容", "重要程度", "二值")


class RulesScreen(QWidget):
    def __init__(self, controller: AppController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setObjectName("page")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        self.header = PageHeader(
            "规则库",
            "规则包可整体替换：换一个 pack 目录即可换一套规则，框架与流程不变。",
        )
        reload_button = QPushButton("重新加载")
        reload_button.setObjectName("subtle")
        reload_button.clicked.connect(self.refresh)
        self.header.add_action(reload_button)
        layout.addWidget(self.header)

        self.stat_items = StatCard("控制项", "0", "当前等级")
        self.stat_binary = StatCard("二值项", "0", "禁部分符合")
        self.stat_cases = StatCard("高风险判例", "0")
        self.stat_guides = StatCard("作业指导书", "0")
        stat_row = QHBoxLayout()
        stat_row.setSpacing(12)
        for card in (self.stat_items, self.stat_binary, self.stat_cases, self.stat_guides):
            stat_row.addWidget(card, 1)
        layout.addLayout(stat_row)

        info_card = Card("规则包信息")
        self.pack_name = QLabel("—")
        self.pack_name.setObjectName("section_title")
        self.pack_meta = QLabel("—")
        self.pack_meta.setObjectName("mono")
        self.guides_row = QHBoxLayout()
        self.guides_row.setSpacing(6)
        self.guides_row.setAlignment(QHBoxLayout().alignment())
        info_card.add(self.pack_name)
        info_card.add(self.pack_meta)
        info_card.body.addLayout(self.guides_row)
        layout.addWidget(info_card)

        self.items_card = Card("控制项清单", "按当前项目等级过滤")
        self.table = QTableWidget(0, len(ITEM_COLUMNS))
        self.table.setHorizontalHeaderLabels(ITEM_COLUMNS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        self.items_card.add(self.table, 1)
        layout.addWidget(self.items_card, 1)

        self.empty = EmptyState("规则包不可用", "检查「导出与设置」里的规则包目录后重新加载。")
        self.empty.setVisible(False)
        layout.addWidget(self.empty)

        self.cases_card = Card("高风险判例", "公安部指引 16 条，命中后进入重大候选")
        self.cases_label = QLabel("—")
        self.cases_label.setObjectName("secondary")
        self.cases_label.setWordWrap(True)
        self.cases_card.add(self.cases_label)
        layout.addWidget(self.cases_card)

        self.refresh()

    # ---- 刷新 ----
    def refresh(self) -> None:
        try:
            pack = self.controller.load_pack()
            items = pack.items_for_level(self.controller.project.level)
        except ControllerError as exc:
            self.empty.set_text("规则包不可用", str(exc))
            self.empty.setVisible(True)
            self.items_card.setVisible(False)
            self.cases_card.setVisible(False)
            self.pack_name.setText("—")
            self.pack_meta.setText("—")
            return

        self.empty.setVisible(False)
        self.items_card.setVisible(True)
        self.cases_card.setVisible(True)

        self.pack_name.setText(f"{pack.meta.name} · {pack.meta.version}")
        self.pack_meta.setText(
            f"等级 {', '.join(str(level) for level in pack.meta.levels)} 级"
            f" · 系统 {', '.join(pack.meta.os_family)}"
            f" · 资产类型 {', '.join(pack.meta.asset_types)}"
        )
        while self.guides_row.count():
            widget = self.guides_row.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        for guide in pack.meta.guides:
            self.guides_row.addWidget(Chip(guide))
        self.guides_row.addStretch(1)

        self.table.setRowCount(0)
        binary = 0
        for item in items:
            row = self.table.rowCount()
            self.table.insertRow(row)
            if item.binary:
                binary += 1
            values = (
                str(item.seq),
                item.item_id,
                item.control_point,
                item.check_content,
                item.importance,
                "是" if item.binary else "否",
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setToolTip(value)
                self.table.setItem(row, column, cell)

        self.stat_items.set_value(str(len(items)), f"{self.controller.project.level} 级")
        self.stat_binary.set_value(str(binary))
        self.stat_cases.set_value(str(len(pack.high_risk)))
        self.stat_guides.set_value(str(len(pack.meta.guides)))

        lines = [
            f"{case.get('hr_id', '—')}  {case.get('问题简述', '')}"
            for case in pack.high_risk[:6]
        ]
        self.cases_label.setText("　·　".join(lines) if lines else "暂无判例")
