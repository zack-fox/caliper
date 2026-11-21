"""设计令牌：配色、字体、间距、圆角。

配色与已审核的前端原型一致（深色侧栏 + 蓝色主色 + 语义状态色）。
QSS 模板中出现的所有颜色必须能在 ``COLORS`` 中找到（``app.theme.ui_lint`` 强制）。
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 浅色（默认）
# ---------------------------------------------------------------------------
PALETTE_LIGHT: dict[str, str] = {
    # 基础面
    "bg": "#f4f6f9",
    "surface": "#ffffff",
    "surface_alt": "#fafbfd",
    "surface_sunken": "#f8fafd",
    "border": "#e5e9f0",
    "border_strong": "#d6dce6",
    "line_soft": "#eef1f5",
    # 文字
    "text": "#111a27",
    "text_secondary": "#48566b",
    "muted": "#8a96a8",
    "white": "#ffffff",
    # 主色
    "primary": "#1f5eff",
    "primary_hover": "#12409e",
    "primary_soft": "#eaf0ff",
    "primary_ink": "#12409e",
    # 语义
    "success": "#12a76a",
    "success_soft": "#e6f7ef",
    "success_ink": "#0b7a4d",
    "warning": "#d98300",
    "warning_soft": "#fff3df",
    "warning_ink": "#8a5a00",
    "danger": "#d94040",
    "danger_soft": "#fdeaea",
    "danger_ink": "#a32626",
    "neutral": "#6b7a90",
    "neutral_soft": "#eef1f5",
    "ai": "#7a3ff0",
    "ai_soft": "#f2ecff",
    "ai_ink": "#5b28c8",
    # 侧栏 / 顶栏（深海军蓝）
    "nav": "#131d2b",
    "nav_alt": "#1b2738",
    "nav_text": "#c3cddd",
    "nav_text_strong": "#ffffff",
    "nav_border": "#0c141f",
    "nav_section": "#7c8798",
    # 交互
    "selection": "#eaf0ff",
    "row_alt": "#fafbfd",
    "header_bg": "#fafbfd",
    # 代码 / 证据原文
    "code_bg": "#0f1622",
    "code_text": "#7fd9c0",
    "upload_border": "#b9cdfa",
    "status_text": "#5d6b7e",
}
# 说明：upload_border / status_text / code_* 仅用于浅色；深色下使用同值以保持一致。

# ---------------------------------------------------------------------------
# 深色
# ---------------------------------------------------------------------------
PALETTE_DARK: dict[str, str] = {
    "bg": "#0f1115",
    "surface": "#181b22",
    "surface_alt": "#20242d",
    "surface_sunken": "#14171c",
    "border": "#2a2f3a",
    "border_strong": "#3a4050",
    "line_soft": "#232833",
    "text": "#e6e8ec",
    "text_secondary": "#a1a7b3",
    "muted": "#6b7280",
    "white": "#ffffff",
    "primary": "#5b8def",
    "primary_hover": "#7ea6f5",
    "primary_soft": "#1e2a45",
    "primary_ink": "#9dbcf7",
    "success": "#34d399",
    "success_soft": "#14352a",
    "success_ink": "#6ee7b7",
    "warning": "#fbbf24",
    "warning_soft": "#3a2e10",
    "warning_ink": "#fcd34d",
    "danger": "#f87171",
    "danger_soft": "#3a1a1a",
    "danger_ink": "#fca5a5",
    "neutral": "#8a96a8",
    "neutral_soft": "#20242d",
    "ai": "#a78bfa",
    "ai_soft": "#261a45",
    "ai_ink": "#c4b5fd",
    "nav": "#0b0f16",
    "nav_alt": "#161d29",
    "nav_text": "#a9b4c6",
    "nav_text_strong": "#ffffff",
    "nav_border": "#05080c",
    "nav_section": "#66717f",
    "selection": "#1e2a45",
    "row_alt": "#14171c",
    "header_bg": "#14171c",
    "code_bg": "#0b1017",
    "code_text": "#7fd9c0",
    "upload_border": "#35507f",
    "status_text": "#7b8794",
}

PALETTES: dict[str, dict[str, str]] = {"light": PALETTE_LIGHT, "dark": PALETTE_DARK}

# ui_lint 允许的全集（浅色 + 深色合并，去重保序）
COLORS: dict[str, str] = {}
for _palette in PALETTES.values():
    for _key, _value in _palette.items():
        COLORS.setdefault(_key, _value)

# ---------------------------------------------------------------------------
# 字体 / 间距 / 圆角
# ---------------------------------------------------------------------------
FONT_FAMILY = '"PingFang SC", "Helvetica Neue", "Microsoft YaHei", Arial, sans-serif'
FONT_MONO = '"SF Mono", "Cascadia Mono", Menlo, Consolas, monospace'

FONTS: dict[str, str] = {
    "family": FONT_FAMILY,
    "mono": FONT_MONO,
    "size_xs": "11px",
    "size_sm": "12px",
    "size_md": "13px",
    "size_lg": "15px",
    "size_xl": "17px",
    "size_2xl": "24px",
}

SPACING: dict[str, int] = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 20, "xxl": 24, "xxxl": 32}

RADIUS: dict[str, int] = {"xs": 4, "sm": 6, "md": 8, "lg": 10, "pill": 999}

# 窗口默认尺寸
WINDOW_SIZE = (1680, 1000)
SIDEBAR_WIDTH = 58
TOPBAR_HEIGHT = 54
STATUS_HEIGHT = 26
CONTENT_MARGIN = 20

# ---------------------------------------------------------------------------
# 业务常量
# ---------------------------------------------------------------------------
# 资产类型（等保常见 10 类）
ASSET_TYPES: tuple[str, ...] = (
    "业务应用",
    "服务器",
    "网络设备",
    "安全设备",
    "终端设备",
    "数据库",
    "中间件",
    "存储设备",
    "网络链路",
    "其他",
)

# 安全域（等保 2.0 十大类）
SECURITY_DOMAINS: tuple[str, ...] = (
    "安全物理环境",
    "安全通信网络",
    "安全区域边界",
    "安全计算环境",
    "安全管理中心",
    "安全管理制度",
    "安全管理机构",
    "安全管理人员",
    "安全建设管理",
    "安全运维管理",
)

APP_NAME = "Caliper"
APP_SUBTITLE = "等保测评取证助手"
APP_VERSION = "2.0.0"
