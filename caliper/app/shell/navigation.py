"""导航模型：工作流五步（四步主流程 + 规则库）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NavStep:
    key: str
    label: str
    numeral: str
    section: str
    hint: str


NAV_STEPS: tuple[NavStep, ...] = (
    NavStep("evidence", "证据与资产", "1", "工作流", "导入采集日志与资产记录表，自动解析"),
    NavStep("results", "结果记录", "2", "工作流", "逐项核对判定结果与证据原文"),
    NavStep("issues", "问题与重大", "3", "工作流", "汇总问题清单，确认重大安全隐患"),
    NavStep("export", "导出与设置", "4", "工作流", "独立导出四张表，维护运行设置"),
    NavStep("rules", "规则库", "", "规则", "浏览控制项、判例与采集脚本映射"),
)

STEP_BY_KEY: dict[str, NavStep] = {step.key: step for step in NAV_STEPS}


def workflow_steps() -> tuple[NavStep, ...]:
    return tuple(step for step in NAV_STEPS if step.section == "工作流")


def rule_steps() -> tuple[NavStep, ...]:
    return tuple(step for step in NAV_STEPS if step.section == "规则")
