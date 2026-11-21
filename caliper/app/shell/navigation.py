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
    NavStep("evidence", "项目与材料", "1", "工作流", "管理项目资料并导入现场材料"),
    NavStep("results", "测评记录", "2", "工作流", "编辑记录表内容并核对证据依据"),
    NavStep("issues", "问题与重大", "", "后续", "汇总问题清单，确认重大安全隐患"),
    NavStep("export", "导出记录表", "3", "工作流", "校验并导出公司格式的测评记录表"),
    NavStep("rules", "规则库", "", "后续", "浏览控制项、判例与采集脚本映射"),
)

STEP_BY_KEY: dict[str, NavStep] = {step.key: step for step in NAV_STEPS}


def workflow_steps() -> tuple[NavStep, ...]:
    return tuple(step for step in NAV_STEPS if step.section == "工作流")


def rule_steps() -> tuple[NavStep, ...]:
    return tuple(step for step in NAV_STEPS if step.section == "规则")
