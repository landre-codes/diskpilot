"""Varredura de diretórios em segundo plano, cancelável e com progresso.

A travessia é iterativa e ignora junctions/reparse points do Windows. Isso
evita ciclos (por exemplo ``Documents and Settings`` apontando para ``Users``)
e evita estouro de pilha em árvores muito profundas.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import stat as stat_module
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from appshell.tasks import TaskCancelled

from .limits import MAX_ENTRIES
from .model import Node, ScanProgress, ScanResult, ScanWarning
from .suggestions import build_suggestions


logger = logging.getLogger("diskpilot.scanner")


class ScanCancelled(Exception):
    pass


def _warning_category(exc: OSError) -> str:
    if isinstance(exc, PermissionError):
        return "permission_denied"
    if isinstance(exc, FileNotFoundError):
        return "not_found"
    errno = getattr(exc, "errno", None)
    winerror = getattr(exc, "winerror", None)
    if errno in (13, 5) or winerror == 5:
        return "permission_denied"
    if errno == 2 or winerror in (2, 3):
        return "not_found"
    if errno == 36 or winerror == 206:
        return "path_too_long"
    return "io_error"


def _display_name(path: str) -> str:
    drive, tail = os.path.splitdrive(path)
    if drive and tail in ("\\", "/", ""):
        return drive + "\\"
    name = Path(path.rstrip("\\/")).name
    return name or path


def _file_id(st: os.stat_result) -> tuple[int, int] | None:
    inode = getattr(st, "st_ino", 0)
    device = getattr(st, "st_dev", 0)
    return (device, inode) if inode else None


def _is_reparse(st: os.stat_result) -> bool:
    attrs = getattr(st, "st_file_attributes", 0)
    flag = getattr(stat_module, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(flag and attrs & flag)


class _ScanBudget:
    """Limite de entradas compartilhado pelas raízes paralelas."""

    def __init__(self, limit: int) -> None:
        self.limit = max(1, int(limit))
        self.used = 0
        self.truncated = False
        self._lock = threading.Lock()

    def reserve(self) -> bool:
        with self._lock:
            if self.used >= self.limit:
                self.truncated = True
                return False
            self.used += 1
            return True


class _ProgressAggregator:
    """Combina o progresso de várias raízes sem regredir os contadores."""

    def __init__(
        self,
        total: int,
        callback: Callable[[ScanProgress], None] | None,
    ) -> None:
        self.total = total
        self.callback = callback
        self._lock = threading.Lock()
        self._children: dict[int, tuple[int, int, int, str, int]] = {}
        self._done: set[int] = set()
        self._seq = 0
        self._last_emit = 0.0

    def child_callback(self, index: int) -> Callable[[ScanProgress], None]:
        def update(progress: ScanProgress) -> None:
            now = time.monotonic()
            with self._lock:
                self._seq += 1
                self._children[index] = (
                    progress.files,
                    progress.dirs,
                    progress.bytes_seen,
                    progress.current,
                    self._seq,
                )
                if now - self._last_emit < 0.13:
                    return
                self._last_emit = now
                snapshot = self._snapshot_locked()
            if self.callback is not None:
                self.callback(snapshot)

        return update

    def finish(self, index: int) -> None:
        with self._lock:
            self._done.add(index)
            self._last_emit = time.monotonic()
            snapshot = self._snapshot_locked()
        if self.callback is not None:
            self.callback(snapshot)

    def _snapshot_locked(self) -> ScanProgress:
        files = sum(item[0] for item in self._children.values())
        dirs = sum(item[1] for item in self._children.values())
        bytes_seen = sum(item[2] for item in self._children.values())
        current = ""
        if self._children:
            current = max(self._children.values(), key=lambda item: item[4])[3]
        return ScanProgress(
            files=files,
            dirs=dirs,
            bytes_seen=bytes_seen,
            current=current,
            roots_done=len(self._done),
            roots_total=self.total,
        )


class _Scanner:
    def __init__(
        self,
        roots: list[str],
        cancel: threading.Event,
        progress_cb: Callable[[ScanProgress], None] | None = None,
        max_entries: int = MAX_ENTRIES,
        budget: _ScanBudget | None = None,
        sink: Any = None,
    ) -> None:
        self.roots = roots
        self.cancel = cancel
        self.progress_cb = progress_cb
        self.max_entries = max_entries
        self.budget = budget or _ScanBudget(max_entries)
        self.sink = sink
        self.progress = ScanProgress(roots_total=len(roots))
        self.visited = 0
        self.errors = 0
        self.warning_counts: dict[tuple[str, str], int] = {}
        self.truncated = False
        self._last_emit = 0.0
        self._started = time.monotonic()

    def _record_warning(self, operation: str, exc: OSError) -> None:
        key = (operation, _warning_category(exc))
        self.warning_counts[key] = self.warning_counts.get(key, 0) + 1
        self.errors += 1

    def _reserve(self) -> bool:
        if self.budget.reserve():
            self.visited += 1
            return True
        self.truncated = True
        return False

    def _check(self) -> None:
        if self.cancel.is_set():
            raise ScanCancelled()

    def _emit(self, force: bool = False) -> None:
        if self.progress_cb is None:
            return
        now = time.monotonic()
        if force or now - self._last_emit >= 0.13:
            self._last_emit = now
            self.progress_cb(self.progress)

    def run(self) -> ScanResult:
        started_wall = time.time()
        nodes: list[Node] = []
        for index, root in enumerate(self.roots):
            self._check()
            self.progress.current = root
            node = self._scan_root(root)
            nodes.append(node)
            self.progress.roots_done = index + 1
            self._emit(force=True)
            if self.truncated:
                break
        elapsed = time.monotonic() - self._started
        warnings = [
            ScanWarning(operation=operation, category=category, count=count)
            for (operation, category), count in sorted(self.warning_counts.items())
        ]
        result = ScanResult(
            roots=nodes,
            total_size=sum(n.size for n in nodes),
            total_files=sum(n.files for n in nodes),
            total_dirs=sum(n.dirs for n in nodes),
            errors=self.errors,
            elapsed=elapsed,
            started_at=started_wall,
            truncated=self.truncated or self.budget.truncated,
            warnings=warnings,
        )
        self._check()
        if self.sink is None:
            result.suggestions = build_suggestions(result)
        self._check()
        return result

    def scan_single(self) -> Node:
        """Varre apenas uma raiz; usado pelo orquestrador paralelo."""
        self._check()
        if not self.roots:
            raise ValueError("nenhuma raiz para varrer")
        root = self.roots[0]
        self.progress.current = root
        node = self._scan_root(root)
        self.progress.roots_done = 1
        self._emit(force=True)
        return node

    def _scan_root(self, path: str) -> Node:
        self._check()
        try:
            st = os.stat(path, follow_symlinks=False)
        except OSError as exc:
            self._record_warning("stat_root", exc)
            node = Node(
                path=path,
                name=_display_name(path),
                is_dir=True,
                error=str(exc),
            )
            if self.sink is not None:
                self.sink.start_root(node)
                self.sink.finish_dir(node.node_id, 0, 0, 0)
            return node

        node = Node(
            path=path,
            name=_display_name(path),
            is_dir=True,
            mtime=getattr(st, "st_mtime", 0.0),
            dirs=1,
        )
        if not self._reserve():
            # A raiz não entrou no orçamento; não pode inflar os totais.
            node.dirs = 0
            if self.sink is not None:
                self.sink.start_root(node)
                self.sink.finish_dir(node.node_id, 0, 0, 0)
            return node
        self.progress.dirs += 1
        if self.sink is not None:
            self.sink.start_root(node)

        seen: set[tuple[int, int]] = set()
        root_id = _file_id(st)
        if root_id is not None:
            seen.add(root_id)
        self._walk(node, seen)
        if self.sink is not None:
            self.sink.finish_dir(
                node.node_id, node.size, node.files, node.dirs
            )
        return node

    def _walk(self, root: Node, seen: set[tuple[int, int]]) -> None:
        try:
            root_iterator = os.scandir(root.path)
        except OSError as exc:
            self._record_warning("list_root", exc)
            root.error = str(exc)
            return

        # (diretório, iterator, pai para agregação, profundidade)
        stack: list[tuple[Node, Any, Node | None, int]] = [
            (root, root_iterator, None, 0)
        ]
        try:
            while stack:
                self._check()
                node, iterator, parent, depth = stack[-1]
                try:
                    entry = next(iterator)
                except StopIteration:
                    try:
                        iterator.close()
                    except Exception:
                        pass
                    stack.pop()
                    if parent is not None:
                        if self.sink is not None:
                            self.sink.finish_dir(
                                node.node_id,
                                node.size,
                                node.files,
                                node.dirs,
                            )
                        parent.size += node.size
                        parent.files += node.files
                        parent.dirs += node.dirs
                    continue
                except OSError as exc:
                    self._record_warning("iterate_dir", exc)
                    node.error = str(exc)
                    try:
                        iterator.close()
                    except Exception:
                        pass
                    stack.pop()
                    if parent is not None:
                        if self.sink is not None:
                            self.sink.finish_dir(
                                node.node_id,
                                node.size,
                                node.files,
                                node.dirs,
                            )
                        parent.size += node.size
                        parent.files += node.files
                        parent.dirs += node.dirs
                    continue

                self.progress.current = entry.path
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        child_st = entry.stat(follow_symlinks=False)
                        # Junctions, mount points e outros reparse points
                        # podem criar ciclos; não entramos neles.
                        if _is_reparse(child_st):
                            continue
                        child_id = _file_id(child_st)
                        if child_id is not None and child_id in seen:
                            continue
                        if not self._reserve():
                            break
                        child = Node(
                            path=entry.path,
                            name=entry.name,
                            is_dir=True,
                            mtime=getattr(child_st, "st_mtime", 0.0),
                            dirs=1,
                        )
                        node.children_total += 1
                        if self.sink is not None:
                            self.sink.start_dir(
                                child,
                                node.node_id,
                                root.node_id,
                                depth + 1,
                            )
                        else:
                            node.children.append(child)
                        self.progress.dirs += 1
                        if child_id is not None:
                            seen.add(child_id)
                        try:
                            child_iterator = os.scandir(entry.path)
                        except OSError as exc:
                            self._record_warning("list_dir", exc)
                            child.error = str(exc)
                            if self.sink is not None:
                                self.sink.finish_dir(
                                    child.node_id, 0, 0, child.dirs
                                )
                            node.dirs += child.dirs
                            continue
                        stack.append(
                            (child, child_iterator, node, depth + 1)
                        )
                    elif entry.is_file(follow_symlinks=False):
                        fst = entry.stat(follow_symlinks=False)
                        if not self._reserve():
                            break
                        child = Node(
                            path=entry.path,
                            name=entry.name,
                            is_dir=False,
                            size=int(fst.st_size),
                            mtime=getattr(fst, "st_mtime", 0.0),
                            files=1,
                        )
                        node.children_total += 1
                        if self.sink is not None:
                            self.sink.add_file(
                                child,
                                node.node_id,
                                root.node_id,
                                depth + 1,
                            )
                        else:
                            node.children.append(child)
                        node.size += child.size
                        node.files += 1
                        self.progress.files += 1
                        self.progress.bytes_seen += child.size
                except OSError as exc:
                    self._record_warning("read_entry", exc)
                    continue
                self._emit()
            if stack and self.truncated:
                # Fecha/agrega o que estava aberto para que os totais parciais
                # reflitam tudo o que foi visitado até o limite.
                while stack:
                    node, iterator, parent, _depth = stack.pop()
                    try:
                        iterator.close()
                    except Exception:
                        pass
                    if parent is not None:
                        if self.sink is not None:
                            self.sink.finish_dir(
                                node.node_id,
                                node.size,
                                node.files,
                                node.dirs,
                            )
                        parent.size += node.size
                        parent.files += node.files
                        parent.dirs += node.dirs
        finally:
            # Em cancelamento/truncamento, fecha iteradores que ficaram abertos.
            for _node, iterator, _parent, _depth in stack:
                try:
                    iterator.close()
                except Exception:
                    pass


def _parallel_root(
    index: int,
    root: str,
    token: threading.Event,
    aggregator: _ProgressAggregator,
    max_entries: int,
    budget: _ScanBudget,
) -> tuple[int, Node, dict[tuple[str, str], int], bool]:
    scanner = _Scanner(
        [root],
        token,
        progress_cb=aggregator.child_callback(index),
        max_entries=max_entries,
        budget=budget,
    )
    node = scanner.scan_single()
    return index, node, dict(scanner.warning_counts), scanner.truncated


def _scan_parallel(
    roots: list[str],
    token: threading.Event,
    progress_cb: Callable[[ScanProgress], None] | None,
    max_entries: int,
) -> ScanResult:
    started = time.monotonic()
    started_wall = time.time()
    aggregator = _ProgressAggregator(len(roots), progress_cb)
    budget = _ScanBudget(max_entries)
    results: dict[int, Node] = {}
    errors = 0
    warning_counts: dict[tuple[str, str], int] = {}
    truncated = False
    workers = min(len(roots), max(1, min(4, os.cpu_count() or 2)))
    with ThreadPoolExecutor(
        max_workers=workers, thread_name_prefix="diskpilot-scan"
    ) as pool:
        futures = {
            pool.submit(
                _parallel_root,
                index,
                root,
                token,
                aggregator,
                max_entries,
                budget,
            ): index
            for index, root in enumerate(roots)
        }
        try:
            for future in as_completed(futures):
                index, node, child_warnings, child_truncated = future.result()
                results[index] = node
                for key, count in child_warnings.items():
                    warning_counts[key] = warning_counts.get(key, 0) + count
                    errors += count
                truncated = truncated or child_truncated
                aggregator.finish(index)
                if token.is_set():
                    break
        except Exception:
            token.set()
            for future in futures:
                future.cancel()
            raise
    if token.is_set():
        raise ScanCancelled()
    nodes = [results[index] for index in range(len(roots)) if index in results]
    warnings = [
        ScanWarning(operation=operation, category=category, count=count)
        for (operation, category), count in sorted(warning_counts.items())
    ]
    result = ScanResult(
        roots=nodes,
        total_size=sum(node.size for node in nodes),
        total_files=sum(node.files for node in nodes),
        total_dirs=sum(node.dirs for node in nodes),
        errors=errors,
        elapsed=time.monotonic() - started,
        started_at=started_wall,
        truncated=truncated or budget.truncated,
        warnings=warnings,
    )
    result.suggestions = build_suggestions(result)
    if token.is_set():
        raise ScanCancelled()
    return result


def scan_paths(
    roots: list[str],
    cancel: threading.Event | None = None,
    progress_cb: Callable[[ScanProgress], None] | None = None,
    max_entries: int = MAX_ENTRIES,
    sink: Any = None,
) -> ScanResult:
    """Varre raízes independentes em paralelo quando há mais de uma."""
    token = cancel or threading.Event()
    if sink is not None:
        # A escrita em um único SQLite é sequencial por desenho.
        return _Scanner(
            roots, token, progress_cb, max_entries=max_entries, sink=sink
        ).run()
    if len(roots) > 1 and (os.cpu_count() or 1) > 1:
        return _scan_parallel(roots, token, progress_cb, max_entries)
    scanner = _Scanner(roots, token, progress_cb, max_entries=max_entries)
    return scanner.run()


def stream_scan_paths(
    roots: list[str],
    index: Any,
    cancel: threading.Event | None = None,
    progress_cb: Callable[[ScanProgress], None] | None = None,
    max_entries: int = MAX_ENTRIES,
    suggestions: bool = True,
) -> ScanResult:
    """Varre e grava os nós diretamente no índice, sem árvore completa."""
    from .index_store import IndexWriter

    token = cancel or threading.Event()
    writer = IndexWriter(index, cancel=token)
    try:
        scanner = _Scanner(
            roots,
            token,
            progress_cb,
            max_entries=max_entries,
            sink=writer,
        )
        result = scanner.run()
        writer.finish(result, writer.rows, token)
        if token.is_set():
            writer.discard()
            raise TaskCancelled()
        result.lazy = True
        result.index_path = str(index.path)
        result.index = index
        if suggestions:
            try:
                result.suggestions = build_suggestions(result)
            except Exception:
                logger.exception("falha ao calcular sugestões indexadas")
                result.suggestions = []
            if token.is_set():
                writer.discard()
                raise TaskCancelled()
        return result
    except sqlite3.OperationalError as exc:
        writer.discard()
        if token.is_set():
            raise TaskCancelled() from exc
        raise
    except BaseException:
        writer.discard()
        raise
    finally:
        writer.close()
