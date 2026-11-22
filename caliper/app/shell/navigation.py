"""导航模型：七页工作台（六个项目步骤 + 规则库工具）。"""

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
    NavStep("overview", "项目概述", "", "项目", "项目上下文、设备与核查进度总览"),
    NavStep("evidence", "材料与资产", "", "项目", "导入现场材料并维护设备资产"),
    NavStep("results", "现场核查", "", "项目", "逐项核对记录并确认证据依据"),
    NavStep("issues", "问题与整改", "", "项目", "汇总问题清单与整改建议"),
    NavStep("risk", "风险与结论", "", "项目", "确认高风险候选与重大隐患"),
    NavStep("export", "导出交付", "", "项目", "校验导出门禁并交付成果物"),
    NavStep("rules", "规则库", "", "工具", "浏览控制项、判例与采集脚本映射"),
)

STEP_BY_KEY: dict[str, NavStep] = {step.key: step for step in NAV_STEPS}


def workflow_steps() -> tuple[NavStep, ...]:
    """项目分组的六个步骤，供步骤条与状态统计使用。"""
    return tuple(step for step in NAV_STEPS if step.section == "项目")


def rule_steps() -> tuple[NavStep, ...]:
    """工具分组的导航项（规则库）。"""
    return tuple(step for step in NAV_STEPS if step.section == "工具")
