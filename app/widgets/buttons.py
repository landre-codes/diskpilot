"""Botões e campos reutilizáveis com ícones MDI e hover próprio."""

from __future__ import annotations

from typing import Any, Iterable

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPen
from PySide6.QtWidgets import (
    QLineEdit,
    QMenu,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from ..icons import icon
from ..theme import get_theme


def _repolish(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


class ActionButton(QPushButton):
    """Botão com texto + ícone MDI e cores de hover sincronizadas com o tema."""

    def __init__(
        self,
        text: str = "",
        icon_name: str = "",
        kind: str = "soft",
        parent: QWidget | None = None,
        icon_size: int = 18,
    ) -> None:
        super().__init__(text, parent)
        self._icon_name = icon_name
        self._kind = kind
        self._icon_size = icon_size
        self._hover = False
        self.setCursor(Qt.PointingHandCursor)
        self.setIconSize(QSize(icon_size, icon_size))
        self.setMinimumHeight(34)
        self.set_kind(kind)
        get_theme().changed.connect(self._sync_icon)
        self._sync_icon()

    def set_kind(self, kind: str) -> None:
        mapping = {
            "primary": "Primary",
            "ghost": "Ghost",
            "soft": "Soft",
            "danger": "DangerGhost",
            "link": "Link",
        }
        self._kind = kind
        self.setObjectName(mapping.get(kind, "Soft"))
        if kind == "primary":
            self.setMinimumHeight(36)
        elif kind == "link":
            self.setMinimumHeight(24)
        else:
            self.setMinimumHeight(34)
        _repolish(self)

    def set_icon_name(self, name: str) -> None:
        self._icon_name = name
        self._sync_icon()

    def _color_for_state(self) -> str:
        theme = get_theme()
        if self._kind == "primary":
            return theme.color("on_primary")
        if self._kind == "danger":
            return theme.color("danger")
        if self._hover:
            return theme.color("primary")
        return theme.color("text")

    def _sync_icon(self, *_args: Any) -> None:
        if not self._icon_name:
            return
        self.setIcon(icon(self._icon_name, self._color_for_state(), self._icon_size))

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self._sync_icon()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self._sync_icon()
        super().leaveEvent(event)


class IconButton(QPushButton):
    """Botão quadrado/apenas-ícone, usado na barra de título e toolbars."""

    def __init__(
        self,
        icon_name: str,
        tooltip: str = "",
        parent: QWidget | None = None,
        icon_size: int = 18,
        size: int | QSize = 32,
        hover_color: str = "primary",
        object_name: str = "IconButton",
    ) -> None:
        super().__init__(parent)
        self._icon_name = icon_name
        self._icon_size = icon_size
        self._hover_color = hover_color
        self._hover = False
        self._normal_color = "text"
        self.setObjectName(object_name)
        self.setToolTip(tooltip)
        self.setCursor(Qt.PointingHandCursor)
        if isinstance(size, QSize):
            self.setFixedSize(size)
        else:
            self.setFixedSize(size, size)
        self.setIconSize(QSize(icon_size, icon_size))
        get_theme().changed.connect(self._sync_icon)
        self._sync_icon()

    def set_icon_name(self, icon_name: str) -> None:
        self._icon_name = icon_name
        self._sync_icon()

    def set_normal_color(self, role: str) -> None:
        self._normal_color = role
        self._sync_icon()

    def _sync_icon(self, *_args: Any) -> None:
        role = self._hover_color if self._hover else self._normal_color
        color = role if role.startswith("#") else get_theme().color(role)
        self.setIcon(icon(self._icon_name, color, self._icon_size))

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self._sync_icon()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self._sync_icon()
        super().leaveEvent(event)


class NavButton(QWidget):
    """Aba vertical desenhada à mão para animar largura, ícone e texto."""

    clicked = Signal()

    def __init__(
        self,
        key: str,
        label: str,
        icon_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.key = key
        self.label = label
        self.icon_name = icon_name
        self._active = False
        self._hover = False
        self._ratio = 1.0
        self.setFixedHeight(46)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setToolTip(label)
        self.setAttribute(Qt.WA_Hover, True)
        get_theme().changed.connect(self.update)

    def set_active(self, active: bool) -> None:
        if self._active == active:
            return
        self._active = active
        self.update()

    def set_expansion(self, ratio: float) -> None:
        self._ratio = max(0.0, min(1.0, ratio))
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        theme = get_theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(theme.color("sidebar")))
        ratio = self._ratio

        if self._active:
            bg = theme.qcolor("primary", 31)
            p.setPen(Qt.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(QRectF(8, 3, w - 16, h - 6), 9, 9)
            p.setBrush(QColor(theme.color("primary")))
            p.drawRoundedRect(QRectF(8, (h - 20) / 2, 3, 20), 1.5, 1.5)
        elif self._hover:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.color("hover")))
            p.drawRoundedRect(QRectF(8, 3, w - 16, h - 6), 9, 9)

        if self.hasFocus():
            p.setPen(QPen(QColor(theme.color("primary")), 1, Qt.DotLine))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(8.5, 3.5, w - 17, h - 7), 9, 9)

        icon_color = theme.color(
            "primary" if self._active else ("text" if self._hover else "muted")
        )
        pm = icon(self.icon_name, icon_color, 21).pixmap(21, 21)
        x_expanded = 20.0
        x_collapsed = (w - 21) / 2.0
        x_icon = x_collapsed + (x_expanded - x_collapsed) * ratio
        p.drawPixmap(int(x_icon), (h - 21) // 2, pm)

        if ratio > 0.08:
            alpha = int(max(0.0, min(1.0, (ratio - 0.10) / 0.55)) * 255)
            color = QColor(theme.color("primary" if self._active else "text"))
            color.setAlpha(alpha)
            p.setPen(color)
            f = QFont("Segoe UI")
            f.setPixelSize(theme.fs(13))
            f.setWeight(QFont.DemiBold if self._active else QFont.Normal)
            p.setFont(f)
            text_x = 52
            available = max(0, w - text_x - 14)
            metrics = p.fontMetrics()
            txt = metrics.elidedText(self.label, Qt.ElideRight, available)
            p.drawText(
                QRectF(text_x, 0, available, h),
                Qt.AlignVCenter | Qt.AlignLeft,
                txt,
            )
        p.end()


class SearchField(QWidget):
    """Campo de busca com ícone MDI, limpar e debounce configurável."""

    searchChanged = Signal(str)

    def __init__(
        self,
        placeholder: str = "Pesquisar…",
        debounce_ms: int = 260,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._debounce_ms = debounce_ms
        self._leading = QIcon()
        self._clear = QIcon()
        self.edit = QLineEdit(self)
        self.edit.setObjectName("Search")
        self.edit.setPlaceholderText(placeholder)
        self.edit.setClearButtonEnabled(False)
        self.edit.setMinimumWidth(230)
        self._leading_action = self.edit.addAction(QIcon(), QLineEdit.LeadingPosition)
        self._clear_action = self.edit.addAction(QIcon(), QLineEdit.TrailingPosition)
        self._clear_action.setVisible(False)
        self._clear_action.triggered.connect(self.edit.clear)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(debounce_ms)
        self._timer.timeout.connect(self._emit_search)
        self.edit.textChanged.connect(self._on_text)
        self.edit.returnPressed.connect(self._emit_search)
        from PySide6.QtWidgets import QHBoxLayout

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.edit)
        get_theme().changed.connect(self._sync_icons)
        self._sync_icons()

    def _on_text(self, _text: str) -> None:
        self._clear_action.setVisible(bool(self.edit.text()))
        self._timer.start()

    def _emit_search(self) -> None:
        self._timer.stop()
        self.searchChanged.emit(self.edit.text().strip())

    def _sync_icons(self, *_args: Any) -> None:
        theme = get_theme()
        self._leading_action.setIcon(icon("magnify", theme.color("muted"), 18))
        self._clear_action.setIcon(icon("close-circle", theme.color("muted"), 17))

    def set_text(self, text: str) -> None:
        self.edit.setText(text)

    def text(self) -> str:
        return self.edit.text()

    def clear(self) -> None:
        self.edit.clear()

    def focus(self) -> None:
        self.edit.setFocus(Qt.ShortcutFocusReason)
        self.edit.selectAll()


class SelectButton(ActionButton):
    """Dropdown nativo estilizado (substitui QComboBox em filtros)."""

    changed = Signal(str)

    def __init__(
        self,
        icon_name: str,
        label: str = "",
        parent: QWidget | None = None,
        kind: str = "soft",
    ) -> None:
        super().__init__(label, icon_name, kind, parent)
        self._options: list[tuple[str, str, str]] = []
        self._current = ""
        self._chevron = True
        self.setMinimumWidth(158)
        self.clicked.connect(self._open)

    def set_chevron(self, visible: bool) -> None:
        self._chevron = visible
        if self._current:
            self.set_current(self._current, emit=False)

    def set_options(self, options: Iterable[tuple], current: str | None = None) -> None:
        parsed: list[tuple[str, str, str]] = []
        for option in options:
            if len(option) >= 3:
                parsed.append((str(option[0]), str(option[1]), str(option[2])))
            else:
                parsed.append((str(option[0]), str(option[1]), self._icon_name))
        self._options = parsed
        if current is None:
            current = self._current or (self._options[0][0] if self._options else "")
        self.set_current(current, emit=False)

    def set_current(self, value: str, emit: bool = True) -> None:
        self._current = value
        label = value
        icon_name = self._icon_name
        for key, text, option_icon in self._options:
            if key == value:
                label = text
                icon_name = option_icon or icon_name
                break
        super().setText(f"{label}   ▾" if self._chevron else label)
        if icon_name and icon_name != self._icon_name:
            self.set_icon_name(icon_name)
        if emit:
            self.changed.emit(value)

    def current(self) -> str:
        return self._current

    def _open(self) -> None:
        if not self._options:
            return
        theme = get_theme()
        menu = QMenu(self)
        for key, text, icon_name in self._options:
            action = QAction(text, menu)
            color = theme.color("primary" if key == self._current else "muted")
            action.setIcon(icon(icon_name, color, 16))
            action.triggered.connect(lambda _=False, k=key: self.set_current(k))
            menu.addAction(action)
        menu.exec(self.mapToGlobal(QPoint(0, self.height() + 5)))
        menu.deleteLater()
