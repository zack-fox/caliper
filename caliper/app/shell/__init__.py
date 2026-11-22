"""应用外壳组件：导航模型、顶栏、侧栏、步骤条、状态栏与 AI 抽屉。"""

from app.shell.ai_drawer import AiDrawer
from app.shell.app_shell import AppShell
from app.shell.navigation import NAV_STEPS, NavStep, rule_steps, workflow_steps
from app.shell.sidebar import Sidebar
from app.shell.statusbar import AppStatusBar
from app.shell.stepbar import StepBar
from app.shell.topbar import TopBar

__all__ = [
    "AiDrawer",
    "AppShell",
    "AppStatusBar",
    "NAV_STEPS",
    "NavStep",
    "Sidebar",
    "StepBar",
    "TopBar",
    "rule_steps",
    "workflow_steps",
]
