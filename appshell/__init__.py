"""Núcleo reutilizável de shell para aplicações PySide6.

O pacote não conhece o domínio da aplicação. Ele fornece o contrato de página,
o contexto compartilhado, a infraestrutura de tarefas em segundo plano e a
janela principal genérica.
"""

from __future__ import annotations

from .context import AppContext, SettingsStore
from .pages import BasePage, PageSpec
from .tasks import Task, TaskCancelled, TaskRunner, TaskSignals

__all__ = [
    "AppContext",
    "BasePage",
    "PageSpec",
    "SettingsStore",
    "Task",
    "TaskCancelled",
    "TaskRunner",
    "TaskSignals",
]
