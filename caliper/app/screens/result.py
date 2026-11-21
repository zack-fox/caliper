"""② 结果记录：控制项列表 + 证据原文 + 备注编辑。"""

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
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.controller import AppController, ControllerError
from core.contracts.verdict import to_text
from core.model.entities import ItemResult


class ResultScreen(QWidget):
    def __init__(self, controller: AppController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.current_result: ItemResult | None = None
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("资产"))
        self.asset_combo = QComboBox()
        self.asset_combo.currentIndexChanged.connect(self._populate_items)
        top.addWidget(self.asset_combo, 1)
        self.summary = QLabel("尚未运行判定")
        self.summary.setObjectName("muted")
        top.addWidget(self.summary)
        layout.addLayout(top)

        splitter = QSplitter(Qt.Horizontal)
        self.item_list = QListWidget()
        self.item_list.currentItemChanged.connect(self._show_item)
        splitter.addWidget(self.item_list)

        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        self.title = QLabel("请选择测评项")
        self.title.setObjectName("title")
        self.title.setWordWrap(True)
        detail_layout.addWidget(self.title)
        self.verdict = QLabel("")
        detail_layout.addWidget(self.verdict)
        self.body = QTextBrowser()
        self.body.setOpenExternalLinks(False)
        detail_layout.addWidget(self.body, 1)

        note_row = QHBoxLayout()
        note_row.addWidget(QLabel("备注"))
        self.note = QLineEdit()
        self.note.setPlaceholderText("现场说明 / 未采集原因")
        note_row.addWidget(self.note, 1)
        self.save_note = QPushButton("保存备注")
        self.save_note.clicked.connect(self._save_note)
        note_row.addWidget(self.save_note)
        detail_layout.addLayout(note_row)
        splitter.addWidget(detail)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter, 1)

    def refresh(self) -> None:
        self.asset_combo.blockSignals(True)
        self.asset_combo.clear()
        if self.controller.run_result is not None:
            for run in self.controller.run_result.asset_runs:
                self.asset_combo.addItem(run.asset.device_name)
        self.asset_combo.blockSignals(False)
        self._populate_items()

    def _current_run(self):
        result = self.controller.run_result
        if result is None:
            return None
        index = self.asset_combo.currentIndex()
        if index < 0 or index >= len(result.asset_runs):
            return None
        return result.asset_runs[index]

    def _populate_items(self) -> None:
        self.item_list.clear()
        self.body.clear()
        self.title.setText("请选择测评项")
        self.verdict.setText("")
        self.note.clear()
        run = self._current_run()
        if run is None:
            self.summary.setText("尚未运行判定")
            return
        counts: dict[str, int] = {}
        for item in run.items:
            label = to_text(item.verdict) or "空"
            counts[label] = counts.get(label, 0) + 1
            entry = QListWidgetItem(f"{item.seq:>2}  {item.control_point}  ·  {label}")
            entry.setData(Qt.UserRole, item.seq)
            self.item_list.addItem(entry)
        self.summary.setText("  ".join(f"{key} {value}" for key, value in counts.items()))

    def _show_item(self, current: QListWidgetItem | None, _previous=None) -> None:
        run = self._current_run()
        if run is None or current is None:
            return
        seq = current.data(Qt.UserRole)
        result = run.item_by_seq(int(seq))
        if result is None:
            return
        self.current_result = result
        self.title.setText(f"{result.seq}. {result.control_point}  {result.item_id}")
        self.verdict.setText(f"结论：{to_text(result.verdict) or '未采集'}")
        self.verdict.setObjectName(
            "success" if result.verdict.value == "符合" else "danger" if result.verdict.value == "不符合" else "warning"
        )
        self.verdict.style().unpolish(self.verdict)
        self.verdict.style().polish(self.verdict)
        self.body.setHtml(self._render_detail(result))
        self.note.setText(result.note)

    @staticmethod
    def _render_detail(result: ItemResult) -> str:
        parts: list[str] = []
        if result.result_text:
            parts.append(f"<h3>判定记录</h3><pre>{_escape(result.result_text)}</pre>")
        if not result.points:
            parts.append(f"<p>{_escape(result.note or '没有可展示的实施点')}</p>")
        for point in result.points:
            state = "通过" if point.passed else "未通过"
            colour = "#1f9d55" if point.passed else "#d64545"
            parts.append(
                f"<p><b>实施点 {point.point}</b> "
                f"<span style='color:{colour}'>{state}</span>：{_escape(point.reason)}</p>"
            )
            parts.append(f"<p style='color:#6b7785'>证据块：{_escape(point.block_title)}</p>")
            for anchor in point.anchors:
                parts.append(
                    "<pre style='background:#f5f6f8;border:1px solid #d9dee7'>"
                    f"{_escape(anchor.file)}:{anchor.line}\n{_escape(anchor.snippet)}</pre>"
                )
        if result.warnings:
            parts.append("<p style='color:#c47f17'><b>告警</b></p><ul>")
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
            self.summary.setText(f"备注保存失败：{exc}")
            return
        self.current_result.note = text
        self.summary.setText("备注已保存到 corrections.db")


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br>")
    )
