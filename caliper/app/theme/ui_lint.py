"""ui-lint：样式表里的颜色必须全部来自 tokens.COLORS。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from app.theme.tokens import COLORS

_COLOR_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    qss = (root / "app.qss").read_text(encoding="utf-8")
    allowed = {value.lower() for value in COLORS.values()}
    unknown = sorted({match.lower() for match in _COLOR_RE.findall(qss)} - allowed)
    if unknown:
        print(f"[失败] app.qss 使用了未登记的颜色：{', '.join(unknown)}", file=sys.stderr)
        return 1
    print(f"[OK] app.qss 颜色全部来自 tokens（{len(allowed)} 个令牌）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
