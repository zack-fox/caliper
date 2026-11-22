"""③ 问题与整改：不符合/部分符合汇总，左侧清单 + 右侧详情，重大确认入口跳转风险页。"""

from __future__ import annotations

import html

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.controller import AppController, ControllerError, MajorReview
from app.widgets import (
    Badge,
    Card,
    EmptyState,
    FilterChip,
    PageHeader,
    StatCard,
    scrollable,
)

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

REMEDIATION_COLUMNS = (
    "问题编号",
    "资产类型",
    "安全控制点",
    "问题概述",
    "危害分析",
    "整改建议",
    "整改状态",
)

ALL_ASSETS = "全部资产类型"
ALL_POINTS = "全部控制点"
ALL_PRIORITIES = "全部优先级"
PRIORITIES = (ALL_PRIORITIES, "高风险命中", "重大候选", "已确认")
DETAIL_MIN_WIDTH = 320


class IssuesScreen(QWidget):
    navigate = Signal(str)

    def __init__(self, controller: AppController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._loading = True
        self._issues = []
        self._filtered = []
        self._reviews_cache: dict[tuple[str, str], MajorReview] = {}
        self.setObjectName("page")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        self.header = PageHeader(
            "问题与整改",
            "自动归集的不符合 / 部分符合项仅作问题草稿；记录人工复核后，勾选的重大隐患才可导出。",
        )
        risk_button = QPushButton("前往风险页")
        risk_button.setObjectName("subtle")
        risk_button.clicked.connect(lambda: self.navigate.emit("risk"))
        self.header.add_action(risk_button)
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

        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索问题编号 / 控制点 / 测评项 / 资产 / 问题概述")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filters)
        self.asset_filter = QComboBox()
        self.asset_filter.addItem(ALL_ASSETS)
        self.asset_filter.currentIndexChanged.connect(self._apply_filters)
        self.point_filter = QComboBox()
        self.point_filter.addItem(ALL_POINTS)
        self.point_filter.currentIndexChanged.connect(self._apply_filters)
        self.priority_filter = QComboBox()
        self.priority_filter.addItems(PRIORITIES)
        self.priority_filter.currentIndexChanged.connect(self._apply_filters)
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        filter_row.addWidget(self.search, 1)
        for combo, width in (
            (self.asset_filter, 150),
            (self.point_filter, 190),
            (self.priority_filter, 140),
        ):
            combo.setMinimumWidth(width)
            filter_row.addWidget(combo)
        layout.addLayout(filter_row)

        view_row = QHBoxLayout()
        view_row.setSpacing(6)
        self._view = "issues"
        self.issue_view_chip = FilterChip("问题清单", "issues")
        self.remediation_view_chip = FilterChip("整改建议", "remediation")
        self.issue_view_chip.setChecked(True)
        self.issue_view_chip.clicked.connect(lambda _c=False: self._switch_view("issues"))
        self.remediation_view_chip.clicked.connect(
            lambda _c=False: self._switch_view("remediation")
        )
        view_row.addWidget(self.issue_view_chip)
        view_row.addWidget(self.remediation_view_chip)
        view_row.addStretch(1)
        layout.addLayout(view_row)

        card = Card("安全问题汇总", "问题清单为 25 列冻结顺序预览；整改建议聚焦危害与整改动作")
        self.table = QTableWidget(0, len(PREVIEW_COLUMNS))
        self.table.setHorizontalHeaderLabels(PREVIEW_COLUMNS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(5, QHeaderView.Stretch)
        for column, width in (
            (0, 52),
            (1, 64),
            (2, 110),
            (3, 88),
            (4, 120),
            (6, 120),
            (7, 110),
            (8, 110),
        ):
            self.table.setColumnWidth(column, width)
        self.table.itemSelectionChanged.connect(
            lambda: self._on_selection(self.table)
        )

        self.remediation_table = QTableWidget(0, len(REMEDIATION_COLUMNS))
        self.remediation_table.setHorizontalHeaderLabels(REMEDIATION_COLUMNS)
        self.remediation_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.remediation_table.setAlternatingRowColors(True)
        self.remediation_table.setWordWrap(False)
        self.remediation_table.setShowGrid(False)
        self.remediation_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.remediation_table.verticalHeader().setVisible(False)
        self.remediation_table.verticalHeader().setDefaultSectionSize(34)
        remediation_header = self.remediation_table.horizontalHeader()
        remediation_header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        remediation_header.setSectionResizeMode(QHeaderView.Interactive)
        remediation_header.setSectionResizeMode(3, QHeaderView.Stretch)
        remediation_header.setSectionResizeMode(5, QHeaderView.Stretch)
        for column, width in ((0, 62), (1, 74), (2, 84), (6, 90)):
            self.remediation_table.setColumnWidth(column, width)
        self.remediation_table.itemSelectionChanged.connect(
            lambda: self._on_selection(self.remediation_table)
        )

        self.empty = EmptyState(
            "尚未运行核查",
            "先在「材料与资产」页导入设备证据并开始核查，问题清单会自动生成。",
        )
        self.stack = QStackedWidget()
        self.stack.addWidget(self.table)
        self.stack.addWidget(self.remediation_table)
        self.stack.addWidget(self.empty)
        card.add(self.stack, 1)

        self.count = QLabel("尚未运行核查")
        self.count.setObjectName("muted")
        card.add(self.count)

        self.detail_card = Card("问题详情", "选中左侧行查看完整问题、危害与整改动作")
        self.detail = QLabel("选择左侧一行查看详情。")
        self.detail.setTextFormat(Qt.RichText)
        self.detail.setWordWrap(True)
        self.detail.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.detail.setMinimumWidth(DETAIL_MIN_WIDTH)
        self.detail_card.add(scrollable(self.detail), 1)
        self.detail_card.setMinimumWidth(DETAIL_MIN_WIDTH)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(card)
        splitter.addWidget(self.detail_card)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([920, 380])
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, 1)

        self._loading = False
        self.refresh()

    # ---- 数据刷新 ----
    def refresh(self) -> None:
        self._loading = True
        rows = self.controller.issue_rows()
        if self.controller.run_result is None:
            self._issues = []
            self._filtered = []
            self.table.setRowCount(0)
            self.remediation_table.setRowCount(0)
            self.stack.setCurrentWidget(self.empty)
            self.count.setText("尚未运行核查：先在「材料与资产」页导入证据并开始核查")
            self.detail.setText("<p>尚未运行核查，暂无问题详情。</p>")
            self._set_stats(0, 0, 0, 0)
            self._loading = False
            return

        self._reviews_cache = self._reviews()
        self._issues = rows
        self._sync_filter_options(rows)
        self._loading = False
        self._apply_filters()

    def _reviews(self) -> dict[tuple[str, str], MajorReview]:
        try:
            return self.controller.major_reviews()
        except ControllerError as exc:
            self.count.setText(f"重大隐患规则上下文不可用：{exc}")
            return {}

    def _sync_filter_options(self, rows) -> None:
        self._loading = True
        for combo, values in (
            (
                self.asset_filter,
                [ALL_ASSETS]
                + list(dict.fromkeys(issue.asset_type for issue in rows)),
            ),
            (
                self.point_filter,
                [ALL_POINTS]
                + list(
                    dict.fromkeys(
                        issue.values.get("安全控制点", "") for issue in rows
                    )
                ),
            ),
        ):
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(values)
            index = combo.findText(current)
            combo.setCurrentIndex(index if index >= 0 else 0)
            combo.blockSignals(False)
        self._loading = False

    def _apply_filters(self, *_args) -> None:
        if self._loading:
            return
        needle = self.search.text().strip().lower()
        asset_type = self.asset_filter.currentText()
        point = self.point_filter.currentText()
        priority = self.priority_filter.currentText()
        filtered = []
        for issue in self._issues:
            review = self._reviews_cache.get((issue.item_id, issue.asset_type))
            if asset_type != ALL_ASSETS and issue.asset_type != asset_type:
                continue
            if point != ALL_POINTS and issue.values.get("安全控制点", "") != point:
                continue
            if priority == "高风险命中" and review is None:
                continue
            if priority == "重大候选" and not (review and review.is_candidate):
                continue
            if priority == "已确认" and not (review and review.confirmed):
                continue
            if needle:
                haystack = " ".join(
                    (
                        issue.issue_no,
                        issue.asset_type,
                        issue.values.get("关联资产", ""),
                        issue.values.get("安全控制点", ""),
                        issue.values.get("测评项", ""),
                        issue.values.get("问题概述", ""),
                    )
                ).lower()
                if needle not in haystack:
                    continue
            filtered.append(issue)
        self._filtered = filtered
        self._fill_tables(filtered)

    def _fill_tables(self, issues) -> None:
        self.table.blockSignals(True)
        self.remediation_table.blockSignals(True)
        self.table.setRowCount(0)
        self.remediation_table.setRowCount(0)
        for issue in issues:
            review = self._reviews_cache.get((issue.item_id, issue.asset_type))
            row = self.table.rowCount()
            self.table.insertRow(row)
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
                item.setToolTip(self._risk_tip(review) if column == 6 else value)
                self.table.setItem(row, column, item)
            self.table.setCellWidget(
                row, len(PREVIEW_COLUMNS) - 1, self._review_cell(issue, review)
            )

            remediation_row = self.remediation_table.rowCount()
            self.remediation_table.insertRow(remediation_row)
            remediation_values = (
                issue.issue_no,
                issue.asset_type,
                issue.values["安全控制点"],
                issue.values["问题概述"],
                issue.values.get("危害分析", ""),
                issue.values.get("整改建议", ""),
                issue.values.get("整改状态", ""),
            )
            for column, value in enumerate(remediation_values):
                self.remediation_table.setItem(
                    remediation_row, column, QTableWidgetItem(value)
                )

        self.table.blockSignals(False)
        self.remediation_table.blockSignals(False)
        self._apply_view()
        if self._filtered:
            if self._view == "issues":
                self.table.selectRow(0)
            else:
                self.remediation_table.selectRow(0)
        else:
            self._clear_selection()

        reviews = self._reviews_cache
        confirmed = sum(1 for review in reviews.values() if review.confirmed)
        pending = sum(1 for review in reviews.values() if not review.confirmed)
        assets = {issue.values["关联资产"] for issue in self._issues}
        self._set_stats(len(self._issues), confirmed, len(assets), pending)
        if len(self._filtered) == len(self._issues):
            self.count.setText(
                f"共 {len(self._issues)} 行待汇总，其中 {confirmed} 行重大确认有效，"
                f"{pending} 行待确认或已失效"
            )
        else:
            self.count.setText(
                f"筛选显示 {len(self._filtered)} / {len(self._issues)} 行；"
                f"重大确认有效 {confirmed} 行，待确认或已失效 {pending} 行"
            )

    # ---- 视图 / 详情 ----
    def _switch_view(self, key: str) -> None:
        self._view = key
        self.issue_view_chip.blockSignals(True)
        self.remediation_view_chip.blockSignals(True)
        self.issue_view_chip.setChecked(key == "issues")
        self.remediation_view_chip.setChecked(key == "remediation")
        self.issue_view_chip.blockSignals(False)
        self.remediation_view_chip.blockSignals(False)
        self._apply_view()
        table = self.table if key == "issues" else self.remediation_table
        if table.rowCount():
            table.selectRow(0)

    def _apply_view(self) -> None:
        if self.controller.run_result is None:
            self.stack.setCurrentWidget(self.empty)
            return
        self.stack.setCurrentWidget(
            self.remediation_table if self._view == "remediation" else self.table
        )

    def _on_selection(self, table: QTableWidget) -> None:
        row = table.currentRow()
        if 0 <= row < len(self._filtered):
            self._show_detail(self._filtered[row])

    def _clear_selection(self) -> None:
        self.detail.setText("<p>当前筛选没有匹配的问题。</p>")

    def _show_detail(self, issue) -> None:
        review = self._reviews_cache.get((issue.item_id, issue.asset_type))
        fields = (
            ("问题编号", issue.issue_no),
            ("资产类型", issue.asset_type),
            ("关联资产", issue.values.get("关联资产", "")),
            ("安全控制点", issue.values.get("安全控制点", "")),
            ("测评项", issue.values.get("测评项", "")),
            ("问题概述", issue.values.get("问题概述", "")),
            ("危害分析", issue.values.get("危害分析", "") or "暂无危害分析"),
            ("整改建议", issue.values.get("整改建议", "") or "暂无整改建议"),
            ("整改状态", issue.values.get("整改状态", "") or "未整改"),
            ("修正原因", issue.values.get("修正原因", "")),
            ("补充措施", issue.values.get("补充措施", "")),
            ("影响区域", issue.values.get("影响的网络区域", "")),
        )
        body = "".join(
            f"<p style='margin:0 0 8px 0'><b>{html.escape(name)}</b><br/>"
            f"{html.escape(value or '—')}</p>"
            for name, value in fields
        )
        related = issue.values.get("关联资产", "")
        materials = [
            path.name.split("__", 1)[-1]
            for asset in self.controller.project.assets
            if asset.device_name and asset.device_name in related
            for path in self.controller.remediation_by_issue(asset).get(issue.issue_no, [])
        ]
        material_text = (
            "、".join(materials)
            if materials
            else "暂无关联整改材料，可在「材料与资产」页选中该设备后上传"
        )
        body += (
            f"<p style='margin:0 0 8px 0'><b>关联整改材料</b><br/>"
            f"{html.escape(material_text)}</p>"
        )
        if review is None:
            risk = "无高风险命中"
        elif review.confirmed:
            risk = "重大隐患已确认"
        elif review.reason == "未确认":
            risk = "待确认"
        else:
            risk = f"确认失效：{review.reason}"
        self.detail.setText(
            f"<h3 style='margin:0 0 10px 0'>{html.escape(issue.values.get('安全控制点', ''))}"
            f"　<span style='font-size:11pt'>{html.escape(issue.asset_type)}</span></h3>"
            f"{body}<hr/><p style='margin:0'><b>风险结论</b><br/>{html.escape(risk)}"
            f"<br/>{html.escape(self._score_text(review))}</p>"
        )

    def _risk_text(self, review: MajorReview | None) -> str:
        if review is None:
            return "无高风险命中"
        if not review.reducible:
            return "可降风险：否"
        basis = "；".join(review.reduction_basis) or "未填写前提"
        first = basis.split("；")[0]
        if len(first) > 46:
            first = f"{first[:46]}…"
        extra = (
            f"（共 {len(review.reduction_basis)} 项前提）"
            if len(review.reduction_basis) > 1
            else ""
        )
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
