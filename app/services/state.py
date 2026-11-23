"""Estado compartilhado do app e orquestração da varredura.

A varredura usa ``QThreadPool`` + ``QRunnable`` em vez de QThread manual.
Isso evita a classe de falhas em que um QThread é destruído enquanto ainda
está executando (típica em reanálises e no fechamento da janela).
"""

from __future__ import annotations

import gc
import logging
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from appshell.tasks import Task, TaskCancelled, TaskRunner

from ..config import AppConfig
from appshell.utils import (
    clear_author_cache,
    normalize_path,
    path_key,
    resolve_network_path,
)
from .index_store import IndexTask, SearchIndex, is_managed_index
from .limits import DEFAULT_ENTRIES, MAX_ENTRIES, MIN_ENTRIES, estimate_max_entries
from .model import ScanProgress, ScanResult, ScanWarning, Suggestion
from .scanner import ScanCancelled, scan_paths
from .suggestions import build_suggestions


logger = logging.getLogger("diskpilot.state")


def _suggestion_payload(suggestion: Suggestion) -> dict[str, Any]:
    return {
        "key": suggestion.key,
        "title": suggestion.title,
        "description": suggestion.description,
        "savings": int(suggestion.savings),
        "count": int(suggestion.count),
        "confidence": suggestion.confidence,
        "icon": suggestion.icon,
        "note": suggestion.note,
        "paths": [str(path) for path in suggestion.paths],
    }


def _suggestion_from_payload(payload: object) -> Suggestion | None:
    if not isinstance(payload, dict):
        return None
    try:
        key = str(payload.get("key", "") or "")
        title = str(payload.get("title", "") or "")
        if not key or not title:
            return None
        raw_paths = payload.get("paths", [])
        if not isinstance(raw_paths, list):
            raw_paths = []
        paths = [
            str(path)
            for path in raw_paths
            if isinstance(path, str) and path
        ]
        return Suggestion(
            key=key,
            title=title,
            description=str(payload.get("description", "") or ""),
            savings=int(payload.get("savings", 0) or 0),
            count=int(payload.get("count", 0) or 0),
            confidence=str(payload.get("confidence", "review") or "review"),
            icon=str(payload.get("icon", "lightbulb-outline") or "lightbulb-outline"),
            note=str(payload.get("note", "") or ""),
            paths=paths,
        )
    except (TypeError, ValueError):
        return None

INDEX_GC_AGE_SECONDS = 24 * 60 * 60


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

    def __init__(
        self,
        roots: list[str],
        cancel: threading.Event,
        max_entries: int = DEFAULT_ENTRIES,
        index: SearchIndex | None = None,
        merge_base: SearchIndex | None = None,
    ) -> None:
        super().__init__(cancel)
        self.roots = list(roots)
        self.max_entries = max(1, int(max_entries))
        self.index = index
        self.merge_base = merge_base

    def execute(self):
        try:
            if self.index is not None:
                from .scanner import stream_scan_paths

                if self.merge_base is None:
                    return stream_scan_paths(
                        self.roots,
                        self.index,
                        self.cancel,
                        progress_cb=self.signals.progress.emit,
                        max_entries=self.max_entries,
                    )
                target = SearchIndex.create(self.index.path.parent)
                try:
                    stream_scan_paths(
                        self.roots,
                        self.index,
                        self.cancel,
                        progress_cb=self.signals.progress.emit,
                        max_entries=self.max_entries,
                        suggestions=False,
                    )
                    self.signals.progress.emit(
                        ScanProgress(
                            current="Consolidando índice…",
                            roots_total=1,
                        )
                    )
                    SearchIndex.merge_indexes(
                        [self.merge_base, self.index],
                        target,
                        self.cancel,
                    )
                    merged = target.load_result(
                        cancel=self.cancel, lazy=True
                    )
                    if merged is None:
                        raise RuntimeError(
                            "índice consolidado não pôde ser restaurado"
                        )
                    try:
                        merged.suggestions = build_suggestions(merged)
                    except Exception:
                        logger.exception(
                            "falha ao calcular sugestões consolidadas"
                        )
                        merged.suggestions = []
                    return merged
                except Exception:
                    target.delete()
                    raise
                finally:
                    self.index.delete()
            return scan_paths(
                self.roots,
                self.cancel,
                progress_cb=self.signals.progress.emit,
                max_entries=self.max_entries,
            )
        except ScanCancelled as exc:
            raise TaskCancelled() from exc


class RestoreTask(Task):
    """Recarrega um ScanResult do índice SQLite persistido."""

    def __init__(self, index: SearchIndex, lazy: bool = False) -> None:
        super().__init__()
        self.index = index
        self.lazy = lazy

    def execute(self):
        return self.index.load_result(cancel=self.cancel, lazy=self.lazy)


