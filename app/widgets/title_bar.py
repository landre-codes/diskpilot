"""Barra de título própria, arrastável e com controles de janela."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from .buttons import IconButton


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
        self.setMouseTracking(True)
        self._maximized = False
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 8, 0)
        lay.setSpacing(6)

        self.menu_button = IconButton(
            "menu", "Recolher menu (Ctrl+B)", self, 20, 32, "primary"
        )
        self.menu_button.clicked.connect(self.menuRequested)
        lay.addWidget(self.menu_button, 0, Qt.AlignVCenter)

        self.app_title = QLabel(app_title)
        self.app_title.setObjectName("AppTitle")
        self.app_title.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        lay.addWidget(self.app_title, 0, Qt.AlignVCenter)

        self.tagline = QLabel(tagline.upper())
        self.tagline.setObjectName("AppStatus")
        self.tagline.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        lay.addWidget(self.tagline, 0, Qt.AlignVCenter)
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

    def set_sidebar_collapsed(self, collapsed: bool) -> None:
        self.menu_button.set_icon_name("menu-open" if collapsed else "menu")
        self.menu_button.setToolTip(
            "Expandir menu (Ctrl+B)" if collapsed else "Recolher menu (Ctrl+B)"
        )

    # ------------------------------------------------------------- arraste
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
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
            self.maximizeRequested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
