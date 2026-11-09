"""Menu lateral com logo persistente, abas verticais e usuário logado."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    Signal,
    Property,
)
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QMenu,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..config import AppConfig
from ..icons import avatar_pixmap, circular_pixmap, icon, rounded_pixmap
from ..theme import get_theme
from .buttons import NavButton
from .common import Divider


EXPANDED_WIDTH = 248
COLLAPSED_WIDTH = 80


class LogoButton(QWidget):
    """Marca/logo no topo; clique altera, menu de contexto remove."""

    clicked = Signal()
    removeRequested = Signal()

    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self._ratio = 1.0
        self._hover = False
        self._logo = QPixmap()
        self.setFixedHeight(72)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Clique para alterar o logo da empresa")
        self.setAttribute(Qt.WA_Hover, True)
        self.set_logo_path(config.logo_path)
        get_theme().changed.connect(self.update)

    def set_logo_path(self, path: str) -> None:
        self._logo = QPixmap(path) if path else QPixmap()
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
        if event.button() == Qt.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        theme = get_theme()
        menu = QMenu(self)
        act_change = menu.addAction(icon("image-outline", theme.color("muted"), 16), "Alterar logo…")
        act_remove = menu.addAction(icon("delete-outline", theme.color("danger"), 16), "Remover logo")
        act_remove.setEnabled(not self._logo.isNull())
        chosen = menu.exec(event.globalPos())
        if chosen == act_change:
            self.clicked.emit()
        elif chosen == act_remove:
            self.removeRequested.emit()

    def paintEvent(self, event) -> None:  # noqa: N802
        theme = get_theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(theme.color("sidebar")))
        if self._hover:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.color("hover")))
            p.drawRoundedRect(QRectF(6, 7, w - 12, h - 14), 10, 10)

        ratio = self._ratio
        if not self._logo.isNull():
            avail_w = max(44, w - 28)
            avail_h = 46
            scaled = self._logo.scaled(
                int(avail_w), avail_h, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            x = (w - scaled.width()) / 2
            y = (h - scaled.height()) / 2
            p.drawPixmap(int(round(x)), int(round(y)), scaled)
            p.end()
            return

        mark = 40
        x = 14 if ratio < 0.5 else (w - mark) / 2
        x = 14 + ((w - mark) / 2 - 14) * (1 - ratio)
        y = (h - mark) / 2
        grad = QLinearGradient(x, y, x + mark, y + mark)
        grad.setColorAt(0, QColor(theme.color("primary")))
        grad.setColorAt(1, QColor(theme.color("info")))
        p.setPen(Qt.NoPen)
        p.setBrush(grad)
        p.drawRoundedRect(QRectF(x, y, mark, mark), 11, 11)
        pm = icon("harddisk", theme.color("on_primary"), 23).pixmap(23, 23)
        p.drawPixmap(int(x + (mark - 23) / 2), int(y + (mark - 23) / 2), pm)

        if ratio > 0.1:
            alpha = int(max(0.0, min(1.0, (ratio - 0.1) / 0.6)) * 255)
            color = QColor(theme.color("text"))
            color.setAlpha(alpha)
            p.setPen(color)
            f = QFont("Segoe UI")
            f.setPixelSize(theme.fs(16))
            f.setWeight(QFont.Bold)
            p.setFont(f)
            p.drawText(
                QRectF(x + mark + 10, h / 2 - 19, w - x - mark - 18, 22),
                Qt.AlignVCenter | Qt.AlignLeft,
                "DiskPilot",
            )
            cap = QColor(theme.color("muted"))
            cap.setAlpha(int(alpha * 0.9))
            p.setPen(cap)
            f.setPixelSize(theme.fs(9))
            f.setWeight(QFont.DemiBold)
            f.setLetterSpacing(QFont.AbsoluteSpacing, 1.1)
            p.setFont(f)
            p.drawText(
                QRectF(x + mark + 10, h / 2 + 2, w - x - mark - 18, 16),
                Qt.AlignVCenter | Qt.AlignLeft,
                "GESTOR DE ESPAÇO",
            )
        p.end()


class UserCard(QWidget):
    clicked = Signal()

    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self._ratio = 1.0
        self._hover = False
        self._avatar = QPixmap()
        self.setFixedHeight(58)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.refresh()
        get_theme().changed.connect(self.update)

    def refresh(self) -> None:
        dpr = max(2.0, self.devicePixelRatioF())
        path = self.config.avatar_path
        if path:
            self._avatar = circular_pixmap(path, 38, dpr)
        else:
            theme = get_theme()
            self._avatar = avatar_pixmap(
                self.config.user_name,
                38,
                theme.color("primary"),
                theme.color("info"),
                theme.color("on_primary"),
                dpr,
            )
        self.setToolTip(
            f"{self.config.user_name}\nConta local\nClique para editar o perfil"
        )
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
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        theme = get_theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(theme.color("sidebar")))
        if self._hover:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.color("hover")))
            p.drawRoundedRect(QRectF(6, 5, w - 12, h - 10), 10, 10)
        ratio = self._ratio
        avatar_size = 38
        x = 9 + ((w - avatar_size) / 2 - 9) * (1 - ratio)
        y = (h - avatar_size) / 2
        p.drawPixmap(int(round(x)), int(round(y)), self._avatar)
        p.setPen(Qt.NoPen)
        p.setBrush(Qt.NoBrush)

        if ratio > 0.1:
            alpha = int(max(0.0, min(1.0, (ratio - 0.1) / 0.55)) * 255)
            text = QColor(theme.color("text"))
            text.setAlpha(alpha)
            p.setPen(text)
            f = QFont("Segoe UI")
            f.setPixelSize(theme.fs(12))
            f.setWeight(QFont.DemiBold)
            p.setFont(f)
            p.drawText(
                QRectF(x + avatar_size + 9, h / 2 - 18, w - x - avatar_size - 38, 19),
                Qt.AlignVCenter | Qt.AlignLeft,
                p.fontMetrics().elidedText(
                    self.config.user_name,
                    Qt.ElideRight,
                    int(max(20, w - x - avatar_size - 40)),
                ),
            )
            muted = QColor(theme.color("muted"))
            muted.setAlpha(alpha)
            p.setPen(muted)
            f.setPixelSize(theme.fs(10))
            f.setWeight(QFont.Normal)
            p.setFont(f)
            p.drawText(
                QRectF(x + avatar_size + 9, h / 2 + 1, w - x - avatar_size - 38, 17),
                Qt.AlignVCenter | Qt.AlignLeft,
                p.fontMetrics().elidedText(
                    "Conta local",
                    Qt.ElideRight,
                    int(max(20, w - x - avatar_size - 40)),
                ),
            )
            chevron = icon("dots-horizontal", theme.color("muted"), 16).pixmap(16, 16)
            p.drawPixmap(int(w - 27), int((h - 16) / 2), chevron)
        p.end()


class Sidebar(QWidget):
    pageSelected = Signal(str)
    collapsedChanged = Signal(bool)
    logoRequested = Signal()
    logoRemoveRequested = Signal()
    userRequested = Signal()

    def __init__(
        self,
        config: AppConfig,
        pages: list[tuple[str, str, str]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.config = config
        self._collapsed = bool(config.get("sidebar_collapsed", False))
        self._anim: QPropertyAnimation | None = None
        self._buttons: dict[str, NavButton] = {}
        self._active_key = ""

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 10)
        lay.setSpacing(4)
        self.logo = LogoButton(config, self)
        self.logo.clicked.connect(self.logoRequested)
        self.logo.removeRequested.connect(self.logoRemoveRequested)
        lay.addWidget(self.logo)
        lay.addSpacing(8)

        self.nav_host = QWidget(self)
        nav = QVBoxLayout(self.nav_host)
        nav.setContentsMargins(0, 0, 0, 0)
        nav.setSpacing(3)
        for key, label, icon_name in pages:
            btn = NavButton(key, label, icon_name, self.nav_host)
            btn.clicked.connect(lambda k=key: self._select(k))
            nav.addWidget(btn)
            self._buttons[key] = btn
        lay.addWidget(self.nav_host)
        lay.addStretch(1)

        self.bottom_divider = Divider(self)
        lay.addWidget(self.bottom_divider)
        lay.addSpacing(2)
        self.user = UserCard(config, self)
        self.user.clicked.connect(self.userRequested)
        lay.addWidget(self.user)

        start_w = COLLAPSED_WIDTH if self._collapsed else EXPANDED_WIDTH
        self.setFixedWidth(start_w)
        self._apply_expansion(self._width_to_ratio(start_w))

    # ----------------------------------------------- propriedade animável
    def _get_sidebar_width(self) -> int:
        return self.width()

    def _set_sidebar_width(self, value: int) -> None:
        self.setFixedWidth(int(value))
        self._apply_expansion(self._width_to_ratio(int(value)))

    sidebarWidth = Property(int, _get_sidebar_width, _set_sidebar_width)

    @staticmethod
    def _width_to_ratio(width: int) -> float:
        span = EXPANDED_WIDTH - COLLAPSED_WIDTH
        return max(0.0, min(1.0, (width - COLLAPSED_WIDTH) / span))

    def _apply_expansion(self, ratio: float) -> None:
        self.logo.set_expansion(ratio)
        self.user.set_expansion(ratio)
        for btn in self._buttons.values():
            btn.set_expansion(ratio)

    # ------------------------------------------------------------- público
    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool, animate: bool = True) -> None:
        collapsed = bool(collapsed)
        if collapsed == self._collapsed and self.width() in (EXPANDED_WIDTH, COLLAPSED_WIDTH):
            return
        self._collapsed = collapsed
        target = COLLAPSED_WIDTH if collapsed else EXPANDED_WIDTH
        if self._anim is not None:
            self._anim.stop()
        if not animate:
            self.setFixedWidth(target)
            self._apply_expansion(self._width_to_ratio(target))
            self.collapsedChanged.emit(collapsed)
            return
        self._anim = QPropertyAnimation(self, b"sidebarWidth", self)
        self._anim.setDuration(240)
        self._anim.setStartValue(self.width())
        self._anim.setEndValue(target)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(lambda: self.collapsedChanged.emit(self._collapsed))
        self._anim.start()

    def toggle(self) -> None:
        self.set_collapsed(not self._collapsed)

    def set_active(self, key: str) -> None:
        self._active_key = key
        for btn_key, btn in self._buttons.items():
            btn.set_active(btn_key == key)

    def _select(self, key: str) -> None:
        self.set_active(key)
        self.pageSelected.emit(key)

    def refresh_user(self) -> None:
        self.user.refresh()

    def refresh_logo(self) -> None:
        self.logo.set_logo_path(self.config.logo_path)

    def set_buttons_enabled(self, enabled: bool) -> None:
        for btn in self._buttons.values():
            btn.setEnabled(enabled)
