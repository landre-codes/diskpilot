"""Componentes visuais genéricos do shell (cards, cabeçalhos, chips, toast)."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..icons import icon
from ..theme import get_theme
from ..utils import short_path
from .buttons import IconButton


class ElidedLabel(QLabel):
    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._full_text = text
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(0)

    def setText(self, text: str) -> None:  # noqa: N802
        self._full_text = text
        self.setToolTip(text)
        self._refresh()

    def full_text(self) -> str:
        return self._full_text

    def _refresh(self) -> None:
        metrics = QFontMetrics(self.font())
        super().setText(
            metrics.elidedText(self._full_text, Qt.ElideMiddle, max(10, self.width()))
        )

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        return QSize(4, hint.height())

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        return QSize(4, hint.height())

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._refresh()


class IconLabel(QLabel):
    def __init__(
        self,
        icon_name: str,
        size: int = 22,
        color_role: str = "primary",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._icon_name = icon_name
        self._size = size
        self._role = color_role
        self.setFixedSize(size + 4, size + 4)
        self.setAlignment(Qt.AlignCenter)
        get_theme().changed.connect(self.refresh)
        self.refresh()

    def set_icon_name(self, name: str) -> None:
        self._icon_name = name
        self.refresh()

    def set_color_role(self, role: str) -> None:
        self._role = role
        self.refresh()

    def refresh(self, *_args: Any) -> None:
        pm = icon(self._icon_name, get_theme().color(self._role), self._size).pixmap(
            self._size, self._size
        )
        self.setPixmap(pm)


class PageHeader(QWidget):
    def __init__(
        self,
        title: str,
        subtitle: str = "",
        eyebrow: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)
        self.eyebrow = QLabel(eyebrow.upper())
        self.eyebrow.setObjectName("Eyebrow")
        self.eyebrow.setVisible(bool(eyebrow))
        self.title = QLabel(title)
        self.title.setObjectName("PageTitle")
        self.subtitle = QLabel(subtitle)
        self.subtitle.setObjectName("PageSubtitle")
        self.subtitle.setWordWrap(True)
        self.subtitle.setVisible(bool(subtitle))
        root.addWidget(self.eyebrow)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(16)
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(5)
        left.addWidget(self.title)
        left.addWidget(self.subtitle)
        row.addLayout(left, 1)
        self.actions = QHBoxLayout()
        self.actions.setContentsMargins(0, 0, 0, 0)
        self.actions.setSpacing(8)
        row.addLayout(self.actions, 0)
        root.addLayout(row)

    def add_action(self, widget: QWidget) -> None:
        self.actions.addWidget(widget)


class Divider(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Divider")
        self.setFixedHeight(1)


class DisclaimerBanner(QFrame):
    """Aviso persistente de somente leitura e responsabilidade."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("TintWarn")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(13, 9, 13, 9)
        lay.setSpacing(9)
        icon = IconLabel("alert-outline", 18, "warn", self)
        lay.addWidget(icon, 0, Qt.AlignTop)
        self.label = QLabel(text)
        self.label.setObjectName("Muted")
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.label, 1)


