"""Infraestrutura genérica de tarefas em segundo plano.

O padrão é sempre o mesmo:

* ``Task`` é um ``QRunnable`` com sinais de progresso, conclusão, falha e
  cancelamento;
* ``TaskRunner`` mantém a tarefa e seus sinais vivos até o término e usa o
  ``QThreadPool`` do Qt.

Assim, cada feature implementa apenas ``execute()``; o ciclo de vida dos sinais
e da thread fica centralizado.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

logger = logging.getLogger("appshell.tasks")


class TaskCancelled(Exception):
    """Exceção usada por uma tarefa para sinalizar cancelamento limpo."""


class TaskSignals(QObject):
    progress = Signal(object)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()


class Task(QRunnable):
    """Tarefa cancelável com sinais padronizados.

    Subclasses implementam ``execute()``. ``run()`` já trata cancelamento e
    exceções, evitando que um erro em worker derrube a aplicação.
    """

    def __init__(self, cancel: threading.Event | None = None) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self.cancel = cancel or threading.Event()
        self.signals = TaskSignals()

    def execute(self) -> Any:
        raise NotImplementedError

    def run(self) -> None:
        try:
            result = self.execute()
        except TaskCancelled:
            self.signals.cancelled.emit()
        except Exception as exc:  # pragma: no cover - borda de integração
            logger.exception("falha na tarefa em segundo plano")
            self.signals.failed.emit(str(exc))
        else:
            if self.cancel.is_set():
                self.signals.cancelled.emit()
            else:
                self.signals.finished.emit(result)


class TaskRunner(QObject):
    """Dono do pool e do ciclo de vida das tarefas de uma feature."""

    busyChanged = Signal(bool)
    progress = Signal(object)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, parent: QObject | None = None, max_threads: int = 1) -> None:
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(max(1, int(max_threads)))
        self._tasks: dict[int, Task] = {}
        self._closing = False

    @property
    def busy(self) -> bool:
        return bool(self._tasks)

    def submit(self, task: Task) -> TaskSignals:
        if self._closing:
            raise RuntimeError("TaskRunner já foi encerrado")
        if not self._tasks:
            self.busyChanged.emit(True)
        self._tasks[id(task.signals)] = task
        task.signals.progress.connect(self.progress.emit)
        task.signals.finished.connect(self.finished.emit)
        task.signals.failed.connect(self.failed.emit)
        task.signals.cancelled.connect(self.cancelled.emit)
        task.signals.finished.connect(self._release_from_sender)
        task.signals.failed.connect(self._release_from_sender)
        task.signals.cancelled.connect(self._release_from_sender)
        self._pool.start(task)
        return task.signals

    def cancel(self) -> None:
        for task in list(self._tasks.values()):
            task.cancel.set()

    def shutdown(self, wait_ms: int = 15000) -> None:
        self._closing = True
        self.cancel()
        try:
            self._pool.waitForDone(wait_ms)
        except Exception:
            logger.exception("falha ao encerrar o pool de tarefas")
        self._tasks.clear()
        self.busyChanged.emit(False)

    @Slot()
    def _release_from_sender(self) -> None:
        signals = self.sender()
        task = self._tasks.pop(id(signals), None)
        if task is None:
            return
        task.signals.deleteLater()
        if not self._tasks:
            self.busyChanged.emit(False)
