"""Contrato base para páginas modulares do shell."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from ..services.state import AppState


class BasePage(QWidget):
    """Toda página recebe o estado compartilhado e pode emitir toasts."""

    toastRequested = Signal(str, str)
    navigateRequested = Signal(str)
    identityChanged = Signal()

    page_id = "page"
    page_title = "Página"
    page_subtitle = ""
    page_icon = "view-dashboard-outline"

    def __init__(self, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self.setObjectName("Page")

    def on_show(self) -> None:
        """Chamado sempre que a página passa a ser a ativa."""

    def on_hide(self) -> None:
        """Chamado ao sair da página."""

    def toast(self, message: str, kind: str = "info") -> None:
        self.toastRequested.emit(message, kind)


@dataclass(frozen=True)
class PageSpec:
    key: str
    title: str
    subtitle: str
    icon: str
    factory: Callable[[AppState], BasePage]
