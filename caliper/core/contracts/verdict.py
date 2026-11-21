"""五值落表文本与分数映射（唯一真相，不许别处自造）。"""

from __future__ import annotations

from enum import Enum


class Verdict(str, Enum):
    COMPLIANT = "符合"
    PARTIAL = "部分符合"
    NON_COMPLIANT = "不符合"
    NOT_APPLICABLE = "不适用"
    UNCOLLECTED = "未采集"


VERDICT_TEXT: dict[Verdict, str] = {
    Verdict.COMPLIANT: "符合(1分)",
    Verdict.PARTIAL: "部分符合(0.5分)",
    Verdict.NON_COMPLIANT: "不符合(0分)",
    Verdict.NOT_APPLICABLE: "不适用",
    Verdict.UNCOLLECTED: "",
}

VERDICT_SCORE: dict[Verdict, float | None] = {
    Verdict.COMPLIANT: 1.0,
    Verdict.PARTIAL: 0.5,
    Verdict.NON_COMPLIANT: 0.0,
    Verdict.NOT_APPLICABLE: None,
    Verdict.UNCOLLECTED: None,
}

TEXT_TO_VERDICT: dict[str, Verdict] = {text: verdict for verdict, text in VERDICT_TEXT.items()}


def to_text(verdict: Verdict) -> str:
    return VERDICT_TEXT[verdict]


def from_text(text: str) -> Verdict:
    if text not in TEXT_TO_VERDICT:
        raise ValueError(f"未知的符合情况文本：{text!r}")
    return TEXT_TO_VERDICT[text]
