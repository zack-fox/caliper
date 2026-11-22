"""界面骨架自检：离屏装配七页工作台、切换导航、步骤状态与主题。"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtGui import QColor, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from app.controller import AppController  # noqa: E402
from app.screens.dialogs import EvidenceReviewDialog  # noqa: E402
from app.screens.results import ResultsScreen  # noqa: E402
from app.shell.app_shell import AppShell  # noqa: E402
from app.shell.navigation import NAV_STEPS, workflow_steps  # noqa: E402
from app.theme.theme import ThemeManager  # noqa: E402
from app.theme.tokens import SIDEBAR_EXPANDED_WIDTH, SIDEBAR_WIDTH  # noqa: E402
from core.model.entities import Asset, AssetRun, ItemResult, RunResult  # noqa: E402
from core.contracts.verdict import Verdict  # noqa: E402

EXPECTED_KEYS = [
    "overview",
    "evidence",
    "results",
    "issues",
    "risk",
    "export",
    "rules",
]


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
    assert [step.key for step in NAV_STEPS] == EXPECTED_KEYS
    assert [step.key for step in NAV_STEPS] == list(shell.pages.keys())
    assert shell.stack.count() == 7


def test_workflow_steps_are_six_projects(shell):
    assert [step.key for step in workflow_steps()] == EXPECTED_KEYS[:6]
    assert all(step.section == "项目" for step in workflow_steps())


def test_navigation_switches_page(shell):
    for step in NAV_STEPS:
        assert shell.go(step.key) is True
        assert shell.stack.currentWidget() is shell.pages[step.key]


def test_unknown_route_keeps_current_page(shell):
    assert shell.go("results") is True
    current = shell.stack.currentWidget()
    assert shell.go("nope") is False
    assert shell.stack.currentWidget() is current
    assert shell.go("risk") is True


def test_sidebar_groups_and_collapse(shell):
    sections = [
        label.text()
        for label in shell.sidebar.findChildren(QLabel)
        if label.objectName() == "nav_section"
    ]
    assert "项目" in sections
    assert "工具" in sections
    assert len(shell.sidebar._buttons) == 7

    shell.sidebar.set_collapsed(True)
    assert shell.sidebar.is_collapsed() is True
    assert shell.sidebar.width() == SIDEBAR_WIDTH
    shell.sidebar.set_collapsed(False)
    assert shell.sidebar.is_collapsed() is False
    assert shell.sidebar.width() == SIDEBAR_EXPANDED_WIDTH


def test_stepbar_states_apply_property(shell):
    shell.stepbar.set_states({"overview": "done", "risk": "blocked"})
    assert shell.stepbar._buttons["overview"].property("state") == "done"
    assert shell.stepbar._buttons["risk"].property("state") == "blocked"
    assert shell.stepbar._buttons["export"].property("state") == "todo"
    assert shell.go("risk") is True
    assert shell.stepbar._buttons["risk"].isChecked()


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


def test_results_screen_surfaces_run_diagnostics(qapp):
    controller = AppController()
    asset = Asset(
        device_name="诊断设备",
        ip="192.0.2.21",
        importance="一般",
        guide="三级-安全通用要求",
    )
    item = ItemResult(
        item_id="L3-CES1-01",
        seq=1,
        control_point="身份鉴别",
        importance="重要",
        verdict=Verdict.UNCOLLECTED,
        note="未采集：规则尚未实现",
    )
    controller.run_result = RunResult(
        project=controller.project,
        asset_runs=[
            AssetRun(
                asset=asset,
                items=[item],
                diagnostics=["1 个检查块没有映射，未参与自动判定"],
            )
        ],
    )
    screen = ResultsScreen(controller)
    assert not screen.diagnostic_banner.isHidden()
    assert "规则覆盖" in screen.diagnostic_summary.text()
    assert screen._diagnostic_entries == [
        ("诊断设备", "1 个检查块没有映射，未参与自动判定")
    ]
    screen.close()
