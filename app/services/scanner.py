"""Varredura de diretórios em segundo plano, cancelável e com progresso.

A travessia é iterativa e ignora junctions/reparse points do Windows. Isso
evita ciclos (por exemplo ``Documents and Settings`` apontando para ``Users``)
e evita estouro de pilha em árvores muito profundas.
"""

from __future__ import annotations

import os
import stat as stat_module
import threading
import time
from pathlib import Path
from typing import Callable

from .model import Node, ScanProgress, ScanResult
from .suggestions import build_suggestions


class ScanCancelled(Exception):
    pass


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


class _Scanner:
    def __init__(
        self,
        roots: list[str],
        cancel: threading.Event,
        progress_cb: Callable[[ScanProgress], None] | None = None,
        max_entries: int = 1_500_000,
    ) -> None:
        self.roots = roots
        self.cancel = cancel
        self.progress_cb = progress_cb
        self.max_entries = max_entries
        self.progress = ScanProgress(roots_total=len(roots))
        self.visited = 0
        self.errors = 0
        self.truncated = False
        self._last_emit = 0.0
        self._started = time.monotonic()

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
        result = ScanResult(
            roots=nodes,
            total_size=sum(n.size for n in nodes),
            total_files=sum(n.files for n in nodes),
            total_dirs=sum(n.dirs for n in nodes),
            errors=self.errors,
            elapsed=elapsed,
            started_at=started_wall,
            truncated=self.truncated,
        )
        self._check()
        result.suggestions = build_suggestions(result)
        self._check()
        return result

    def _scan_root(self, path: str) -> Node:
        self._check()
        try:
            st = os.stat(path, follow_symlinks=False)
        except OSError as exc:
            self.errors += 1
            return Node(path=path, name=_display_name(path), is_dir=True, error=str(exc))

        node = Node(
            path=path,
            name=_display_name(path),
            is_dir=True,
            mtime=getattr(st, "st_mtime", 0.0),
            dirs=1,
        )
        self.visited += 1
        self.progress.dirs += 1
        if self.visited > self.max_entries:
            self.truncated = True
            return node

        seen: set[tuple[int, int]] = set()
        root_id = _file_id(st)
        if root_id is not None:
            seen.add(root_id)
        self._walk(node, seen)
        return node

    def _walk(self, root: Node, seen: set[tuple[int, int]]) -> None:
        try:
            root_iterator = os.scandir(root.path)
        except OSError as exc:
            self.errors += 1
            root.error = str(exc)
            return

        # (diretório pai, iterator do diretório, nó pai para agregação)
        stack: list[tuple[Node, object, Node | None]] = [(root, root_iterator, None)]
        try:
            while stack:
                self._check()
                node, iterator, parent = stack[-1]
                try:
                    entry = next(iterator)  # type: ignore[arg-type]
                except StopIteration:
                    try:
                        iterator.close()  # type: ignore[attr-defined]
                    except Exception:
                        pass
                    stack.pop()
                    if parent is not None:
                        parent.size += node.size
                        parent.files += node.files
                        parent.dirs += node.dirs
                    continue
                except OSError as exc:
                    self.errors += 1
                    node.error = str(exc)
                    try:
                        iterator.close()  # type: ignore[attr-defined]
                    except Exception:
                        pass
                    stack.pop()
                    if parent is not None:
                        parent.size += node.size
                        parent.files += node.files
                        parent.dirs += node.dirs
                    continue

                if self.visited >= self.max_entries:
                    self.truncated = True
                    break

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
                        child = Node(
                            path=entry.path,
                            name=entry.name,
                            is_dir=True,
                            mtime=getattr(child_st, "st_mtime", 0.0),
                            dirs=1,
                        )
                        node.children.append(child)
                        self.visited += 1
                        self.progress.dirs += 1
                        if child_id is not None:
                            seen.add(child_id)
                        try:
                            child_iterator = os.scandir(entry.path)
                        except OSError as exc:
                            self.errors += 1
                            child.error = str(exc)
                            node.dirs += child.dirs
                            continue
                        stack.append((child, child_iterator, node))
                    elif entry.is_file(follow_symlinks=False):
                        fst = entry.stat(follow_symlinks=False)
                        child = Node(
                            path=entry.path,
                            name=entry.name,
                            is_dir=False,
                            size=int(fst.st_size),
                            mtime=getattr(fst, "st_mtime", 0.0),
                            files=1,
                        )
                        node.children.append(child)
                        node.size += child.size
                        node.files += 1
                        self.visited += 1
                        self.progress.files += 1
                        self.progress.bytes_seen += child.size
                except OSError:
                    self.errors += 1
                    continue
                self._emit()
            if stack and self.truncated:
                # Fecha/agrega o que estava aberto para que os totais parciais
                # reflitam tudo o que foi visitado até o limite.
                while stack:
                    node, iterator, parent = stack.pop()
                    try:
                        iterator.close()  # type: ignore[attr-defined]
                    except Exception:
                        pass
                    if parent is not None:
                        parent.size += node.size
                        parent.files += node.files
                        parent.dirs += node.dirs
        finally:
            # Em cancelamento/truncamento, fecha iteradores que ficaram abertos.
            for _node, iterator, _parent in stack:
                try:
                    iterator.close()  # type: ignore[attr-defined]
                except Exception:
                    pass


def scan_paths(
    roots: list[str],
    cancel: threading.Event | None = None,
    progress_cb: Callable[[ScanProgress], None] | None = None,
    max_entries: int = 1_500_000,
) -> ScanResult:
    """Executa a varredura de forma síncrona. Use em uma thread de trabalho."""
    token = cancel or threading.Event()
    scanner = _Scanner(roots, token, progress_cb, max_entries=max_entries)
    return scanner.run()
