"""界面骨架自检：离屏装配外壳、切换五个页面、切换主题。"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.controller import AppController  # noqa: E402
from app.shell.app_shell import AppShell  # noqa: E402
from app.shell.navigation import NAV_STEPS  # noqa: E402
from app.theme.theme import ThemeManager  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def shell(qapp):
    prefs = {"name": "light"}
    theme = ThemeManager(
        qapp,
        get_pref=lambda: prefs["name"],
        set_pref=lambda name: prefs.update(name=name),
    )
    theme.apply()
    window = AppShell(AppController(), theme=theme)
    yield window
    window.close()


def test_shell_has_all_pages(shell):
    assert [step.key for step in NAV_STEPS] == list(shell.pages.keys())
    assert shell.stack.count() == len(NAV_STEPS)


def test_navigation_switches_page(shell):
    for step in NAV_STEPS:
        shell.go(step.key)
        assert shell.stack.currentWidget() is shell.pages[step.key]


def test_theme_toggle_roundtrip(shell):
    assert shell.theme is not None
    assert shell.theme.current() == "light"
    assert shell.theme.toggle() == "dark"
    assert shell.theme.current() == "dark"
    assert shell.theme.toggle() == "light"


def test_ui_lint_passes():
    from app.theme import ui_lint

    assert ui_lint.main() == 0
