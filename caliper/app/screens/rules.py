"""⑥ 规则库：六库页签 + 搜索 + 左表右详情。

六库对应规则包内的六类数据资产：控制项、检查映射、判定规则、
高风险判例、重大隐患规则、文案库。每库显示条数、版本与路径。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.controller import AppController
from app.widgets import PageHeader

LIBRARIES = (
    ("items", "控制项"),
    ("checks", "检查映射"),
    ("rules", "判定规则"),
    ("high_risk", "高风险判例"),
    ("major", "重大隐患规则"),
    ("texts", "文案库"),
)


class RulesScreen(QWidget):
    def __init__(self, controller: AppController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._pack = None
        self._rows: dict[str, list[tuple[str, str, str]]] = {}
        self.setObjectName("page")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        self.header = PageHeader("规则库", "规则包内的控制项、映射、判定规则与判例，只读展示")
        layout.addWidget(self.header)

        self.pack_line = QLabel("尚未加载规则包")
        self.pack_line.setObjectName("muted")
        self.pack_line.setWordWrap(True)
        layout.addWidget(self.pack_line)

        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self._on_tab_changed)
        for key, label in LIBRARIES:
            self.tabs.addTab(self._build_page(key), label)
        layout.addWidget(self.tabs, 1)

        self.refresh()

    # ------------------------------------------------------------------ 页面
    def _build_page(self, key: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        info_row = QHBoxLayout()
        info_row.setSpacing(8)
        search = QLineEdit()
        search.setPlaceholderText("搜索当前库")
        search.setClearButtonEnabled(True)
        search.textChanged.connect(lambda _t, k=key: self._apply_filter(k))
        info = QLabel("")
        info.setObjectName("muted")
        info_row.addWidget(search, 1)
        info_row.addWidget(info)
        layout.addLayout(info_row)

        splitter = QSplitter(Qt.Horizontal)
        table = QTableWidget(0, 2)
        table.setHorizontalHeaderLabels(("标识", "摘要"))
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.setWordWrap(False)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        header = table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        table.setColumnWidth(0, 200)
        table.itemSelectionChanged.connect(lambda k=key: self._show_detail(k))

        detail = QTextBrowser()
        detail.setObjectName("evidence")
        detail.setOpenExternalLinks(False)

        splitter.addWidget(table)
        splitter.addWidget(detail)
        splitter.setSizes([480, 420])
        layout.addWidget(splitter, 1)

        setattr(self, f"_{key}_search", search)
        setattr(self, f"_{key}_info", info)
        setattr(self, f"_{key}_table", table)
        setattr(self, f"_{key}_detail", detail)
        setattr(self, f"_{key}_visible", [])
        return page

    # ------------------------------------------------------------------ 数据
    def _load_pack(self):
        if self._pack is not None:
            return self._pack
        self._pack = self.controller.pack or self.controller.load_pack()
        return self._pack

    def refresh(self) -> None:
        self._rows = {}
        try:
            pack = self._load_pack()
        except Exception as exc:  # noqa: BLE001
            self.pack_line.setText(f"规则包加载失败：{exc}")
            return
        self._pack = pack
        self.pack_line.setText(
            f"{pack.meta.name} v{pack.meta.version}　·　"
            f"等级 {pack.meta.levels}　·　OS {pack.meta.os_family}　·　"
            f"资产类型 {pack.meta.asset_types}"
        )
        self._rows["items"] = self._items_rows(pack)
        self._rows["checks"] = self._checks_rows(pack)
        self._rows["rules"] = self._rules_rows(pack)
        self._rows["high_risk"] = self._high_risk_rows(pack)
        self._rows["major"] = self._major_rows(pack)
        self._rows["texts"] = self._texts_rows(pack)
        self._on_tab_changed(self.tabs.currentIndex())

    # ---- 各库行提取：返回 (标识, 摘要, 详情)
    def _items_rows(self, pack) -> list[tuple[str, str, str]]:
        try:
            items = pack.items_for_level(self.controller.project.level)
        except Exception:  # noqa: BLE001
            items = []
        rows = []
        for item in items:
            detail = (
                f"{item.item_id}　{item.control_point}\n"
                f"重要性：{item.importance}\n"
                f"判定：{item.binary}\n"
                f"核查内容：{item.check_content or '—'}\n"
                f"判断标准：{item.criteria or '—'}"
            )
            rows.append((str(item.seq), item.control_point, detail))
        return rows

    def _checks_rows(self, pack) -> list[tuple[str, str, str]]:
        rows = []
        for check in pack.checks.checks:
            detail = (
                f"标题：{check.title}\n"
                f"采集段：{check.section or '—'}（块 {check.block_index}）\n"
                f"类型：{check.kind}\n"
                f"系统族：{check.os_family or '—'}\n"
                f"归一化：{check.normalize or '—'}\n"
                f"绑定实施点：{len(check.binds)} 个"
            )
            rows.append((f"块 {check.block_index}", check.title, detail))
        return rows

    def _rules_rows(self, pack) -> list[tuple[str, str, str]]:
        rows = []
        for rule in pack.rules.rules:
            detail = (
                f"规则：{rule.rule_id or '（自动生成）'}\n"
                f"等级/项/实施点：L{rule.level}-{rule.item}-P{rule.point}\n"
                f"采集块：{rule.block}\n"
                f"判定：{rule.expect}"
            )
            rows.append((rule.rule_id or f"L{rule.level}-{rule.item}", f"P{rule.point} {rule.block}", detail))
        return rows

    def _high_risk_rows(self, pack) -> list[tuple[str, str, str]]:
        rows = []
        for entry in pack.high_risk:
            hr_id = entry.get("hr_id", "—")
            summary = entry.get("问题概述") or entry.get("问题") or ""
            detail = "\n".join(f"{k}：{v}" for k, v in entry.items())
            rows.append((hr_id, summary, detail))
        return rows

    def _major_rows(self, pack) -> list[tuple[str, str, str]]:
        rows = []
        if pack.major is None:
            return rows
        for rule in pack.major.rules:
            scores = "　".join(f"{name} {entry.score}" for name, entry in rule.scores.items())
            detail = (
                f"规则：{rule.id}\n"
                f"关联高风险判例：{', '.join(rule.hr_ids)}\n"
                f"三维得分：{scores}\n"
                f"库版本：{pack.major.version}　阈值：{pack.major.threshold}"
            )
            rows.append((rule.id, f"关联 {len(rule.hr_ids)} 条判例", detail))
        return rows

    def _texts_rows(self, pack) -> list[tuple[str, str, str]]:
        rows = []
        for entry in pack.texts:
            control = entry.get("control_item") or entry.get("控制项") or "—"
            summary = entry.get("问题") or entry.get("问题概述") or ""
            detail = "\n".join(f"{k}：{v}" for k, v in entry.items())
            rows.append((control, summary, detail))
        return rows

    # ---- 展示
    def _on_tab_changed(self, index: int) -> None:
        if index < 0:
            return
        key = LIBRARIES[index][0]
        self._apply_filter(key)

    def _apply_filter(self, key: str) -> None:
        search = getattr(self, f"_{key}_search")
        info = getattr(self, f"_{key}_info")
        table = getattr(self, f"_{key}_table")
        needle = search.text().strip().lower()
        rows = self._rows.get(key, [])
        visible = [
            row for row in rows
            if not needle or needle in row[0].lower() or needle in row[1].lower()
        ]
        table.setRowCount(0)
        setattr(self, f"_{key}_visible", visible)
        for primary, secondary, _detail in visible:
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(primary))
            table.setItem(row, 1, QTableWidgetItem(secondary))
        version, path = self._library_meta(key)
        info.setText(f"共 {len(visible)}/{len(rows)} 条　·　v{version}　·　{path}")
        self._show_detail(key)

    def _library_meta(self, key: str) -> tuple[str, str]:
        pack = self._pack
        if pack is None:
            return "—", "—"
        if key == "major" and pack.major is not None:
            return pack.major.version, pack.meta.major
        version = pack.meta.version
        paths = {
            "items": pack.meta.items.get(str(self.controller.project.level), "—")
            if isinstance(pack.meta.items, dict)
            else str(pack.meta.items),
            "checks": pack.meta.checks_map,
            "rules": pack.meta.rules_dir,
            "high_risk": pack.meta.high_risk,
            "texts": pack.meta.texts,
        }
        return version, paths.get(key, "—")

    def _show_detail(self, key: str) -> None:
        detail = getattr(self, f"_{key}_detail")
        table = getattr(self, f"_{key}_table")
        rows = getattr(self, f"_{key}_visible")
        row = table.currentRow()
        if row < 0 or row >= len(rows):
            detail.setPlainText("选择左侧一行查看详情")
            return
        detail.setPlainText(rows[row][2])
