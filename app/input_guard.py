"""Proteções globais de entrada da interface."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QApplication


class CtrlWheelGuard(QObject):
    """Consome Ctrl+roda do mouse em toda a aplicação.

    Alguns widgets Qt (árvores, áreas de rolagem, editores e componentes
    estilizados) reagem de formas diferentes a Ctrl+wheel; em janelas com
    efeitos gráficos e layouts complexos isso pode gerar repinturas
    inesperadas. O gesto não tem função no DiskPilot, então é descartado
    antes de chegar ao widget.
    """

    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self._app = app
        self._enabled = True

    def stop(self) -> None:
        """Remove o filtro antes do teardown do Qt/Python."""
        if not self._enabled:
            return
        self._enabled = False
        try:
            self._app.removeEventFilter(self)
        except (RuntimeError, ReferenceError):
            pass

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if not self._enabled:
            return False
        try:
            if event.type() == QEvent.Wheel:
                modifiers = event.modifiers()
                if modifiers & (Qt.ControlModifier | Qt.MetaModifier):
                    event.accept()
                    return True
        except (RuntimeError, ReferenceError):
            # Durante o shutdown, objetos C++ já podem ter sido destruídos.
            self._enabled = False
        return False
