"""默认分析器：永远返回空草稿，不联网、不生成内容。"""

from __future__ import annotations

from typing import Any, Mapping

from core.ports.interfaces import AnalysisDraft


class NoopAnalyzer:
    name = "noop"

    def analyze(self, issue: Mapping[str, Any], context: Mapping[str, Any]) -> AnalysisDraft:
        return AnalysisDraft(source=self.name)
