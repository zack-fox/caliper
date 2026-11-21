"""仓库自检：契约里能用静态检查表达的规则。

- core 内不得出现 "packs/" 字面量（pack 路径只能来自项目配置/命令行）。
- core/app/adapters 不得引入网络或模型 SDK。
- app 不得自己构造 Verdict（判定只能来自 core）。
"""

from __future__ import annotations

import re
from pathlib import Path

FORBIDDEN_IMPORTS = re.compile(
    r"^\s*(?:import|from)\s+(openai|anthropic|requests|httpx)\b", re.MULTILINE
)
VERDICT_BUILD = re.compile(r"\bVerdict\(")


def _python_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    problems: list[str] = []

    for path in _python_files(root / "core"):
        if path.name == "selfcheck.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "packs/" in text:
            problems.append(f"{path.relative_to(root)}：core 内不得出现 packs/ 字面量")

    for folder in ("core", "app", "adapters"):
        for path in _python_files(root / folder):
            text = path.read_text(encoding="utf-8")
            for match in FORBIDDEN_IMPORTS.finditer(text):
                problems.append(
                    f"{path.relative_to(root)}：禁止引入网络/模型依赖 {match.group(1)}"
                )
            if folder == "app" and VERDICT_BUILD.search(text):
                problems.append(f"{path.relative_to(root)}：app 内不得构造 Verdict")

    if problems:
        for problem in problems:
            print(f"[失败] {problem}")
        return 1
    print("[OK] 静态自检：无 packs/ 字面量、无网络依赖、app 未构造 Verdict")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
