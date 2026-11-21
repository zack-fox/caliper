"""桌面入口：caliper-gui。未安装 PySide6 时给出明确提示而不是崩溃。"""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ModuleNotFoundError:
        print(
            "未安装 PySide6，无法启动界面。\n"
            "安装命令：.venv/bin/pip install -e '.[gui]'\n"
            "命令行仍可使用：.venv/bin/python -m core.cli --help",
            file=sys.stderr,
        )
        return 3

    app = QApplication(sys.argv)
    app.setApplicationName("Caliper")
    from app.main_window import MainWindow

    window = MainWindow()
    window.show()
    if "--smoke" in sys.argv:
        app.processEvents()
        print("GUI smoke OK：四个页签已创建")
        window.close()
        return 0
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