class AppState(QObject):
    rootsChanged = Signal()
    scanStarted = Signal()
    scanProgress = Signal(object)
    scanFinished = Signal(object)
    scanCancelled = Signal()
    scanFailed = Signal(str)
    resultsCleared = Signal()
    busyChanged = Signal(bool)
    searchIndexReady = Signal(object)
    searchIndexCleared = Signal()
    searchIndexFailed = Signal(str)
    rootsPending = Signal(object)
    indexUsageChanged = Signal()

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config
        self.roots: list[str] = [
            resolve_network_path(path) for path in config.roots
        ]
        if self.roots != config.roots:
            try:
                config.roots = self.roots
            except Exception:
                logger.exception("falha ao normalizar as raízes persistidas")
        self.last_result: ScanResult | None = None
        self.last_error: str = ""
        self.is_scanning = False
        self._runner = TaskRunner(self, max_threads=1)
        self._runner.busyChanged.connect(self.busyChanged.emit)
        self._index_runner = TaskRunner(self, max_threads=1)
        self._restore_runner = TaskRunner(self, max_threads=1)
        self._index_generation = 0
        self._restore_generation = 0
        self._restoring = False
        self.search_index: SearchIndex | None = None
        self.index_building = False
        self._task: ScanTask | None = None
        self._signals = None
        self._cancel: threading.Event | None = None
        self._scan_merge = False
        self._generation = 0
        self._pending_restart = False
        self._closing = False
        self._building_index_path: Path | None = None
        self._restore_queue: list[Path] = []
        self._restore_index: SearchIndex | None = None
        self._restore_active_path = ""
        self._last_restore_error = ""
        self._pending_signature: tuple[str, ...] = ()
        self._current_limit_entries = 0
        self._scan_budget_total = 0
        self._pending_index: SearchIndex | None = None
        self._pending_added_roots: list[str] = []
        self._retention_timer = QTimer(self)
        self._retention_timer.setInterval(24 * 60 * 60 * 1000)
        self._retention_timer.timeout.connect(self._enforce_index_retention)
        self._retention_timer.start()
        self._load_persisted_index()

    # ---------------------------------------------------------- persistência
    @property
    def index_dir(self) -> Path:
        return self.config.path.parent / "index"

    def _scan_limit(self) -> int:
        raw = self.config.get("scan.max_entries", 0)
        try:
            override = int(raw or 0)
        except (TypeError, ValueError):
            override = 0
        limit = estimate_max_entries(override=override)
        logger.info(
            "limite efetivo de análise: %s entradas (override=%s)",
            limit,
            override or "automático",
        )
        return limit

    def _index_space_guard(self, merge: bool) -> str:
        """Falha cedo quando não há espaço para o índice temporário/merge."""
        try:
            base = self.index_dir if self.index_dir.exists() else self.index_dir.parent
            free = int(shutil.disk_usage(base).free)
        except OSError:
            return ""
        current = int(self.index_usage().get("total_bytes", 0) or 0)
        required = max(
            256 * 1024 * 1024,
            int(current * 1.10) + 64 * 1024 * 1024,
        ) if merge else 256 * 1024 * 1024
        if free >= required:
            return ""
        return (
            "espaço livre insuficiente para criar o índice de busca "
            f"({free // (1024 * 1024)} MB livres; {required // (1024 * 1024)} MB "
            "necessários). O snapshot anterior foi preservado."
        )

    @property
    def scan_limit(self) -> int:
        """Limite efetivo para a próxima análise; não altera o snapshot."""
        return self._scan_limit()

    def _scan_engine(self) -> str:
        raw = str(self.config.get("scan.engine", "auto") or "auto").lower()
        return raw if raw in {"auto", "stream", "memory"} else "auto"

    def _use_streaming(self) -> bool:
        return self._scan_engine() != "memory"

    @property
    def scan_engine(self) -> str:
        return self._scan_engine()

    def _index_config_keys(self) -> tuple[str, ...]:
        return (
            "scan.index_path",
            "scan.index_previous_path",
            "scan.index_entries",
            "scan.indexed_roots",
            "scan.index_verified_at",
        )

    def _snapshot_index_config(self) -> dict[str, object]:
        return {
            key: self.config.get(key, None)
            for key in self._index_config_keys()
        }

    def _save_index_config(self, values: dict[str, object]) -> bool:
        """Publica referências com rollback em memória se o save falhar."""
        previous = self._snapshot_index_config()
        for key, value in values.items():
            self.config.set(key, value, save=False)
        try:
            self.config.save()
            return True
        except Exception:
            for key, value in previous.items():
                self.config.set(key, value, save=False)
            logger.exception("falha ao publicar o estado do índice")
            return False

    def _clear_index_reference(self) -> bool:
        return self._save_index_config(
            {
                "scan.index_path": "",
                "scan.index_previous_path": "",
                "scan.index_entries": 0,
                "scan.indexed_roots": [],
                "scan.index_verified_at": 0,
            }
        )

    @staticmethod
    def _path_identity(path: str | Path) -> str:
        try:
            return os.path.normcase(str(Path(path).resolve(strict=False)))
        except OSError:
            return os.path.normcase(os.path.abspath(str(path)))

    def _load_persisted_index(self) -> None:
        active_raw = str(self.config.get("scan.index_path", "") or "")
        previous_raw = str(
            self.config.get("scan.index_previous_path", "") or ""
        )
        candidates: list[Path] = []
        seen: set[str] = set()
        for raw in (active_raw, previous_raw):
            if not raw:
                continue
            path = Path(raw)
            key = self._path_identity(path)
            if key in seen:
                continue
            seen.add(key)
            if path.is_file():
                candidates.append(path)
            else:
                logger.warning("índice persistido ausente: %s", path)
        if not candidates:
            try:
                managed = sorted(
                    (
                        path
                        for path in self.index_dir.glob("search-*.sqlite")
                        if is_managed_index(path, self.index_dir)
                    ),
                    key=lambda path: path.stat().st_mtime,
                    reverse=True,
                )
            except OSError:
                managed = []
            for path in managed[:3]:
                if path.is_file():
                    candidates.append(path)
            if candidates:
                logger.info(
                    "recuperando índice gerenciado sem referência: %s",
                    candidates[0],
                )
        if not candidates:
            if active_raw or previous_raw:
                self._clear_index_reference()
                QTimer.singleShot(
                    0,
                    lambda: self.searchIndexFailed.emit(
                        "índice persistido ausente"
                    ),
                )
            return
        self._restore_active_path = active_raw
        self._restore_queue = candidates
        self._restoring = True
        self._start_next_restore()

    def _start_next_restore(self) -> None:
        if self._restore_queue:
            path = self._restore_queue.pop(0)
            index = SearchIndex(path)
            self._restore_index = index
            self._last_restore_error = ""
            self._restore_generation += 1
            generation = self._restore_generation
            task = RestoreTask(index, lazy=self._use_streaming())
            task.signals.finished.connect(
                lambda result, gen=generation: self._on_restored(gen, result)
            )
            task.signals.failed.connect(
                lambda message, gen=generation: self._on_restore_failed(
                    gen, message
                )
            )
            logger.info("restaurando análise persistida: %s", path)
            self._restore_runner.submit(task)
            return
        self._restoring = False
        self._restore_index = None
        self._drop_index(emit=False, clear_config=True, delete_files=False)
        self.searchIndexFailed.emit(
            self._last_restore_error or "índice persistido inválido"
        )
        self._flush_pending_added()

    def _stored_suggestions(self) -> list[Suggestion]:
        stored = self.config.get("scan.summary", {})
        if not isinstance(stored, dict):
            return []
        raw = stored.get("suggestions", [])
        if not isinstance(raw, list):
            return []
        restored: list[Suggestion] = []
        for item in raw:
            suggestion = _suggestion_from_payload(item)
            if suggestion is not None:
                restored.append(suggestion)
        return restored

    def _summary_matches_result(self, result: ScanResult) -> bool:
        summary = self.config.get("scan.summary", {})
        if not isinstance(summary, dict):
            return False
        if not isinstance(summary.get("suggestions"), list):
            return False
        try:
            same_time = abs(
                float(summary.get("started_at", 0) or 0)
                - float(result.started_at or 0)
            ) <= 1.0
        except (TypeError, ValueError):
            return False
        if not same_time:
            return False
        summary_roots = {
            path_key(str(item.get("path", "")))
            for item in summary.get("roots", [])
            if isinstance(item, dict) and item.get("path")
        }
        result_roots = {path_key(root.path) for root in result.roots}
        if not result_roots or summary_roots != result_roots:
            return False
        stored_index = str(summary.get("index_path", "") or "")
        result_index = str(getattr(result, "index_path", "") or "")
        if stored_index:
            if not result_index:
                return False
            if self._path_identity(stored_index) != self._path_identity(
                result_index
            ):
                return False
            try:
                stored_entries = int(summary.get("index_entries", 0) or 0)
            except (TypeError, ValueError):
                return False
            index = getattr(result, "index", None)
            if (
                stored_entries
                and index is not None
                and index.stats.rows != stored_entries
            ):
                return False
        for key, value in (
            ("total_size", result.total_size),
            ("total_files", result.total_files),
            ("total_dirs", result.total_dirs),
        ):
            if key not in summary:
                continue
            try:
                if int(summary[key]) != int(value):
                    return False
            except (TypeError, ValueError):
                return False
        return True

    def _on_restored(self, generation: int, result: ScanResult | None) -> None:
        if (
            generation != self._restore_generation
            or not self._restoring
            or self._closing
        ):
            return
        if result is None:
            self._last_restore_error = "índice persistido inválido"
            self._start_next_restore()
            return
        index = self._restore_index
        if index is None:
            self._last_restore_error = "índice persistido indisponível"
            self._start_next_restore()
            return
        self._restore_index = None
        self._restoring = False
        if self._summary_matches_result(result):
            result.suggestions = self._stored_suggestions()
            logger.info(
                "sugestões restauradas do resumo: %s",
                len(result.suggestions),
            )
        else:
            try:
                result.suggestions = build_suggestions(result)
            except Exception:
                logger.exception("falha ao recalcular sugestões restauradas")
                result.suggestions = []
        self.search_index = index
        from_previous = self._path_identity(index.path) != self._path_identity(
            self._restore_active_path
        )
        values: dict[str, object] = {
            "scan.index_path": str(index.path),
            "scan.index_entries": index.stats.rows,
            "scan.indexed_roots": list(
                index.snapshot_roots
                or [root.path for root in result.roots]
            ),
            "scan.index_verified_at": time.time(),
        }
        if from_previous:
            values["scan.index_previous_path"] = ""
        if not self._save_index_config(values):
            logger.warning(
                "análise restaurada, mas as referências do índice não "
                "puderam ser publicadas"
            )
        clear_author_cache()
        self.last_result = result
        logger.info(
            "análise restaurada: raízes=%s arquivos=%s pastas=%s",
            len(result.roots),
            result.total_files,
            result.total_dirs,
        )
        self.scanFinished.emit(result)
        self.searchIndexReady.emit(self.search_index)
        self._emit_pending_roots()
        self._collect_index_garbage()
        self._flush_pending_added()

    def _on_restore_failed(self, generation: int, message: str) -> None:
        if generation != self._restore_generation or self._closing:
            return
        logger.error("falha ao restaurar análise: %s", message)
        self._last_restore_error = message
        self._start_next_restore()

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
            self._persist_roots()
            self.rootsChanged.emit()
            if autoscan:
                self.scan_added(added)
        return added

    def _persist_roots(self) -> None:
        try:
            self.config.roots = self.roots
        except Exception:
            logger.exception("falha ao persistir a lista de raízes")

    def _can_merge_added(self, added: list[str]) -> bool:
        """A adição é incremental se o resultado atual ainda representa as raízes antigas."""
        if self.last_result is None or self.is_scanning:
            return False
        if self.last_result.lazy and (
            not self._use_streaming() or self.last_result.index is None
        ):
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

    def _queue_pending_added(self, added: list[str]) -> None:
        existing = {path_key(path) for path in self._pending_added_roots}
        for path in added:
            key = path_key(path)
            if key in existing:
                continue
            existing.add(key)
            self._pending_added_roots.append(path)
        if self._pending_added_roots:
            logger.info(
                "adições aguardando restauração: %s",
                len(self._pending_added_roots),
            )

    def _flush_pending_added(self) -> None:
        if self._restoring or not self._pending_added_roots:
            return
        added = list(self._pending_added_roots)
        self._pending_added_roots.clear()
        if added:
            self.scan_added(added)

    def scan_added(self, added: list[str]) -> None:
        """Varre somente as pastas novas e mescla o resultado anterior."""
        if not added:
            return
        if self._restoring:
            self._queue_pending_added(added)
            return
        if self._can_merge_added(added):
            base_entries = (
                self.last_result.total_files + self.last_result.total_dirs
                if self.last_result is not None
                else 0
            )
            remaining = (
                (self._current_limit_entries or self._scan_limit())
                - base_entries
            )

            if remaining > 0:
                self.start_scan(roots=added, merge=True, max_entries=remaining)
                return
            logger.warning(
                "orçamento agregado esgotado (%s entradas); refazendo a "
                "análise completa com truncamento controlado",
                base_entries,
            )
        self.start_scan()

    def remove_root(self, path: str, autoscan: bool = True) -> None:
        key = path_key(path)
        new_roots = [p for p in self.roots if path_key(p) != key]
        if len(new_roots) == len(self.roots):
            return
        self.roots = new_roots
        self._persist_roots()
        self.rootsChanged.emit()
        if not self.roots:
            self.clear_results(persist=True)
            self.cancel_scan()
            return
        if autoscan:
            self.start_scan()

    def clear_results(self, persist: bool = False) -> None:
        self.last_result = None
        clear_author_cache()
        self._pending_restart = False
        if self._cancel is not None:
            self._cancel.set()
        self._generation += 1
        self._task = None
        self._signals = None
        self._cancel = None
        self.is_scanning = False
        self._scan_merge = False
        self._restoring = False
        self._pending_added_roots.clear()
        self._restore_generation += 1
        self._restore_queue.clear()
        self._restore_index = None
        self._restore_runner.cancel()
        self._index_generation += 1
        self._index_runner.cancel()
        self._discard_pending_index()
        self._drop_index(emit=True, clear_config=True)
        if persist:
            try:
                self.config.set("scan.summary", {}, save=False)
                self.config.set("scan.last_scan", 0, save=True)
            except Exception:
                logger.exception("falha ao limpar o resumo persistido")
        self.resultsCleared.emit()

    # -------------------------------------------------------------- varredura
    def start_scan(
        self,
        force: bool = False,
        roots: list[str] | None = None,
        merge: bool = False,
        max_entries: int | None = None,
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
        if max_entries is None:
            max_entries = self._scan_limit()
        else:
            max_entries = max(1, int(max_entries))
        base_entries = (
            self.last_result.total_files + self.last_result.total_dirs
            if merge and self.last_result is not None
            else 0
        )
        self._scan_budget_total = max_entries + base_entries
        self._current_limit_entries = self._scan_budget_total
        self._restoring = False
        self._pending_added_roots.clear()
        self._restore_generation += 1
        self._restore_queue.clear()
        self._restore_index = None
        self._restore_runner.cancel()
        self._cancel_index_build()
        self.last_error = ""
        self._generation += 1
        generation = self._generation
        self._cancel = threading.Event()
        merge_base_index = (
            self.last_result.index
            if merge
            and self.last_result is not None
            and self.last_result.lazy
            else None
        )
        stream_index: SearchIndex | None = None
        if self._use_streaming() and (
            not merge or merge_base_index is not None
        ):
            space_error = self._index_space_guard(
                bool(merge and merge_base_index is not None)
            )
            if space_error:
                logger.error(space_error)
                self.index_building = False
                self._building_index_path = None
                self._pending_index = None
                self.last_error = space_error
                self.scanFailed.emit(space_error)
                return
            try:
                stream_index = SearchIndex.create(self.index_dir)
            except Exception:
                allow_fallback = bool(
                    self.config.get("scan.allow_memory_fallback", False)
                )
                if not allow_fallback:
                    logger.exception(
                        "falha ao preparar o índice; análise cancelada para "
                        "evitar varredura em RAM"
                    )
                    self.index_building = False
                    self._building_index_path = None
                    self._pending_index = None
                    self.last_error = (
                        "não foi possível criar o índice de busca; a análise "
                        "não foi iniciada para evitar consumo excessivo de "
                        "memória. Verifique espaço/permissões e tente novamente."
                    )
                    self.scanFailed.emit(self.last_error)
                    return
                logger.exception(
                    "falha ao preparar o índice; fallback explícito para RAM"
                )
                max_entries = min(max_entries, MIN_ENTRIES)
                merge = False
                merge_base_index = None
                scan_roots = list(self.roots)
                stream_index = None
                self._scan_budget_total = max_entries
                self._current_limit_entries = max_entries
        self._pending_index = stream_index
        self.index_building = stream_index is not None
        self._building_index_path = (
            stream_index.path if stream_index is not None else None
        )
        if merge and merge_base_index is not None and stream_index is None:
            logger.warning(
                "índice temporário indisponível; refazendo a análise completa"
            )
            scan_roots = list(self.roots)
            merge = False
            max_entries = self._scan_limit()
        task = ScanTask(
            scan_roots,
            self._cancel,
            max_entries=max_entries,
            index=stream_index,
            merge_base=merge_base_index,
        )
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

    def _cancel_index_build(self) -> None:
        """Interrompe a indexação anterior antes de outra árvore grande."""
        if not self.index_building and not self._index_runner.busy:
            return
        self._index_generation += 1
        self._index_runner.cancel()
        if self._building_index_path is not None:
            logger.info(
                "indexação anterior cancelada: %s", self._building_index_path
            )
        self._building_index_path = None
        self.index_building = False

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
        counts: dict[tuple[str, str], int] = {}
        for warning in (*base.warnings, *extra.warnings):
            key = (warning.operation, warning.category)
            counts[key] = counts.get(key, 0) + warning.count
        merged.warnings = [
            ScanWarning(operation=operation, category=category, count=count)
            for (operation, category), count in sorted(counts.items())
        ]
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
            if result.index is not None and result.index is not self.search_index:
                result.index.delete(managed_dir=self.index_dir)
            self._discard_pending_index()
            QTimer.singleShot(0, self.start_scan)
            return
        if result.index is not None:
            self._publish_stream_result(result)
            return
        if merge_base is not None:
            base_entries = merge_base.total_files + merge_base.total_dirs
            extra_entries = result.total_files + result.total_dirs
            budget_total = self._scan_budget_total or MAX_ENTRIES
            if base_entries + extra_entries > budget_total:
                logger.error(
                    "mesclagem recusada: %s + %s entradas excedem o teto %s",
                    base_entries,
                    extra_entries,
                    budget_total,
                )
                self.last_result = merge_base
                self.last_error = (
                    "a nova pasta excederia o limite agregado de análise; "
                    "o snapshot anterior foi preservado"
                )
                self.scanFailed.emit(self.last_error)
                return
            result = self._merge_results(merge_base, result)
        clear_author_cache()
        self.last_result = result
        try:
            self._store_summary(result)
        except Exception:
            logger.exception("falha ao persistir o resumo da análise")
        logger.info(
            "scan done gen=%s files=%s dirs=%s size=%s elapsed_s=%.3f "
            "suggestions=%s truncated=%s",
            generation,
            result.total_files,
            result.total_dirs,
            result.total_size,
            result.elapsed,
            len(result.suggestions),
            result.truncated,
        )
        if result.warnings:
            logger.info(
                "scan warnings gen=%s %s",
                generation,
                ", ".join(
                    f"{warning.operation}/{warning.category}={warning.count}"
                    for warning in result.warnings
                ),
            )
        self.scanFinished.emit(result)
        self._schedule_index(result)

    def _discard_pending_index(self) -> None:
        index = self._pending_index
        self._pending_index = None
        self.index_building = False
        self._building_index_path = None
        if index is not None and index is not self.search_index:
            index.delete(managed_dir=self.index_dir)

    def _publish_stream_result(self, result: ScanResult) -> None:
        index = result.index
        if index is None:
            return
        old = self.search_index
        old_path = str(old.path) if old is not None else ""
        previous = str(
            self.config.get("scan.index_previous_path", "") or ""
        )
        new_previous = (
            old_path if old_path and old_path != str(index.path) else previous
        )
        values: dict[str, object] = {
            "scan.index_path": str(index.path),
            "scan.index_previous_path": new_previous,
            "scan.index_entries": index.stats.rows,
            "scan.indexed_roots": [root.path for root in result.roots],
            "scan.index_verified_at": 0,
        }
        if not self._save_index_config(values):
            logger.error(
                "análise indexada concluída, mas não foi possível publicar "
                "as referências do índice; o snapshot anterior foi mantido"
            )
            self.index_building = False
            self._building_index_path = None
            self._pending_index = None
            if index is not self.search_index:
                index.delete(managed_dir=self.index_dir)
            self.last_error = (
                "análise não persistida: falha ao publicar a configuração "
                "do índice; o snapshot anterior foi preservado"
            )
            self.scanFailed.emit(self.last_error)
            return
        self.search_index = index
        self.index_building = False
        self._building_index_path = None
        self._pending_index = None
        clear_author_cache()
        self.last_result = result
        try:
            self._store_summary(result)
        except Exception:
            logger.exception("falha ao persistir o resumo da análise")
        logger.info(
            "scan done (stream) files=%s dirs=%s size=%s elapsed_s=%.3f "
            "suggestions=%s truncated=%s",
            result.total_files,
            result.total_dirs,
            result.total_size,
            result.elapsed,
            len(result.suggestions),
            result.truncated,
        )
        if result.warnings:
            logger.info(
                "scan warnings (stream) %s",
                ", ".join(
                    f"{warning.operation}/{warning.category}={warning.count}"
                    for warning in result.warnings
                ),
            )
        self.scanFinished.emit(result)
        self.searchIndexReady.emit(index)
        self._emit_pending_roots()
        self._collect_index_garbage(
            protected_paths=[index.path, new_previous]
        )

    def _drop_index(
        self,
        emit: bool = True,
        clear_config: bool = False,
        delete_files: bool = True,
    ) -> None:
        old = self.search_index
        previous_raw = str(
            self.config.get("scan.index_previous_path", "") or ""
        )
        paths: list[Path] = []
        if old is not None:
            paths.append(old.path)
        if previous_raw:
            paths.append(Path(previous_raw))
        self.search_index = None
        self.index_building = False
        self._building_index_path = None
        if clear_config and not self._clear_index_reference():
            delete_files = False
            logger.warning(
                "referências do índice não foram limpas; arquivos preservados"
            )
        if delete_files:
            for path in paths:
                SearchIndex(path).delete(managed_dir=self.index_dir)
        if emit:
            self.searchIndexCleared.emit()
        self.indexUsageChanged.emit()

    def _schedule_index(self, result: ScanResult) -> None:
        """Constrói e persiste o sidecar SQLite de toda análise concluída."""
        self._index_generation += 1
        generation = self._index_generation
        self._index_runner.cancel()
        if not result.roots or self._closing:
            self.index_building = False
            self._building_index_path = None
            if not self._closing:
                self.search_index = None
            return
        try:
            index = SearchIndex.create(self.index_dir)
        except Exception as exc:
            self.index_building = False
            self._building_index_path = None
            self.search_index = None
            logger.exception("falha ao preparar o índice de busca")
            self.searchIndexFailed.emit(str(exc))
            return
        self.index_building = True
        self._building_index_path = index.path
        task = IndexTask(result, index)
        task.signals.finished.connect(
            lambda value, gen=generation: self._on_index_ready(gen, value)
        )
        task.signals.failed.connect(
            lambda message, gen=generation: self._on_index_failed(gen, message)
        )
        self._index_runner.submit(task)

    def _on_index_ready(self, generation: int, index: SearchIndex) -> None:
        if generation != self._index_generation or self._closing:
            index.delete(managed_dir=self.index_dir)
            return
        old = self.search_index
        old_path = str(old.path) if old is not None else ""
        previous = str(
            self.config.get("scan.index_previous_path", "") or ""
        )
        new_previous = (
            old_path if old_path and old_path != str(index.path) else previous
        )
        expected_roots = list(index.snapshot_roots)
        if not expected_roots and self.last_result is not None:
            expected_roots = [root.path for root in self.last_result.roots]
        values: dict[str, object] = {
            "scan.index_path": str(index.path),
            "scan.index_previous_path": new_previous,
            "scan.index_entries": index.stats.rows,
            "scan.indexed_roots": expected_roots,
            "scan.index_verified_at": 0,
        }
        if not self._save_index_config(values):
            self.index_building = False
            self._building_index_path = None
            # O snapshot anterior permanece referenciado na configuração e
            # não é apagado. O novo índice nunca foi publicado.
            self.search_index = None
            index.delete(managed_dir=self.index_dir)
            logger.error("índice construído, mas não publicado")
            self.searchIndexFailed.emit(
                "falha ao publicar o índice de busca"
            )
            self._emit_pending_roots()
            return
        self.search_index = index
        self.index_building = False
        self._building_index_path = None
        stats = index.stats
        logger.info(
            "índice de busca pronto: %s (rows=%s, %.1f ms, "
            "case_collision_groups=%s, case_collision_paths=%s, "
            "sample_hashes=%s, diagnostics=%s)",
            index.path,
            stats.rows,
            stats.elapsed_ms,
            stats.case_collision_groups,
            stats.case_collision_paths,
            stats.sample_hashes,
            stats.diagnostics_path or "-",
        )
        self._collect_index_garbage(
            protected_paths=[index.path, new_previous]
        )
        self.searchIndexReady.emit(index)
        self._emit_pending_roots()

    def _on_index_failed(self, generation: int, message: str) -> None:
        if generation != self._index_generation:
            return
        self.index_building = False
        self._building_index_path = None
        # O índice antigo continua no disco e referenciado para rollback, mas
        # não representa mais a árvore atual; a busca cai para memória.
        self.search_index = None
        logger.error("falha ao construir o índice de busca: %s", message)
        self.searchIndexFailed.emit(message)
        self._emit_pending_roots()

    def _collect_index_garbage(
        self, protected_paths: list[str] | None = None
    ) -> None:
        protected = {path for path in (protected_paths or []) if path}
        if self._building_index_path is not None:
            protected.add(str(self._building_index_path))
        for key in ("scan.index_path", "scan.index_previous_path"):
            raw = str(self.config.get(key, "") or "")
            if raw:
                protected.add(raw)
        try:
            removed = SearchIndex.prune(
                self.index_dir,
                protected_paths=protected,
                keep=0,
                min_age_seconds=INDEX_GC_AGE_SECONDS,
            )
            if removed:
                logger.info("índices órfãos removidos: %s", removed)
        except Exception:
            logger.exception("falha ao limpar índices órfãos")
        self._enforce_index_retention()

    def _index_quota_bytes(self) -> int:
        try:
            gigabytes = float(self.config.get("scan.index_max_gb", 8) or 8)
        except (TypeError, ValueError):
            gigabytes = 8.0
        if gigabytes <= 0:
            return 0
        return int(gigabytes * 1024**3)

    def _index_previous_seconds(self) -> float:
        try:
            days = float(
                self.config.get("scan.index_previous_days", 7) or 7
            )
        except (TypeError, ValueError):
            days = 7.0
        return max(0.0, days) * 24 * 60 * 60

    def index_usage(self) -> dict[str, object]:
        """Tamanho e snapshots gerenciados, para a UI e para a quota."""
        total = 0
        snapshots = 0
        active_raw = str(self.config.get("scan.index_path", "") or "")
        previous_raw = str(
            self.config.get("scan.index_previous_path", "") or ""
        )
        active_path = Path(active_raw) if active_raw else None
        previous_path = Path(previous_raw) if previous_raw else None
        active_bytes = 0
        previous_bytes = 0
        for database in self.index_dir.glob("search-*.sqlite"):
            if not is_managed_index(database, self.index_dir):
                continue
            snapshots += 1
            size = 0
            for suffix in ("", "-wal", "-shm"):
                try:
                    size += Path(str(database) + suffix).stat().st_size
                except OSError:
                    continue
            total += size
            if active_path is not None and database == active_path:
                active_bytes = size
            if previous_path is not None and database == previous_path:
                previous_bytes = size
        return {
            "total_bytes": total,
            "active_bytes": active_bytes,
            "previous_bytes": previous_bytes,
            "snapshots": snapshots,
            "quota_bytes": self._index_quota_bytes(),
            "active_path": active_raw,
            "previous_path": previous_raw,
            "previous_exists": bool(
                previous_path is not None and previous_path.is_file()
            ),
            "active_exists": bool(
                active_path is not None and active_path.is_file()
            ),
        }

    def _delete_previous_index(self, reason: str) -> bool:
        raw = str(self.config.get("scan.index_previous_path", "") or "")
        if not raw:
            return False
        path = Path(raw)
        if self.search_index is not None and self.search_index.path == path:
            return False
        active_raw = str(self.config.get("scan.index_path", "") or "")
        if active_raw and self._path_identity(path) == self._path_identity(
            active_raw
        ):
            return False
        if not is_managed_index(path, self.index_dir):
            logger.warning(
                "índice anterior fora da pasta gerenciada; referência limpa"
            )
            self._save_index_config({"scan.index_previous_path": ""})
            return False
        if not self._save_index_config({"scan.index_previous_path": ""}):
            logger.warning(
                "não foi possível limpar a referência do índice anterior"
            )
            return False
        removed = SearchIndex(path).delete(managed_dir=self.index_dir)
        logger.info("índice anterior removido (%s): %s", reason, path)
        self.indexUsageChanged.emit()
        return removed

    def clear_previous_index(self) -> bool:
        """Remove o rollback anterior sem tocar no índice ativo."""
        return self._delete_previous_index("solicitação do usuário")

    def _enforce_index_retention(self) -> None:
        previous_raw = str(
            self.config.get("scan.index_previous_path", "") or ""
        )
        quota = self._index_quota_bytes()
        usage = self.index_usage()
        if not previous_raw:
            if quota and int(usage["total_bytes"]) > quota:
                logger.warning(
                    "quota do índice excedida sem snapshot anterior: %s > %s",
                    usage["total_bytes"],
                    quota,
                )
            self.indexUsageChanged.emit()
            return
        previous = Path(previous_raw)
        if not previous.is_file():
            self._save_index_config({"scan.index_previous_path": ""})
            self.indexUsageChanged.emit()
            return
        try:
            age = time.time() - previous.stat().st_mtime
        except OSError:
            age = 0.0
        verified = False
        try:
            verified = float(
                self.config.get("scan.index_verified_at", 0) or 0
            ) > 0
        except (TypeError, ValueError):
            verified = False
        expired = age >= self._index_previous_seconds()
        pressure = bool(quota and int(usage["total_bytes"]) > quota)
        eligible = verified and (expired or (pressure and age >= 24 * 60 * 60))
        if eligible:
            self._delete_previous_index(
                "expirado" if expired else "quota"
            )
        else:
            if expired and not verified:
                logger.info(
                    "índice anterior expirado, mas o ativo ainda não foi "
                    "restaurado com sucesso; snapshot preservado"
                )
            if pressure:
                logger.warning(
                    "quota do índice excedida: %s > %s",
                    usage["total_bytes"],
                    quota,
                )
        self.indexUsageChanged.emit()

    def _emit_pending_roots(self) -> None:
        pending = self.pending_roots
        signature = tuple(path_key(path) for path in pending)
        if signature == self._pending_signature:
            return
        self._pending_signature = signature
        if pending:
            logger.warning(
                "raízes solicitadas fora do snapshot persistido: %s",
                len(pending),
            )
        self.rootsPending.emit(pending)

    @property
    def pending_roots(self) -> list[str]:
        if not self.roots:
            return []
        active = str(self.config.get("scan.index_path", "") or "")
        if not active:
            if self.index_building or self.last_result is None:
                return []
            return list(self.roots)
        raw_indexed = self.config.get("scan.indexed_roots", None)
        if isinstance(raw_indexed, list) and raw_indexed:
            indexed = {path_key(str(path)) for path in raw_indexed}
        elif self.last_result is not None:
            indexed = {
                path_key(root.path) for root in self.last_result.roots
            }
        else:
            return []
        return [path for path in self.roots if path_key(path) not in indexed]

    @Slot(int)
    def _on_cancelled(self, generation: int) -> None:
        if generation != self._generation:
            return
        self._finish_task(generation)
        if self._pending_restart:
            self._pending_restart = False
            self._discard_pending_index()
            QTimer.singleShot(0, self.start_scan)
            return
        self._discard_pending_index()
        logger.info("scan cancelled gen=%s", generation)
        self.scanCancelled.emit()

    @Slot(int, str)
    def _on_failed(self, generation: int, message: str) -> None:
        if generation != self._generation:
            return
        self._finish_task(generation)
        if self._pending_restart:
            self._pending_restart = False
            self._discard_pending_index()
            QTimer.singleShot(0, self.start_scan)
            return
        self._discard_pending_index()
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
            "suggestions": [
                _suggestion_payload(suggestion)
                for suggestion in result.suggestions
            ],
            "index_path": str(getattr(result, "index_path", "") or ""),
            "index_entries": (
                int(result.index.stats.rows)
                if getattr(result, "index", None) is not None
                else 0
            ),
            "warnings": [
                {
                    "operation": warning.operation,
                    "category": warning.category,
                    "count": warning.count,
                }
                for warning in result.warnings
            ],
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
                "suggestions": [
                    _suggestion_payload(suggestion)
                    for suggestion in self.last_result.suggestions
                ],
                "index_path": str(
                    getattr(self.last_result, "index_path", "") or ""
                ),
                "index_entries": (
                    int(self.last_result.index.stats.rows)
                    if getattr(self.last_result, "index", None) is not None
                    else 0
                ),
                "warnings": [
                    {
                        "operation": warning.operation,
                        "category": warning.category,
                        "count": warning.count,
                    }
                    for warning in self.last_result.warnings
                ],
            }
        stored = self.config.get("scan.summary", {})
        return stored if isinstance(stored, dict) else {}

    @property
    def suggestions(self) -> list[Suggestion]:
        if self.last_result is not None:
            return self.last_result.suggestions
        stored = self.config.get("scan.summary", {})
        if not isinstance(stored, dict):
            return []
        raw = stored.get("suggestions", [])
        if not isinstance(raw, list):
            return []
        restored: list[Suggestion] = []
        for item in raw:
            suggestion = _suggestion_from_payload(item)
            if suggestion is not None:
                restored.append(suggestion)
        return restored

    @property
    def busy(self) -> bool:
        return self._task is not None

    def shutdown(self) -> None:
        self._closing = True
        self._pending_restart = False
        try:
            self._retention_timer.stop()
        except RuntimeError:
            pass
        self._restore_queue.clear()
        self._restore_index = None
        logger.info("shutdown solicitado")
        if self._cancel is not None:
            self._cancel.set()
        try:
            # O TaskRunner aguarda as threads e mantém os sinais vivos até o
            # término; não destruímos um QThread em execução.
            if not self._runner.shutdown():
                logger.warning("encerramento com varredura ainda ativa")
        except Exception:
            logger.exception("falha ao encerrar o pool de varredura")
        try:
            if not self._index_runner.shutdown():
                logger.warning("encerramento com indexação ainda ativa")
        except Exception:
            logger.exception("falha ao encerrar o pool do índice")
        try:
            if not self._restore_runner.shutdown():
                logger.warning("encerramento com restauração ainda ativa")
        except Exception:
            logger.exception("falha ao encerrar o pool de restauração")
        self._index_generation += 1
        self._restore_generation += 1
        # Não apagar o índice: ele é a análise persistida para a próxima sessão.
        try:
            self.config.save()
        except Exception:
            logger.exception("falha ao salvar a configuração no encerramento")
