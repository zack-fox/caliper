"""Caliper 桌面端入口。

用法：
    python -m app.main            # 打开图形界面
    python -m app.main --smoke    # 离屏自检：装配外壳后立即退出
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from app.controller import AppController
from app.shell.app_shell import AppShell
from app.theme.theme import ThemeManager
from app.theme.tokens import APP_NAME
from core.render.result_record import find_template

ORGANISATION = "Caliper"
THEME_KEY = "ui/theme"


def _settings() -> QSettings:
    return QSettings(ORGANISATION, APP_NAME)


def build_theme(app: QApplication) -> ThemeManager:
    settings = _settings()

    def get_pref() -> str:
        return str(settings.value(THEME_KEY, "light"))

    def set_pref(name: str) -> None:
        settings.setValue(THEME_KEY, name)

    return ThemeManager(app, get_pref=get_pref, set_pref=set_pref)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    smoke = "--smoke" in argv

    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORGANISATION)

    theme = build_theme(app)
    theme.apply()

    shell = AppShell(theme=theme)
    if smoke:
        keys = " ".join(shell.pages.keys())
        try:
            pack = shell.controller.load_pack()
            templates = [
                find_template(pack.root, name)
                for name in (
                    "result_record.xlsx",
                    "asset_record.xlsx",
                    "issue_summary.xlsx",
                    "major_risk.xlsx",
                )
            ]
            details = [
                f"[smoke] pages={len(shell.pages)} keys={keys}",
                f"[smoke] theme={theme.current()} title={shell.windowTitle()}",
                f"[smoke] pack={pack.meta.name} version={pack.meta.version}",
                f"[smoke] templates={len(templates)}",
            ]
            result = "\n".join(details) + "\n"
            print(result, end="")
            report = _smoke_report_path(argv)
            if report:
                report.write_text(result, encoding="utf-8")
        except Exception as exc:
            message = f"[smoke] ERROR {type(exc).__name__}: {exc}\n"
            print(message, end="", file=sys.stderr)
            report = _smoke_report_path(argv)
            if report:
                report.write_text(message, encoding="utf-8")
            return 1
        return 0

    shell.show()
    return app.exec()


def _smoke_report_path(argv: list[str]) -> Path | None:
    for index, value in enumerate(argv):
        if value == "--smoke-report" and index + 1 < len(argv):
            return Path(argv[index + 1])
        if value.startswith("--smoke-report="):
            return Path(value.split("=", 1)[1])
    return None


if __name__ == "__main__":
    raise SystemExit(main())
