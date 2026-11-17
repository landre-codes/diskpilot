"""Contratos compartilhados entre o shell e as páginas."""

from __future__ import annotations

from typing import Any, Protocol


class SettingsStore(Protocol):
    """Armazenamento de configurações usado pelo shell.

    O shell só precisa de leitura/gravação por chave. O domínio pode expor
    propriedades tipadas por cima dessa interface.
    """

    def get(self, dotted: str, default: Any = None) -> Any: ...

    def set(self, dotted: str, value: Any, save: bool = True) -> None: ...

    def save(self) -> None: ...


class AppContext(Protocol):
    """Contexto entregue às páginas pelo shell.

    O shell não conhece os métodos específicos do domínio; ele apenas repassa
    este objeto para as fábricas de página. O estado concreto da aplicação
    pode oferecer propriedades e sinais adicionais.
    """

    config: SettingsStore

    def shutdown(self) -> None:
        """Libera recursos ao fechar a janela."""
