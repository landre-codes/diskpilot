"""Barra de título própria, arrastável e com controles de janela."""

from __future__ import annotations

import time

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QWidget,
)

from .buttons import IconButton


class _ElidedTitle(QLabel):
    """QLabel que encolhe com reticências em vez de empurrar o layout."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._full = text
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.setMinimumWidth(0)
        self.setWordWrap(False)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(22, super().minimumSizeHint().height())

    def natural_width(self) -> int:
        """Largura do texto completo, mesmo quando o rótulo está elidido."""
        return self.fontMetrics().horizontalAdvance(self._full) + 2

    def _apply_elide(self) -> None:
        metrics = self.fontMetrics()
        text = metrics.elidedText(self._full, Qt.ElideRight, max(12, self.width()))
        if text != super().text():
            super().setText(text)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_elide()

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.FontChange:
            self._apply_elide()


class TitleBar(QFrame):
    minimizeRequested = Signal()
    maximizeRequested = Signal()
    closeRequested = Signal()
    themeRequested = Signal()
    menuRequested = Signal()
    dragStarted = Signal(QPoint)
    dragMoved = Signal(QPoint)
    dragFinished = Signal()

    def __init__(self, app_title: str, tagline: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("TitleBar")
        self.setFixedHeight(52)
        self.setMinimumWidth(0)
        self.setMouseTracking(True)
        self._maximized = False
        self._last_press_time = 0.0
        self._last_press_pos = QPoint()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 8, 0)
        lay.setSpacing(6)

        self.menu_button = IconButton(
            "menu", "Recolher menu (Ctrl+B)", self, 20, 32, "primary"
        )
        self.menu_button.clicked.connect(self.menuRequested)
        lay.addWidget(self.menu_button, 0, Qt.AlignVCenter)

        self.app_title = _ElidedTitle(app_title, self)
        self.app_title.setObjectName("AppTitle")
        self.app_title.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        lay.addWidget(self.app_title, 0, Qt.AlignVCenter)

        # O slogan é uma camada própria, posicionada no centro exato da barra.
        # Ele não participa do layout para não ser deslocado pela largura dos
        # botões da direita; também não intercepta cliques (arraste/duplo clique).
        self.tagline = _ElidedTitle(tagline.upper(), self)
        self.tagline.setObjectName("AppStatus")
        self.tagline.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.tagline.setAlignment(Qt.AlignCenter)
        self.tagline.raise_()

        lay.addStretch(1)

        self.theme_button = IconButton(
            "weather-night", "Ativar tema claro", self, 18, 32, "primary"
        )
        self.theme_button.clicked.connect(self.themeRequested)
        lay.addWidget(self.theme_button, 0, Qt.AlignVCenter)

        sep = QFrame(self)
        sep.setObjectName("VSep")
        sep.setFixedSize(1, 18)
        lay.addSpacing(4)
        lay.addWidget(sep, 0, Qt.AlignVCenter)
        lay.addSpacing(4)

        self.minimize_button = IconButton(
            "window-minimize",
            "Minimizar",
            self,
            16,
            QSize(44, 32),
            "primary",
            object_name="WindowButton",
        )
        self.minimize_button.clicked.connect(self.minimizeRequested)
        lay.addWidget(self.minimize_button, 0, Qt.AlignVCenter)

        self.maximize_button = IconButton(
            "window-maximize",
            "Maximizar",
            self,
            16,
            QSize(44, 32),
            "primary",
            object_name="WindowButton",
        )
        self.maximize_button.clicked.connect(self.maximizeRequested)
        lay.addWidget(self.maximize_button, 0, Qt.AlignVCenter)

        self.close_button = IconButton(
            "close",
            "Fechar",
            self,
            16,
            QSize(44, 32),
            "#ffffff",
            object_name="WindowClose",
        )
        self.close_button.clicked.connect(self.closeRequested)
        lay.addWidget(self.close_button, 0, Qt.AlignVCenter)

        for widget in (self.app_title, self.tagline):
            widget.setMouseTracking(False)

    def set_maximized(self, maximized: bool) -> None:
        self._maximized = maximized
        self.maximize_button.set_icon_name(
            "window-restore" if maximized else "window-maximize"
        )
        self.maximize_button.setToolTip("Restaurar" if maximized else "Maximizar")

    def set_theme(self, key: str) -> None:
        if key == "light":
            self.theme_button.set_icon_name("weather-night")
            self.theme_button.setToolTip("Ativar tema escuro")
        else:
            self.theme_button.set_icon_name("white-balance-sunny")
            self.theme_button.setToolTip("Ativar tema claro")
        self._place_tagline()

    def set_sidebar_collapsed(self, collapsed: bool) -> None:
        self.menu_button.set_icon_name("menu-open" if collapsed else "menu")
        self.menu_button.setToolTip(
            "Expandir menu (Ctrl+B)" if collapsed else "Recolher menu (Ctrl+B)"
        )

    def _place_tagline(self) -> None:
        """Centraliza o slogan no meio exato da barra, sem cobrir os controles."""
        layout = self.layout()
        if layout is not None:
            layout.activate()
        center_x = self.width() // 2
        left_edge = self.app_title.geometry().right() + 14
        right_edge = self.theme_button.geometry().left() - 14
        room = min(center_x - left_edge, right_edge - center_x)
        if room < 24:
            self.tagline.hide()
            return
        width = min(self.tagline.natural_width(), room * 2)
        height = self.tagline.fontMetrics().height()
        self.tagline.setGeometry(
            center_x - width // 2, (self.height() - height) // 2, width, height
        )
        self.tagline.setVisible(True)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._place_tagline()

    # ------------------------------------------------------------- arraste
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            now = time.monotonic()
            pos = event.position().toPoint()
            # Fallback de duplo clique: em alguns estados (janela maximizada
            # por nós, telas com escala) o Windows entrega dois pressionamentos
            # comuns em vez de um MouseButtonDblClick. O comportamento precisa
            # ser o mesmo de qualquer outra janela.
            interval = QApplication.doubleClickInterval() / 1000.0
            tolerance = max(12, QApplication.startDragDistance())
            if (
                self._last_press_time
                and now - self._last_press_time <= interval
                and (pos - self._last_press_pos).manhattanLength() <= tolerance
            ):
                self._last_press_time = 0.0
                self.maximizeRequested.emit()
                event.accept()
                return
            self._last_press_time = now
            self._last_press_pos = pos
            self.dragStarted.emit(event.globalPosition().toPoint())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.buttons() & Qt.LeftButton:
            self.dragMoved.emit(event.globalPosition().toPoint())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.dragFinished.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._last_press_time = 0.0
            self.maximizeRequested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