class Card(QFrame):
    """Card com cabeçalho opcional e corpo vertical."""

    def __init__(
        self,
        title: str = "",
        subtitle: str = "",
        parent: QWidget | None = None,
        padding: int = 18,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setAttribute(Qt.WA_Hover, True)
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(padding, padding, padding, padding)
        self._root.setSpacing(12)
        self.header_actions = QHBoxLayout()
        self.header_actions.setSpacing(6)
        self._heading: QWidget | None = None
        if title:
            self._heading = QWidget(self)
            h = QVBoxLayout(self._heading)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(2)
            t = QLabel(title)
            t.setObjectName("SectionTitle")
            h.addWidget(t)
            if subtitle:
                s = QLabel(subtitle)
                s.setObjectName("Muted")
                s.setWordWrap(True)
                h.addWidget(s)
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(self._heading, 1)
            row.addLayout(self.header_actions, 0)
            self._root.addLayout(row)
        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(10)
        self._root.addLayout(self.body, 1)

    def add_header_action(self, widget: QWidget) -> None:
        self.header_actions.addWidget(widget)


class StatCard(QFrame):
    clicked = Signal()

    def __init__(
        self,
        label: str,
        value: str = "—",
        hint: str = "",
        icon_name: str = "harddisk",
        tone: str = "primary",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("StatCard")
        self.setAttribute(Qt.WA_Hover, True)
        self.setMinimumHeight(116)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._tone = tone
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 15, 16, 14)
        lay.setSpacing(7)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        self.icon_tile = QFrame(self)
        self.icon_tile.setObjectName(
            "IconTile"
            if tone == "primary"
            else f"IconTile{tone.capitalize()}"
        )
        self.icon_tile.setFixedSize(40, 40)
        it = QHBoxLayout(self.icon_tile)
        it.setContentsMargins(0, 0, 0, 0)
        self.icon = IconLabel(icon_name, 21, tone if tone != "primary" else "primary")
        it.addWidget(self.icon, 0, Qt.AlignCenter)
        top.addWidget(self.icon_tile, 0)
        top.addStretch(1)
        self.badge = QLabel("")
        self.badge.setObjectName("Badge")
        self.badge.setVisible(False)
        top.addWidget(self.badge, 0, Qt.AlignTop)
        lay.addLayout(top)
        self.value = QLabel(value)
        self.value.setObjectName("Value")
        lay.addWidget(self.value)
        self.label = ElidedLabel(label)
        self.label.setObjectName("Muted")
        lay.addWidget(self.label)
        self.hint = ElidedLabel(hint)
        self.hint.setObjectName("Faint")
        self.hint.setVisible(bool(hint))
        lay.addWidget(self.hint)

    def set_value(self, value: str, hint: str | None = None) -> None:
        self.value.setText(value)
        if hint is not None:
            self.hint.setText(hint)
            self.hint.setVisible(bool(hint))

    def set_badge(self, text: str, tone: str = "info") -> None:
        self.badge.setText(text)
        self.badge.setObjectName(
            {
                "success": "BadgeSuccess",
                "warn": "BadgeWarn",
                "danger": "BadgeDanger",
                "info": "BadgeInfo",
            }.get(tone, "Badge")
        )
        self.badge.setVisible(bool(text))
        self.badge.style().unpolish(self.badge)
        self.badge.style().polish(self.badge)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class EmptyState(QFrame):
    def __init__(
        self,
        title: str,
        description: str,
        icon_name: str = "folder-search-outline",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("EmptyCard")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 42, 32, 42)
        lay.setSpacing(10)
        lay.setAlignment(Qt.AlignCenter)
        self.icon = IconLabel(icon_name, 42, "primary")
        lay.addWidget(self.icon, 0, Qt.AlignHCenter)
        self.title = QLabel(title)
        self.title.setObjectName("SectionTitle")
        self.title.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.title)
        self.description = QLabel(description)
        self.description.setObjectName("Muted")
        self.description.setAlignment(Qt.AlignCenter)
        self.description.setWordWrap(True)
        self.description.setMaximumWidth(520)
        lay.addWidget(self.description, 0, Qt.AlignHCenter)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        self.actions.setAlignment(Qt.AlignCenter)
        lay.addSpacing(4)
        lay.addLayout(self.actions)

    def add_action(self, widget: QWidget) -> None:
        self.actions.addWidget(widget)


class Chip(QFrame):
    removeRequested = Signal(str)

    def __init__(self, path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.path = path
        self.setObjectName("Pill")
        self.setFixedHeight(32)
        self.setToolTip(path)
        self.setAttribute(Qt.WA_Hover, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 5, 0)
        lay.setSpacing(6)
        self.icon = IconLabel("folder", 15, "primary", self)
        lay.addWidget(self.icon, 0, Qt.AlignVCenter)
        self.label = QLabel(short_path(path, 44))
        self.label.setObjectName("ChipText")
        lay.addWidget(self.label, 1, Qt.AlignVCenter)
        close = IconButton(
            "close",
            "Remover pasta",
            self,
            14,
            22,
            "danger",
            object_name="ChipClose",
        )
        close.set_normal_color("muted")
        close.clicked.connect(lambda: self.removeRequested.emit(self.path))
        lay.addWidget(close, 0, Qt.AlignVCenter)
        self._close = close


class Toast(QFrame):
    """Notificação flutuante com fade-in/fade-out."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 16, 10)
        lay.setSpacing(10)
        self.icon = IconLabel("check-circle-outline", 19, "success")
        lay.addWidget(self.icon)
        self.label = QLabel("")
        self.label.setWordWrap(False)
        lay.addWidget(self.label, 1)
        self._effect: QGraphicsOpacityEffect | None = None
        self._anim: QPropertyAnimation | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)
        self.hide()

    def present(self, text: str, kind: str = "success", duration: int = 3200) -> None:
        mapping = {
            "success": ("check-circle-outline", "success"),
            "info": ("information-outline", "info"),
            "warn": ("alert-outline", "warn"),
            "danger": ("alert-circle-outline", "danger"),
        }
        ico, role = mapping.get(kind, mapping["info"])
        self.icon._icon_name = ico
        self.icon._role = role
        self.icon.refresh()
        self.label.setText(text)
        self.adjustSize()
        self.setFixedWidth(min(max(280, self.sizeHint().width() + 10), 470))
        self.adjustSize()
        parent = self.parentWidget()
        if parent:
            self.move(
                max(14, parent.width() - self.width() - 22),
                max(14, parent.height() - self.height() - 22),
            )
        self.show()
        self.raise_()
        if self._effect is None:
            self._effect = QGraphicsOpacityEffect(self)
            self.setGraphicsEffect(self._effect)
        self._effect.setOpacity(0.0)
        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setDuration(180)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.start()
        self._timer.start(duration)

    def _fade_out(self) -> None:
        if self._effect is None:
            self.hide()
            return
        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setDuration(220)
        self._anim.setStartValue(self._effect.opacity())
        self._anim.setEndValue(0.0)
        self._anim.setEasingCurve(QEasingCurve.InCubic)
        self._anim.finished.connect(self.hide)
        self._anim.start()
