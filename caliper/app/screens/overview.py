"""① 项目概述：项目上下文、核查进度、待处理项与下一步入口。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.controller import AppController
from app.widgets import Badge, Card, EmptyState, MetricPill, PageHeader, scrollable
from core.contracts.verdict import Verdict

STATE_TEXT = {"done": "已完成", "todo": "待处理", "blocked": "阻断"}
STATE_TONE = {"done": "ok", "todo": "neutral", "blocked": "bad"}

SUMMARY_FIELDS = (
    ("project_code", "项目编号"),
    ("system_name", "系统名称"),
    ("level", "等保等级"),
    ("check_date", "检查日期"),
    ("devices", "设备数"),
    ("pack", "规则包"),
)

QUICK_ENTRIES = (
    ("evidence", "导入材料"),
    ("results", "现场核查"),
    ("risk", "风险与结论"),
    ("export", "导出交付"),
)

UNSET = "未设置"
NO_DRAFT = "尚未生成记录草稿"


class OverviewScreen(QWidget):
    navigate = Signal(str)

    def __init__(self, controller: AppController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setObjectName("page")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        self.header = PageHeader(
            "项目概述",
            "现场作业入口：确认项目上下文、核查进度与待处理事项，再进入对应页面。",
        )
        self.import_button = self._action_button("导入材料", "primary", "evidence")
        self.header.add_action(self.import_button)
        layout.addWidget(self.header)

        layout.addWidget(self._build_metrics())

        self.stack = QStackedWidget()
        self.stack.addWidget(scrollable(self._build_body()))
        self.stack.addWidget(scrollable(self._build_empty()))
        layout.addWidget(self.stack, 1)

        self.refresh()

    # ---- 构建 ----
    def _build_metrics(self) -> QWidget:
        area = QWidget()
        area.setObjectName("page")
        column = QVBoxLayout(area)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        self.pill_devices = MetricPill("设备数", "—")
        self.pill_checked = MetricPill("已核查", "—")
        self.pill_non_compliant = MetricPill("不符合数", "—")
        self.pill_pending = MetricPill("待确认重大隐患", "—")
        for pill in (
            self.pill_devices,
            self.pill_checked,
            self.pill_non_compliant,
            self.pill_pending,
        ):
            row.addWidget(pill)
        row.addStretch(1)
        column.addLayout(row)

        self.metric_hint = QLabel(NO_DRAFT)
        self.metric_hint.setObjectName("muted")
        self.metric_hint.setWordWrap(True)
        column.addWidget(self.metric_hint)
        return area

    def _build_body(self) -> QWidget:
        body = QWidget()
        body.setObjectName("page")
        column = QVBoxLayout(body)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(14)

        column.addWidget(self._build_summary())
        column.addWidget(self._build_steps())
        column.addWidget(self._build_pending())
        column.addWidget(self._build_quick_entries())
        column.addStretch(1)
        return body

    def _build_summary(self) -> Card:
        self.summary_card = Card("项目摘要", "数据来自当前项目与规则包")
        grid = QGridLayout()
        grid.setContentsMargins(0, 2, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        self.summary_fields: dict[str, QLabel] = {}
        for index, (key, caption) in enumerate(SUMMARY_FIELDS):
            label = QLabel(caption)
            label.setObjectName("secondary")
            value = QLabel(UNSET)
            value.setObjectName("mono")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.summary_fields[key] = value
            grid.addWidget(label, index // 2, (index % 2) * 2)
            grid.addWidget(value, index // 2, (index % 2) * 2 + 1)
        self.summary_card.body.addLayout(grid)
        return self.summary_card

    def _build_steps(self) -> Card:
        # app.shell 包会在导入时装配 AppShell，延迟导入避免概述页与外壳循环引用。
        from app.shell.navigation import workflow_steps

        card = Card("核查进度", "与顶部步骤条同一状态口径，点击步骤进入对应页面")
        grid = QGridLayout()
        grid.setContentsMargins(0, 2, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(2, 1)

        self.step_buttons: dict[str, QPushButton] = {}
        self.step_badges: dict[str, Badge] = {}
        for row, step in enumerate(workflow_steps()):
            button = QPushButton(f"{row + 1}  {step.label}")
            button.setObjectName("ghost")
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(step.hint)
            button.clicked.connect(
                lambda _checked=False, target=step.key: self.navigate.emit(target)
            )
            badge = Badge(STATE_TEXT["todo"], STATE_TONE["todo"])
            hint = QLabel(step.hint)
            hint.setObjectName("muted")
            hint.setWordWrap(True)
            self.step_buttons[step.key] = button
            self.step_badges[step.key] = badge
            grid.addWidget(button, row, 0)
            grid.addWidget(badge, row, 1)
            grid.addWidget(hint, row, 2)
        card.body.addLayout(grid)
        return card

    def _build_pending(self) -> Card:
        self.pending_card = Card("待处理清单", "最多显示 5 条，点击「前往」进入对应页面")
        self.pending_box = QVBoxLayout()
        self.pending_box.setContentsMargins(0, 0, 0, 0)
        self.pending_box.setSpacing(4)
        self.pending_card.body.addLayout(self.pending_box)
        return self.pending_card

    def _build_quick_entries(self) -> Card:
        card = Card("快捷入口", "按四步闭环进入下一步")
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.quick_entries: dict[str, QPushButton] = {}
        for key, caption in QUICK_ENTRIES:
            button = self._action_button(caption, "subtle", key)
            row.addWidget(button)
            self.quick_entries[key] = button
        row.addStretch(1)
        card.body.addLayout(row)
        return card

    def _build_empty(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        column = QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)

        self.empty = EmptyState(
            "尚未导入项目材料",
            "前往「材料与资产」导入采集目录后，这里会显示核查进度与待处理事项。",
        )
        column.addWidget(self.empty, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        self.empty_import = self._action_button("导入材料", "primary", "evidence")
        row.addWidget(self.empty_import)
        row.addStretch(1)
        column.addLayout(row)
        column.addStretch(1)
        return page

    def _action_button(self, caption: str, kind: str, route: str) -> QPushButton:
        button = QPushButton(caption)
        button.setObjectName(kind)
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(
            lambda _checked=False, target=route: self.navigate.emit(target)
        )
        return button

    # ---- 刷新 ----
    def refresh(self) -> None:
        # 与 AppShell 共用步骤状态函数；延迟导入避免循环引用。
        from app.shell.progress import step_states

        project = self.controller.project
        result = self.controller.run_result
        has_assets = bool(project.assets)
        has_data = has_assets or result is not None
        pending_major = self._pending_major(result)
        checked, total, non_compliant = self._verdict_counts(result)

        self._fill_summary(project, has_data)
        self._fill_metrics(project, result, has_data, pending_major, checked, total, non_compliant)
        self._fill_steps(step_states(has_assets, result is not None, pending_major))
        self._fill_pending(project, result, pending_major)
        self.stack.setCurrentIndex(0 if has_data else 1)

    def _pending_major(self, result) -> int:
        if result is None:
            return 0
        try:
            reviews = self.controller.major_reviews()
        except Exception:  # noqa: BLE001 - 统计失败不应阻断概述页
            return 0
        return sum(1 for review in reviews.values() if review.reason == "未确认")

    def _verdict_counts(self, result) -> tuple[int, int, int]:
        checked = total = non_compliant = 0
        if result is None:
            return checked, total, non_compliant
        for run in result.asset_runs:
            for item in run.items:
                total += 1
                if item.verdict != Verdict.UNCOLLECTED:
                    checked += 1
                if item.verdict == Verdict.NON_COMPLIANT:
                    non_compliant += 1
        return checked, total, non_compliant

    def _fill_summary(self, project, has_data: bool) -> None:
        if not has_data:
            for key in self.summary_fields:
                self.summary_fields[key].setText(UNSET)
            self.summary_fields["devices"].setText("—")
            return

        try:
            pack = self.controller.load_pack()
        except Exception:  # noqa: BLE001 - 规则包缺失时明确标注
            pack_label = "规则包未加载"
        else:
            pack_label = f"{pack.meta.name} v{pack.meta.version}"

        check_date = getattr(project, "check_date", None)
        values = {
            "project_code": project.project_code.strip() or UNSET,
            "system_name": project.system_name.strip() or UNSET,
            "level": f"{project.level} 级" if project.level else UNSET,
            "check_date": check_date.strftime("%Y-%m-%d") if check_date else UNSET,
            "devices": str(len(project.assets)),
            "pack": pack_label,
        }
        for key, text in values.items():
            self.summary_fields[key].setText(text)

    def _fill_metrics(
        self,
        project,
        result,
        has_data: bool,
        pending_major: int,
        checked: int,
        total: int,
        non_compliant: int,
    ) -> None:
        self.metric_hint.setVisible(result is None)
        if not has_data:
            for pill in (
                self.pill_devices,
                self.pill_checked,
                self.pill_non_compliant,
                self.pill_pending,
            ):
                pill.set_value("—")
            return

        self.pill_devices.set_value(str(len(project.assets)))
        if result is None:
            self.pill_checked.set_value("—")
            self.pill_non_compliant.set_value("—")
            self.pill_pending.set_value("—")
            return

        self.pill_checked.set_value(f"{checked}/{total}")
        self.pill_non_compliant.set_value(str(non_compliant))
        self.pill_pending.set_value(str(pending_major))

    def _fill_steps(self, states: dict[str, str]) -> None:
        for key, badge in self.step_badges.items():
            state = states.get(key, "todo")
            badge.set_text(STATE_TEXT[state], STATE_TONE[state])

    def _fill_pending(self, project, result, pending_major: int) -> None:
        while self.pending_box.count():
            entry = self.pending_box.takeAt(0)
            widget = entry.widget()
            if widget is not None:
                widget.deleteLater()

        self.pending_actions: list[tuple[str, QPushButton]] = []
        self.pending_labels: list[QLabel] = []

        items = self._pending_items(project, result, pending_major)[:5]
        if not items:
            label = QLabel("当前没有待处理事项")
            label.setObjectName("muted")
            self.pending_box.addWidget(label)
            self.pending_labels.append(label)
            return

        for route, text in items:
            row = QWidget()
            row.setObjectName("page")
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
            label = QLabel(text)
            label.setObjectName("secondary")
            label.setWordWrap(True)
            button = self._action_button("前往", "ghost", route)
            button.setMinimumHeight(26)
            layout.addWidget(label, 1)
            layout.addWidget(button)
            self.pending_box.addWidget(row)
            self.pending_labels.append(label)
            self.pending_actions.append((route, button))

    def _pending_items(self, project, result, pending_major: int) -> list[tuple[str, str]]:
        items: list[tuple[str, str]] = []
        if pending_major:
            items.append(("risk", f"未确认重大隐患 {pending_major} 条"))

        if result is None:
            items.append(("evidence", NO_DRAFT))
        else:
            uncollected = sum(
                1
                for run in result.asset_runs
                for item in run.items
                if item.verdict == Verdict.UNCOLLECTED
            )
            if uncollected:
                items.append(("results", f"存在未采集项 {uncollected} 条"))

            try:
                issue_count = len(self.controller.issue_rows())
            except Exception:  # noqa: BLE001 - 问题统计失败时省略该提示
                issue_count = 0
            if issue_count:
                items.append(("issues", f"问题 {issue_count} 条待整改"))

        missing = [
            asset for asset in project.assets if not (asset.evidence_package or "").strip()
        ]
        if missing:
            items.append(("evidence", f"{len(missing)} 台设备尚未关联材料"))
        return items
