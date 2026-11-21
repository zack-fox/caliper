"""骨架自检：核心包可导入、CLI 子命令可用、缺参非零退出。"""

from __future__ import annotations

import subprocess
import sys


def test_core_packages_importable() -> None:
    import core.checks  # noqa: F401
    import core.contracts  # noqa: F401
    import core.evidence  # noqa: F401
    import core.issues  # noqa: F401
    import core.items  # noqa: F401
    import core.judge  # noqa: F401
    import core.major  # noqa: F401
    import core.model  # noqa: F401
    import core.ports  # noqa: F401
    import core.render  # noqa: F401
    import core.rules  # noqa: F401
    import core.store  # noqa: F401


def test_cli_help_lists_all_subcommands() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "core.cli", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    for command in ("run", "parse", "explain", "export", "lint-rules", "golden"):
        assert command in result.stdout


def test_cli_run_requires_project() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "core.cli", "run"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2


def test_golden_without_cases_reports_usage() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "core.cli", "golden", "--dir", "fixtures/golden"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "金标准用例" in result.stderr
