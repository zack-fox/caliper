"""ui-lint：主题模板必须只使用 tokens 里登记的颜色，且渲染后不能残留占位符。"""

from __future__ import annotations

import re
import sys

from app.theme.theme import _QSS_TEMPLATE, render_qss
from app.theme.tokens import COLORS, PALETTES
_COLOR_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")
_PLACEHOLDER_RE = re.compile(r"@[a-z_]+@")
_TOKEN_RE = re.compile(r"@([a-z_]+)@")


def main() -> int:
    allowed = {
        value.lower() for palette in PALETTES.values() for value in palette.values()
    }
    failures: list[str] = []

    for name, palette in PALETTES.items():
        rendered = render_qss(palette)
        leftovers = sorted(set(_PLACEHOLDER_RE.findall(rendered)))
        if leftovers:
            failures.append(f"{name} 残留未替换占位符：{', '.join(leftovers)}")
        unknown = sorted({match.lower() for match in _COLOR_RE.findall(rendered)} - allowed)
        if unknown:
            failures.append(f"{name} 使用了未登记颜色：{', '.join(unknown)}")

    # 模板里出现的令牌名必须都在 COLORS 中，避免拼错后静默失效
    template_tokens = set(_TOKEN_RE.findall(_QSS_TEMPLATE)) - {"font_family", "font_mono"}
    missing = sorted(template_tokens - set(COLORS))
    if missing:
        failures.append(f"模板引用了未定义的令牌：{', '.join(missing)}")

    if failures:
        for line in failures:
            print(f"[失败] {line}", file=sys.stderr)
        return 1

    print(f"[OK] 主题模板校验通过：{len(template_tokens)} 个令牌 × {len(PALETTES)} 套调色板")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
