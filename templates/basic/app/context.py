"""Contexto compartilhado entregue às páginas."""

from __future__ import annotations

from dataclasses import dataclass

from appshell.config import JsonSettings


@dataclass
class AppContext:
    config: JsonSettings

    def shutdown(self) -> None:
        """Libere recursos de domínio aqui, se houver."""
        self.config.save()
