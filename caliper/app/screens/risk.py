"""⑤ 风险与结论：高风险候选与重大隐患确认（占位，后续任务继续充实）。"""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from app.controller import AppController
from app.widgets import EmptyState, PageHeader


class RiskScreen(QWidget):
    def __init__(self, controller: AppController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setObjectName("page")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        self.header = PageHeader(
            "风险与结论",
            "独立确认高风险候选与重大隐患；未确认或失效的候选会阻断导出。",
        )
        layout.addWidget(self.header)

        self.empty = EmptyState(
            "尚未生成核查结果",
            "完成现场核查后，这里会列出高风险候选、三维评分与重大隐患确认状态。",
        )
        layout.addWidget(self.empty, 1)

        self.refresh()

    def refresh(self) -> None:
        if self.controller.run_result is None:
            self.empty.set_text(
                "尚未生成核查结果",
                "完成现场核查后，这里会列出高风险候选、三维评分与重大隐患确认状态。",
            )
            return
        try:
            reviews = self.controller.major_reviews()
        except Exception:  # noqa: BLE001 - 风险统计失败时退回空状态说明
            self.empty.set_text("风险统计暂不可用", "规则包或判定依据尚未就绪，请重新运行判定。")
            return
        pending = sum(1 for review in reviews.values() if review.reason == "未确认")
        self.empty.set_text(
            "风险与结论（占位）",
            f"当前批次共 {len(reviews)} 条高风险候选，其中 {pending} 条重大隐患待确认。",
        )
