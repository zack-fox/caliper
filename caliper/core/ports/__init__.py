"""扩展端口（首版只提供 noop 实现）。"""

from core.ports.interfaces import (
    AcceptancePort,
    AnalysisDraft,
    AnalyzerPort,
    CorrectionStorePort,
    ExporterPort,
    ReportComposerPort,
)

__all__ = [
    "AcceptancePort",
    "AnalysisDraft",
    "AnalyzerPort",
    "CorrectionStorePort",
    "ExporterPort",
    "ReportComposerPort",
]
