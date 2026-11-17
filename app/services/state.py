"""Estado compartilhado do app e orquestração da varredura.

A varredura usa ``QThreadPool`` + ``QRunnable`` em vez de QThread manual.
Isso evita a classe de falhas em que um QThread é destruído enquanto ainda
está executando (típica em reanálises e no fechamento da janela).
"""

from __future__ import annotations

import gc
import logging
import os
import threading
import time
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from appshell.tasks import Task, TaskCancelled, TaskRunner

from ..config import AppConfig
from appshell.utils import normalize_path, path_key, resolve_network_path
from .model import ScanProgress, ScanResult, Suggestion
from .scanner import ScanCancelled, scan_paths
from .suggestions import build_suggestions


logger = logging.getLogger("diskpilot.state")


def _is_within(path: str, parent: str) -> bool:
    """True quando ``path`` é igual ou está dentro de ``parent``."""
    try:
        child = os.path.normcase(os.path.normpath(os.path.abspath(path))).rstrip("\\/")
        root = os.path.normcase(os.path.normpath(os.path.abspath(parent))).rstrip("\\/")
    except Exception:
        return False
    if child == root:
        return True
    return child.startswith(root + os.sep)


# Acima deste volume, manter a árvore antiga enquanto a nova é construída
# pode duplicar o uso de memória e derrubar o processo em discos grandes.
RELEASE_RESULT_THRESHOLD = 80_000


class ScanTask(Task):
    """Uma execução da varredura, gerenciada pelo TaskRunner genérico."""

    def __init__(self, roots: list[str], cancel: threading.Event) -> None:
        super().__init__(cancel)
        self.roots = list(roots)

    def execute(self):
        try:
            return scan_paths(
                self.roots,
                self.cancel,
                progress_cb=self.signals.progress.emit,
            )
        except ScanCancelled as exc:
            raise TaskCancelled() from exc


