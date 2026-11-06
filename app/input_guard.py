"""Proteções globais de entrada da interface."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt


class CtrlWheelGuard(QObject):
    """Consome Ctrl+roda do mouse em toda a aplicação.

    Alguns widgets Qt (árvores, áreas de rolagem, editores e componentes
    estilizados) reagem de formas diferentes a Ctrl+wheel; em janelas com
    efeitos gráficos e layouts complexos isso pode gerar repinturas
    inesperadas. O gesto não tem função no DiskPilot, então é descartado
    antes de chegar ao widget.
    """

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Wheel:
            modifiers = event.modifiers()
            if modifiers & (Qt.ControlModifier | Qt.MetaModifier):
                event.accept()
                return True
        return super().eventFilter(watched, event)
