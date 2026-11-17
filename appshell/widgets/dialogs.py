"""Di?logos gen?ricos do shell: modal sem moldura, confirma??o e redimensionamento."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..theme import get_theme
from .buttons import ActionButton, IconButton
from .common import IconLabel


class _DialogHeader(QFrame):
    def __init__(self, title: str, subtitle: str, dialog: QDialog) -> None:
        super().__init__(dialog)
        self.setObjectName("DialogHeader")
        self._dialog = dialog
        self._drag_offset = QPoint()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 14, 10, 14)
        lay.setSpacing(10)
        texts = QVBoxLayout()
        texts.setContentsMargins(0, 0, 0, 0)
        texts.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("DialogTitle")
        t.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        texts.addWidget(t)
        s = QLabel(subtitle)
        s.setObjectName("DialogSubtitle")
        s.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        texts.addWidget(s)
        lay.addLayout(texts, 1)
        close = IconButton("close", "Fechar", self, 17, 30, "danger")
        close.clicked.connect(dialog.reject)
        lay.addWidget(close)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint()
                - self._dialog.frameGeometry().topLeft()
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if event.buttons() & Qt.LeftButton and not self._drag_offset.isNull():
            self._dialog.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_offset = QPoint()
        super().mouseReleaseEvent(event)


class _ResizeGrip(QWidget):
    """Alça de redimensionamento desenhada sem depender do QStyle."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setFixedSize(16, 16)
        self.setCursor(Qt.SizeFDiagCursor)
        self.setToolTip("Arraste para redimensionar")
        self._start = QPoint()
        self._size = QSize()
        self._resizing = False

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color = QColor(get_theme().color("muted"))
        color.setAlpha(190)
        painter.setPen(QPen(color, 1.2))
        width = self.width()
        height = self.height()
        for offset in (4, 9, 14):
            painter.drawLine(
                width - offset, height - 2, width - 2, height - offset
            )

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._resizing = True
            self._start = event.globalPosition().toPoint()
            self._size = self.window().size()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._resizing and event.buttons() & Qt.LeftButton:
            delta = event.globalPosition().toPoint() - self._start
            window = self.window()
            window.resize(
                max(window.minimumWidth(), self._size.width() + delta.x()),
                max(window.minimumHeight(), self._size.height() + delta.y()),
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._resizing = False
        super().mouseReleaseEvent(event)


class SheetDialog(QDialog):
    """Modal sem moldura do sistema, com card, sombra e arraste."""

    def __init__(
        self,
        parent: QWidget | None,
        title: str,
        subtitle: str = "",
        width: int = 860,
        height: int = 600,
        min_width: int = 480,
        min_height: int = 320,
    ) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self.setWindowModality(Qt.ApplicationModal)
        screen = parent.screen() if parent is not None else QGuiApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else None
        max_w = available.width() - 60 if available is not None else 1200
        max_h = available.height() - 60 if available is not None else 800
        self._width = max(260, min(width, max_w))
        self._height = max(220, min(height, max_h))
        self.setMinimumSize(min(min_width, max_w), min(min_height, max_h))
        self.resize(self._width + 36, self._height + 36)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)
        self.card = QFrame(self)
        self.card.setObjectName("DialogCard")
        outer.addWidget(self.card)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(38)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 130))
        self.card.setGraphicsEffect(shadow)
        root = QVBoxLayout(self.card)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.header = _DialogHeader(title, subtitle, self)
        root.addWidget(self.header)
        self.body_host = QWidget(self.card)
        self.body = QVBoxLayout(self.body_host)
        self.body.setContentsMargins(20, 16, 20, 16)
        self.body.setSpacing(12)
        self.body_scroll = QScrollArea(self.card)
        self.body_scroll.setWidgetResizable(True)
        self.body_scroll.setFrameShape(QFrame.NoFrame)
        self.body_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.body_scroll.setWidget(self.body_host)
        root.addWidget(self.body_scroll, 1)
        self.footer = QHBoxLayout()
        self.footer.setContentsMargins(20, 12, 20, 14)
        self.footer.setSpacing(8)
        foot = QFrame(self)
        foot.setObjectName("DialogFooter")
        foot.setLayout(self.footer)
        root.addWidget(foot)
        self._footer_frame = foot
        self._resize_grip = _ResizeGrip(self)
        self._resize_grip.move(self.width() - 34, self.height() - 34)
        self._resize_grip.raise_()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        grip = getattr(self, "_resize_grip", None)
        if grip is not None:
            grip.move(self.width() - 34, self.height() - 34)
            grip.raise_()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        parent = self.parentWidget()
        if parent:
            center = parent.window().frameGeometry().center()
            self.move(center - self.rect().center())
        else:
            screen = self.screen()
            if screen:
                self.move(screen.availableGeometry().center() - self.rect().center())
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            x = max(available.left() + 8, min(self.x(), available.right() - self.width() - 8))
            y = max(available.top() + 8, min(self.y(), available.bottom() - self.height() - 8))
            self.move(x, y)
        self.raise_()
        self.activateWindow()




class ConfirmDialog(SheetDialog):
    """Confirmação estilizada (evita QMessageBox fora da identidade visual)."""

    def __init__(
        self,
        parent: QWidget | None,
        title: str,
        message: str,
        confirm_text: str = "Confirmar",
        danger: bool = True,
    ) -> None:
        super().__init__(
            parent,
            title,
            "Esta ação não pode ser desfeita.",
            470,
            260,
            min_width=420,
            min_height=240,
        )
        content = QHBoxLayout()
        content.setSpacing(14)
        icon = IconLabel("alert-outline" if danger else "information-outline", 32, "danger" if danger else "info", self)
        content.addWidget(icon, 0, Qt.AlignTop)
        text = QLabel(message)
        text.setWordWrap(True)
        text.setObjectName("Muted")
        content.addWidget(text, 1)
        self.body.addLayout(content)
        self.body.addStretch(1)
        cancel = ActionButton("Cancelar", "", "ghost", self)
        cancel.clicked.connect(self.reject)
        self.footer.addStretch(1)
        self.footer.addWidget(cancel)
        confirm = ActionButton(
            confirm_text,
            "check" if not danger else "delete-outline",
            "danger" if danger else "primary",
            self,
        )
        confirm.clicked.connect(self.accept)
        self.footer.addWidget(confirm)