class AppState(QObject):
    rootsChanged = Signal()
    scanStarted = Signal()
    scanProgress = Signal(object)
    scanFinished = Signal(object)
    scanCancelled = Signal()
    scanFailed = Signal(str)
    resultsCleared = Signal()
    busyChanged = Signal(bool)

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config
        self.roots: list[str] = [
            resolve_network_path(path) for path in config.roots
        ]
        if self.roots != config.roots:
            config.roots = self.roots
        self.last_result: ScanResult | None = None
        self.last_error: str = ""
        self.is_scanning = False
        self._runner = TaskRunner(self, max_threads=1)
        self._runner.busyChanged.connect(self.busyChanged.emit)
        self._task: ScanTask | None = None
        self._signals = None
        self._cancel: threading.Event | None = None
        self._scan_merge = False
        self._generation = 0
        self._pending_restart = False
        self._closing = False

    # --------------------------------------------------------------- raízes
    def add_roots(
        self,
        paths: list[str],
        autoscan: bool = True,
        trusted: bool = False,
    ) -> list[str]:
        added: list[str] = []
        existing = {path_key(p) for p in self.roots}
        for raw in paths:
            try:
                path = normalize_path(str(raw))
                path = resolve_network_path(path)
            except Exception:
                continue
            if not trusted and not os.path.isdir(path):
                continue
            key = path_key(path)
            if key in existing:
                continue
            existing.add(key)
            self.roots.append(path)
            added.append(path)
        if added:
            self.config.roots = self.roots
            self.rootsChanged.emit()
            if autoscan:
                self.scan_added(added)
        return added

    def _can_merge_added(self, added: list[str]) -> bool:
        """A adição é incremental se o resultado atual ainda representa as raízes antigas."""
        if self.last_result is None or self.is_scanning:
            return False
        if self.last_result.truncated:
            return False
        added_keys = {path_key(path) for path in added}
        old_keys = {path_key(path) for path in self.roots} - added_keys
        result_keys = {path_key(root.path) for root in self.last_result.roots}
        if result_keys != old_keys:
            return False
        # Raízes aninhadas seriam contadas duas vezes; nesse caso, refaça tudo.
        for index, first in enumerate(self.roots):
            for second in self.roots[index + 1 :]:
                if _is_within(first, second) or _is_within(second, first):
                    return False
        return True

    def scan_added(self, added: list[str]) -> None:
        """Varre somente as pastas novas e mescla o resultado anterior."""
        if not added:
            return
        if self._can_merge_added(added):
            self.start_scan(roots=added, merge=True)
        else:
            self.start_scan()

    def remove_root(self, path: str, autoscan: bool = True) -> None:
        key = path_key(path)
        new_roots = [p for p in self.roots if path_key(p) != key]
        if len(new_roots) == len(self.roots):
            return
        self.roots = new_roots
        self.config.roots = self.roots
        self.rootsChanged.emit()
        if not self.roots:
            self.clear_results(persist=True)
            self.cancel_scan()
            return
        if autoscan:
            self.start_scan()

    def clear_results(self, persist: bool = False) -> None:
        self.last_result = None
        if persist:
            self.config.set("scan.summary", {}, save=False)
            self.config.set("scan.last_scan", 0, save=True)
        self.resultsCleared.emit()

    # -------------------------------------------------------------- varredura
    def start_scan(
        self,
        force: bool = False,
        roots: list[str] | None = None,
        merge: bool = False,
    ) -> None:
        if self._closing or not self.roots:
            return
        if self._task is not None:
            self._pending_restart = True
            if self._cancel is not None:
                self._cancel.set()
            return
        scan_roots = list(roots) if roots is not None else list(self.roots)
        if not scan_roots:
            return
        self.last_error = ""
        self._generation += 1
        generation = self._generation
        self._cancel = threading.Event()
        task = ScanTask(scan_roots, self._cancel)
        signals = task.signals
        signals.progress.connect(
            lambda progress, gen=generation: self._on_progress(gen, progress)
        )
        signals.finished.connect(
            lambda result, gen=generation: self._on_result(gen, result)
        )
        signals.cancelled.connect(
            lambda gen=generation: self._on_cancelled(gen)
        )
        signals.failed.connect(
            lambda message, gen=generation: self._on_failed(gen, message)
        )
        self._task = task
        self._signals = signals
        self._scan_merge = bool(merge and not force and self.last_result is not None)
        self.is_scanning = True
        if not self._scan_merge:
            self._release_large_result()
        self.scanStarted.emit()
        logger.info(
            "scan start gen=%s roots=%s merge=%s",
            generation,
            len(scan_roots),
            self._scan_merge,
        )
        self._runner.submit(task)

    def _release_large_result(self) -> None:
        result = self.last_result
        if result is None:
            return
        entries = result.total_files + result.total_dirs
        if entries < RELEASE_RESULT_THRESHOLD:
            return
        self.last_result = None
        logger.info("resultado anterior liberado (%s entradas)", entries)
        self.resultsCleared.emit()
        gc.collect()

    def cancel_scan(self) -> None:
        self._pending_restart = False
        if self._cancel is not None:
            self._cancel.set()

    def _finish_task(self, generation: int) -> None:
        """Libera a task atual, ignorando callbacks de gerações antigas."""
        if generation != self._generation:
            return
        self._signals = None
        self._task = None
        self._cancel = None
        self._scan_merge = False
        self.is_scanning = False

    @staticmethod
    def _merge_results(base: ScanResult, extra: ScanResult) -> ScanResult:
        merged = ScanResult(
            roots=[*base.roots, *extra.roots],
            total_size=base.total_size + extra.total_size,
            total_files=base.total_files + extra.total_files,
            total_dirs=base.total_dirs + extra.total_dirs,
            errors=base.errors + extra.errors,
            elapsed=base.elapsed + extra.elapsed,
            started_at=base.started_at or extra.started_at,
            truncated=base.truncated or extra.truncated,
        )
        merged.suggestions = build_suggestions(merged)
        return merged

    @Slot(int, object)
    def _on_progress(self, generation: int, progress: ScanProgress) -> None:
        if generation != self._generation:
            return
        self.scanProgress.emit(progress)

    @Slot(int, object)
    def _on_result(self, generation: int, result: ScanResult) -> None:
        if generation != self._generation:
            return
        merge_base = self.last_result if self._scan_merge else None
        self._finish_task(generation)
        if self._pending_restart:
            self._pending_restart = False
            QTimer.singleShot(0, self.start_scan)
            return
        if merge_base is not None:
            result = self._merge_results(merge_base, result)
        self.last_result = result
        try:
            self._store_summary(result)
        except Exception:
            logger.exception("falha ao persistir o resumo da análise")
        logger.info(
            "scan done gen=%s files=%s dirs=%s size=%s suggestions=%s truncated=%s",
            generation,
            result.total_files,
            result.total_dirs,
            result.total_size,
            len(result.suggestions),
            result.truncated,
        )
        self.scanFinished.emit(result)

    @Slot(int)
    def _on_cancelled(self, generation: int) -> None:
        if generation != self._generation:
            return
        self._finish_task(generation)
        if self._pending_restart:
            self._pending_restart = False
            QTimer.singleShot(0, self.start_scan)
            return
        logger.info("scan cancelled gen=%s", generation)
        self.scanCancelled.emit()

    @Slot(int, str)
    def _on_failed(self, generation: int, message: str) -> None:
        if generation != self._generation:
            return
        self._finish_task(generation)
        if self._pending_restart:
            self._pending_restart = False
            QTimer.singleShot(0, self.start_scan)
            return
        self.last_error = message
        logger.error("scan failed gen=%s: %s", generation, message)
        self.scanFailed.emit(message)

    def _store_summary(self, result: ScanResult) -> None:
        summary = {
            "total_size": result.total_size,
            "total_files": result.total_files,
            "total_dirs": result.total_dirs,
            "errors": result.errors,
            "elapsed": round(result.elapsed, 3),
            "started_at": result.started_at,
            "truncated": result.truncated,
            "safe_savings": result.safe_savings,
            "review_savings": result.review_savings,
            "roots": [
                {
                    "path": root.path,
                    "name": root.name,
                    "size": root.size,
                    "files": root.files,
                    "dirs": root.dirs,
                }
                for root in result.roots
            ],
            "top_dirs": [
                {"path": node.path, "name": node.name, "size": node.size}
                for node in result.largest_paths(6)
            ],
            "suggestion_count": len(result.suggestions),
        }
        self.config.set("scan.last_scan", time.time(), save=False)
        self.config.set("scan.summary", summary, save=True)

    # --------------------------------------------------------------- consulta
    @property
    def summary(self) -> dict[str, Any]:
        if self.last_result is not None:
            return {
                "total_size": self.last_result.total_size,
                "total_files": self.last_result.total_files,
                "total_dirs": self.last_result.total_dirs,
                "errors": self.last_result.errors,
                "elapsed": self.last_result.elapsed,
                "started_at": self.last_result.started_at,
                "truncated": self.last_result.truncated,
                "safe_savings": self.last_result.safe_savings,
                "review_savings": self.last_result.review_savings,
                "roots": [
                    {
                        "path": root.path,
                        "name": root.name,
                        "size": root.size,
                        "files": root.files,
                        "dirs": root.dirs,
                    }
                    for root in self.last_result.roots
                ],
                "top_dirs": [
                    {"path": node.path, "name": node.name, "size": node.size}
                    for node in self.last_result.largest_paths(6)
                ],
                "suggestion_count": len(self.last_result.suggestions),
            }
        stored = self.config.get("scan.summary", {})
        return stored if isinstance(stored, dict) else {}

    @property
    def suggestions(self) -> list[Suggestion]:
        if self.last_result is not None:
            return self.last_result.suggestions
        return []

    @property
    def busy(self) -> bool:
        return self._task is not None

    def shutdown(self) -> None:
        self._closing = True
        self._pending_restart = False
        logger.info("shutdown solicitado")
        if self._cancel is not None:
            self._cancel.set()
        try:
            # O TaskRunner aguarda as threads e mantém os sinais vivos até o
            # término; não destruímos um QThread em execução.
            self._runner.shutdown()
        except Exception:
            logger.exception("falha ao encerrar o pool de varredura")
        try:
            self.config.save()
        except Exception:
            logger.exception("falha ao salvar a configuração no encerramento")
