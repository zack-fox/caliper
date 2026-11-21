"""界面骨架自检：离屏装配外壳、切换五个页面、切换主题。"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtGui import QColor, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.controller import AppController  # noqa: E402
from app.screens.dialogs import EvidenceReviewDialog  # noqa: E402
from app.shell.app_shell import AppShell  # noqa: E402
from app.shell.navigation import NAV_STEPS  # noqa: E402
from app.theme.theme import ThemeManager  # noqa: E402
from core.model.entities import Asset  # noqa: E402


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


def test_evidence_review_dialog_previews_text_and_images(qapp, tmp_path):
    evidence_dir = tmp_path / "device-evidence"
    evidence_dir.mkdir()
    (evidence_dir / "capture.log").write_text(
        "# ===== Ubuntu baseline check =====\n"
        "===== RESULTS (collected) =====\n"
        "===== SYSTEM =====\n"
        "[01] Host info\n"
        "  hostname: review-host\n"
        "===== END OF REPORT =====\n",
        encoding="utf-8",
    )
    screenshot = QPixmap(24, 24)
    screenshot.fill(QColor("#2878d0"))
    assert screenshot.save(str(evidence_dir / "screen.png"))

    controller = AppController()
    controller.project = controller.project.model_copy(update={"evidence_root": tmp_path})
    asset = Asset(
        device_name="审阅设备",
        ip="192.0.2.20",
        importance="一般",
        guide="三级-安全通用要求",
        evidence_package=evidence_dir.name,
    )
    dialog = EvidenceReviewDialog(controller, asset)
    assert dialog.file_list.count() == 2
    assert "review-host" in dialog.text_preview.toPlainText()

    dialog.file_list.setCurrentRow(1)
    assert dialog.preview_stack.currentWidget() is dialog.image_preview
    assert dialog.image_preview.pixmap() is not None
    dialog.close()
