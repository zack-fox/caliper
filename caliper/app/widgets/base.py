"""通用界面组件：卡片、统计卡、徽章、页头、空状态与布局助手。

只做外观与组合，不承载业务逻辑，保证各屏幕视觉一致。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.theme.theme import restyle

TONES = ("ok", "warn", "bad", "info", "neutral", "ai")


def hbox(*widgets: QWidget, spacing: int = 8, margins: tuple[int, int, int, int] = (0, 0, 0, 0)):
    """水平布局快捷构造。"""
    layout = QHBoxLayout()
    layout.setSpacing(spacing)
    layout.setContentsMargins(*margins)
    for widget in widgets:
        if widget is None:
            layout.addStretch(1)
        elif isinstance(widget, int):
            layout.addSpacing(widget)
        else:
            layout.addWidget(widget)
    return layout


def vbox(*widgets: QWidget, spacing: int = 8, margins: tuple[int, int, int, int] = (0, 0, 0, 0)):
    """垂直布局快捷构造。"""
    layout = QVBoxLayout()
    layout.setSpacing(spacing)
    layout.setContentsMargins(*margins)
    for widget in widgets:
        if widget is None:
            layout.addStretch(1)
        elif isinstance(widget, int):
            layout.addSpacing(widget)
        else:
            layout.addWidget(widget)
    return layout


def divider() -> QFrame:
    line = QFrame()
    line.setObjectName("divider")
    line.setFixedHeight(1)
    return line


class Badge(QLabel):
    """小徽章：语义色调由 ``tone`` 决定。"""

    def __init__(self, text: str = "", tone: str = "neutral", parent=None) -> None:
        super().__init__(text, parent)
        self.setObjectName("badge")
        self.setAlignment(Qt.AlignCenter)
        self.set_tone(tone)

    def set_tone(self, tone: str) -> None:
        self.setProperty("tone", tone if tone in TONES else "neutral")
        restyle(self)

    def set_text(self, text: str, tone: str | None = None) -> None:
        self.setText(text)
        if tone is not None:
            self.set_tone(tone)


class Chip(QLabel):
    """中性信息胶囊。"""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setObjectName("chip")
        self.setAlignment(Qt.AlignCenter)


class Card(QFrame):
    """白底卡片，可选头部（标题 + 副标题 + 右侧操作）。"""

    def __init__(
        self,
        title: str = "",
        subtitle: str = "",
        parent=None,
        *,
        paddings: tuple[int, int, int, int] = (16, 14, 16, 16),
    ) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(*paddings)
        self._outer.setSpacing(10)

        self.header: QHBoxLayout | None = None
        if title:
            self.header = QHBoxLayout()
            self.header.setSpacing(8)
            self.title_label = QLabel(title)
            self.title_label.setObjectName("section_title")
            self.subtitle_label = QLabel(subtitle)
            self.subtitle_label.setObjectName("section_sub")
            self.subtitle_label.setVisible(bool(subtitle))
            self.header.addWidget(self.title_label)
            self.header.addWidget(self.subtitle_label)
            self.header.addStretch(1)
            self._outer.addLayout(self.header)

        self.body = QVBoxLayout()
        self.body.setSpacing(8)
        self._outer.addLayout(self.body, 1)

    def add_action(self, widget: QWidget) -> None:
        """把控件放到卡片头部右侧。"""
        if self.header is not None:
            self.header.addWidget(widget)

    def set_subtitle(self, text: str) -> None:
        if self.header is not None:
            self.subtitle_label.setText(text)
            self.subtitle_label.setVisible(bool(text))

    def add(self, widget: QWidget, stretch: int = 0) -> None:
        self.body.addWidget(widget, stretch)


class StatCard(QFrame):
    """统计卡：大数字 + 标签 + 提示。"""

    def __init__(self, label: str, value: str = "—", hint: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("stat_card")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(2)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("stat_value")
        self.label_label = QLabel(label)
        self.label_label.setObjectName("stat_label")
        self.hint_label = QLabel(hint)
        self.hint_label.setObjectName("stat_hint")
        self.hint_label.setVisible(bool(hint))
        layout.addWidget(self.value_label)
        layout.addWidget(self.label_label)
        layout.addWidget(self.hint_label)

    def set_value(self, value: str, hint: str | None = None) -> None:
        self.value_label.setText(value)
        if hint is not None:
            self.hint_label.setText(hint)
            self.hint_label.setVisible(bool(hint))


class PageHeader(QWidget):
    """页面头部：标题 + 说明 + 右侧操作区。"""

    def __init__(self, title: str, subtitle: str = "", parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        texts = QVBoxLayout()
        texts.setSpacing(2)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("page_title")
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("page_sub")
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setVisible(bool(subtitle))
        texts.addWidget(self.title_label)
        texts.addWidget(self.subtitle_label)
        layout.addLayout(texts, 1)

        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        layout.addLayout(self.actions)

    def add_action(self, widget: QWidget) -> None:
        self.actions.addWidget(widget)

    def set_subtitle(self, text: str) -> None:
        self.subtitle_label.setText(text)
        self.subtitle_label.setVisible(bool(text))


class EmptyState(QWidget):
    """空状态：居中提示。"""

    def __init__(self, title: str, hint: str = "", parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 40, 24, 40)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignCenter)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("section_title")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.hint_label = QLabel(hint)
        self.hint_label.setObjectName("muted")
        self.hint_label.setAlignment(Qt.AlignCenter)
        self.hint_label.setWordWrap(True)
        self.hint_label.setVisible(bool(hint))
        layout.addWidget(self.title_label)
        layout.addWidget(self.hint_label)

    def set_text(self, title: str, hint: str = "") -> None:
        self.title_label.setText(title)
        self.hint_label.setText(hint)
        self.hint_label.setVisible(bool(hint))


def scrollable(widget: QWidget) -> QWidget:
    """为长内容套一层滚动容器。"""
    from PySide6.QtWidgets import QScrollArea

    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setWidget(widget)
    return area
