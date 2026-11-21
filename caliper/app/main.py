"""Caliper 桌面端入口。

用法：
    python -m app.main            # 打开图形界面
    python -m app.main --smoke    # 离屏自检：装配外壳后立即退出
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from app.controller import AppController
from app.shell.app_shell import AppShell
from app.theme.theme import ThemeManager
from app.theme.tokens import APP_NAME

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
        print(f"[smoke] pages={len(shell.pages)} keys={keys}")
        print(f"[smoke] theme={theme.current()} title={shell.windowTitle()}")
        return 0

    shell.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
