"""扩展端口：首版只用 noop 实现，后续大模型/报告合成/验收材料从这里接入。

端口只定义边界，不引入任何网络或模型依赖。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable


@dataclass(frozen=True)
class AnalysisDraft:
    """人工分析草稿。空字段一律保持空，不许编造。"""

    summary: str = ""
    detail: str = ""
    hazard: str = ""
    remediation: str = ""
    source: str = "noop"
    extra: dict[str, str] = field(default_factory=dict)


@runtime_checkable
class AnalyzerPort(Protocol):
    """禁止未授权访问/非法使用等问题的分析草稿来源。"""

    name: str

    def analyze(self, issue: Mapping[str, Any], context: Mapping[str, Any]) -> AnalysisDraft: ...


@runtime_checkable
class CorrectionStorePort(Protocol):
    """预览校正的持久化端口（P8 接入）。"""

    def load(self, project_key: str) -> list[dict[str, Any]]: ...

    def append(self, project_key: str, correction: dict[str, Any]) -> None: ...


@runtime_checkable
class ExporterPort(Protocol):
    """四张表的导出端口。"""

    def export(self, run_result: Any, items: list[Any], output_dir: Path) -> list[Path]: ...


@runtime_checkable
class ReportComposerPort(Protocol):
    """报告合成端口（当前不做，仅预留）。"""

    def compose(self, run_result: Any, output_dir: Path) -> Path: ...


@runtime_checkable
class AcceptancePort(Protocol):
    """验收材料端口（当前不做，仅预留）。"""

    def build(self, run_result: Any, output_dir: Path) -> list[Path]: ...
