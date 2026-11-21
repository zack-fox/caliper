"""② 结果记录：控制项列表 + 详情/证据原文 + 判定与备注。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.controller import AppController, ControllerError
from app.widgets import Badge, Card, EmptyState, PageHeader, StatCard, hbox
from core.model.entities import ItemResult

VERDICT_TONES = {
    "符合": "ok",
    "部分符合": "warn",
    "不符合": "bad",
    "不适用": "neutral",
    "未采集": "info",
}


class ResultsScreen(QWidget):
    def __init__(self, controller: AppController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.current_result: ItemResult | None = None
        self._item_names: dict[int, str] = {}
        self.setObjectName("page")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        self.header = PageHeader(
            "结果记录",
            "判定由规则产出，人工只做校正并留下理由；证据原文始终可追溯到日志行号。",
        )
        self.asset_combo = QComboBox()
        self.asset_combo.setMinimumWidth(220)
        self.asset_combo.currentIndexChanged.connect(self._populate_items)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索控制点 / 编号")
        self.search.setMinimumWidth(180)
        self.search.textChanged.connect(self._populate_items)
        self.verdict_filter = QComboBox()
        self.verdict_filter.addItems(["全部结论", "符合", "部分符合", "不符合", "不适用", "未采集"])
        self.verdict_filter.currentIndexChanged.connect(self._populate_items)
        for widget in (QLabel("资产"), self.asset_combo, self.search, self.verdict_filter):
            if isinstance(widget, QLabel):
                widget.setObjectName("secondary")
            self.header.add_action(widget)
        layout.addWidget(self.header)

        self.stat_ok = StatCard("符合", "0")
        self.stat_partial = StatCard("部分符合", "0")
        self.stat_bad = StatCard("不符合", "0")
        self.stat_na = StatCard("不适用 / 未采集", "0")
        stat_row = QHBoxLayout()
        stat_row.setSpacing(12)
        for card in (self.stat_ok, self.stat_partial, self.stat_bad, self.stat_na):
            stat_row.addWidget(card, 1)
        layout.addLayout(stat_row)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        list_card = Card("控制项", "按安全控制点排列")
        self.item_list = QListWidget()
        self.item_list.setWordWrap(True)
        self.item_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.item_list.currentItemChanged.connect(self._show_item)
        list_card.add(self.item_list, 1)
        splitter.addWidget(list_card)

        detail_card = Card()
        self.detail_empty = EmptyState(
            "尚未运行核查",
            "请在「证据与资产」页导入设备证据后开始核查，结果会逐项列出。",
        )

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)

        self.title = QLabel("请选择测评项")
        self.title.setObjectName("section_title")
        self.title.setWordWrap(True)
        self.verdict_badge = Badge("未选择", "neutral")
        self.item_meta = QLabel("")
        self.item_meta.setObjectName("muted")
        content_layout.addLayout(hbox(self.title, None, self.verdict_badge))
        content_layout.addWidget(self.item_meta)
        self.body = QTextBrowser()
        self.body.setObjectName("evidence")
        content_layout.addWidget(self.body, 1)

        note_row = QHBoxLayout()
        note_row.setSpacing(8)
        note_caption = QLabel("核查说明")
        note_caption.setObjectName("secondary")
        self.note = QLineEdit()
        self.note.setPlaceholderText("现场说明 / 未采集原因 / 校正理由（必填）")
        self.save_note = QPushButton("保存说明")
        self.save_note.clicked.connect(self._save_note)
        note_row.addWidget(note_caption)
        note_row.addWidget(self.note, 1)
        note_row.addWidget(self.save_note)
        content_layout.addLayout(note_row)

        self.detail_stack = QStackedWidget()
        self.detail_stack.addWidget(self.detail_empty)
        self.detail_stack.addWidget(content)
        self.detail_content = content
        detail_card.add(self.detail_stack, 1)
        splitter.addWidget(detail_card)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([320, 900])
        layout.addWidget(splitter, 1)

        self.refresh()

    # ---- 刷新 ----
    def refresh(self) -> None:
        self._item_names = self._load_item_names()
        self.asset_combo.blockSignals(True)
        self.asset_combo.clear()
        if self.controller.run_result is not None:
            for run in self.controller.run_result.asset_runs:
                self.asset_combo.addItem(run.asset.device_name)
        self.asset_combo.blockSignals(False)
        self._populate_items()

    def _load_item_names(self) -> dict[int, str]:
        """序号 → 控制项名称，避免列表里连续多行同名控制点。"""
        try:
            pack = self.controller.load_pack()
            items = pack.items_for_level(self.controller.project.level)
        except Exception:
            return {}
        return {item.seq: item.control_item for item in items}

    def _current_run(self):
        result = self.controller.run_result
        if result is None:
            return None
        index = self.asset_combo.currentIndex()
        if index < 0 or index >= len(result.asset_runs):
            return None
        return result.asset_runs[index]

    def _populate_items(self, *_args) -> None:
        self.item_list.clear()
        self.body.clear()
        self.title.setText("请选择测评项")
        self.item_meta.setText("")
        self.verdict_badge.set_text("未选择", "neutral")
        self.note.clear()
        run = self._current_run()
        if run is None:
            self.detail_empty.set_text(
                "尚未运行核查",
                "请在「证据与资产」页导入设备证据后开始核查，结果会逐项列出。",
            )
            self.detail_stack.setCurrentWidget(self.detail_empty)
            for card in (self.stat_ok, self.stat_partial, self.stat_bad, self.stat_na):
                card.set_value("0")
            return

        keyword = self.search.text().strip().lower()
        selected = self.verdict_filter.currentText()
        counts = {"符合": 0, "部分符合": 0, "不符合": 0, "不适用": 0, "未采集": 0}
        for item in run.items:
            label = _verdict_label(item)
            counts[label] = counts.get(label, 0) + 1
            if selected != "全部结论" and label != selected:
                continue
            haystack = f"{item.seq} {item.control_point} {item.item_id}".lower()
            if keyword and keyword not in haystack:
                continue
            entry = QListWidgetItem(
                f"{item.seq:>2}  {self._item_names.get(item.seq) or item.control_point}"
            )
            entry.setData(Qt.UserRole, item.seq)
            entry.setToolTip(f"{item.item_id} · {label}")
            self.item_list.addItem(entry)

        self.stat_ok.set_value(str(counts["符合"]))
        self.stat_partial.set_value(str(counts["部分符合"]))
        self.stat_bad.set_value(str(counts["不符合"]))
        self.stat_na.set_value(str(counts["不适用"] + counts["未采集"]))
        if self.item_list.count() == 0:
            self.detail_empty.set_text("没有匹配的测评项", "调整搜索关键词或结论筛选试试。")
            self.detail_stack.setCurrentWidget(self.detail_empty)
        else:
            self.detail_empty.set_text("选择左侧测评项", "点击任意控制项查看判定结果与证据原文。")
            self.detail_stack.setCurrentWidget(self.detail_empty)

    # ---- 详情 ----
    def _show_item(self, current: QListWidgetItem | None, _previous=None) -> None:
        run = self._current_run()
        if run is None or current is None:
            return
        result = run.item_by_seq(int(current.data(Qt.UserRole)))
        if result is None:
            return
        self.current_result = result
        label = _verdict_label(result)
        self.title.setText(
            f"{result.seq}. {self._item_names.get(result.seq) or result.control_point}"
        )
        self.item_meta.setText(
            f"{result.control_point} · {result.item_id} · 重要程度 {result.importance}"
        )
        self.verdict_badge.set_text(label, VERDICT_TONES.get(label, "neutral"))
        self.body.setHtml(self._render_detail(result))
        self.note.setText(result.note)
        self.detail_stack.setCurrentWidget(self.detail_content)

    @staticmethod
    def _render_detail(result: ItemResult) -> str:
        pre = '<pre style="white-space:pre-wrap; margin:4px 0">'
        parts: list[str] = []
        if result.result_text:
            parts.append(f"<b>判定记录</b><br>{pre}{_escape(result.result_text)}</pre>")
        if not result.points:
            parts.append(f"<p>{_escape(result.note or '没有可展示的实施点')}</p>")
        for point in result.points:
            state = "通过" if point.passed else "未通过"
            colour = "#4ade80" if point.passed else "#f87171"
            parts.append(
                f"<p><b>实施点 {point.point}</b> "
                f"<span style='color:{colour}'>{state}</span>：{_escape(point.reason)}</p>"
            )
            parts.append(f"<p style='color:#94a3b8'>证据块：{_escape(point.block_title)}</p>")
            for anchor in point.anchors:
                parts.append(
                    f"{pre}{_escape(anchor.file)}:{anchor.line}\n{_escape(anchor.snippet)}</pre>"
                )
        if result.warnings:
            parts.append("<p style='color:#fbbf24'><b>告警</b></p><ul>")
            parts.extend(f"<li>{_escape(text)}</li>" for text in result.warnings)
            parts.append("</ul>")
        return "".join(parts) or "<p>暂无内容</p>"

    def _save_note(self) -> None:
        run = self._current_run()
        if self.current_result is None or run is None:
            return
        text = self.note.text()
        try:
            self.controller.save_note(
                self.current_result.item_id, run.asset.asset_type.value, text
            )
        except ControllerError as exc:
            self.item_meta.setText(f"备注保存失败：{exc}")
            return
        self.current_result.note = text
        self.item_meta.setText("核查说明已保存到 corrections.db，导出时自动带入")


def _verdict_label(item: ItemResult) -> str:
    return item.verdict.value


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br>")
    )
