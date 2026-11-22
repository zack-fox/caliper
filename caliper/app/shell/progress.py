"""项目步骤状态：顶部步骤条与概述页共用同一取值口径。"""

from __future__ import annotations

PROJECT_STEP_KEYS: tuple[str, ...] = (
    "overview",
    "evidence",
    "results",
    "issues",
    "risk",
    "export",
)


def step_states(
    has_assets: bool, has_result: bool, pending_major: int
) -> dict[str, str]:
    """按当前批次返回六个项目步骤的 done / todo / blocked 状态。"""
    blocked = "blocked" if pending_major > 0 else "done"
    if has_result:
        return {
            "overview": "done",
            "evidence": "done",
            "results": "done",
            "issues": "done",
            "risk": blocked,
            "export": blocked,
        }
    return {
        "overview": "done" if has_assets else "todo",
        "evidence": "todo",
        "results": "todo",
        "issues": "todo",
        "risk": "todo",
        "export": "todo",
    }
