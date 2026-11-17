"""Índice SQLite opcional para buscas em análises grandes.

O índice não substitui a árvore em memória nesta fase: ele funciona como um
sidecar para consultas de nome. A árvore e o resumo continuam no ``ScanResult``;
quando o volume cresce, a busca deixa de percorrer ``Node.name`` em Python e
passa a usar o FTS5 do SQLite.
"""

from __future__ import annotations

import json
import sqlite3
import time
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from appshell.tasks import Task, TaskCancelled
from appshell.utils import path_key

from .model import Node, ScanResult


SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id          INTEGER PRIMARY KEY,
    created_at  REAL NOT NULL,
    roots_json  TEXT NOT NULL,
    total_size  INTEGER NOT NULL,
    total_files INTEGER NOT NULL,
    total_dirs  INTEGER NOT NULL,
    errors      INTEGER NOT NULL,
    truncated   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS nodes (
    id         INTEGER PRIMARY KEY,
    scan_id    INTEGER NOT NULL,
    parent_id  INTEGER,
    root_id    INTEGER NOT NULL,
    name       TEXT NOT NULL,
    name_fold  TEXT NOT NULL,
    path       TEXT NOT NULL,
    path_key   TEXT NOT NULL,
    is_dir     INTEGER NOT NULL,
    size       INTEGER NOT NULL,
    mtime      REAL NOT NULL,
    files      INTEGER NOT NULL,
    dirs       INTEGER NOT NULL,
    depth      INTEGER NOT NULL,
    error      TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
    name_fold,
    content='',
    tokenize='trigram'
);
"""

INDEXES = """
CREATE INDEX IF NOT EXISTS idx_nodes_parent
    ON nodes(scan_id, parent_id, size DESC);
CREATE INDEX IF NOT EXISTS idx_nodes_root
    ON nodes(scan_id, root_id);
CREATE INDEX IF NOT EXISTS idx_nodes_top
    ON nodes(scan_id, is_dir, size DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_nodes_path
    ON nodes(scan_id, path_key);
"""


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


@dataclass(slots=True)
class SearchHits:
    paths: list[str]
    matches: int


class SearchIndex:
    """Arquivo SQLite independente, seguro para consultas em outra thread."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    @classmethod
    def create(cls, base_dir: str | Path) -> "SearchIndex":
        base = Path(base_dir)
        base.mkdir(parents=True, exist_ok=True)
        cls.prune(base)
        return cls(base / f"search-{uuid.uuid4().hex}.sqlite")

    @staticmethod
    def prune(base_dir: str | Path, keep: int = 2) -> None:
        """Remove índices antigos, preservando os mais recentes."""
        base = Path(base_dir)
        if not base.is_dir():
            return
        files = sorted(
            base.glob("search-*.sqlite"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for old in files[max(1, keep) :]:
            for suffix in ("", "-wal", "-shm"):
                try:
                    Path(str(old) + suffix).unlink()
                except OSError:
                    pass

    def delete(self) -> None:
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(self.path) + suffix)
            try:
                candidate.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                # A consulta pode estar em andamento no Windows; o arquivo
                # será removido na próxima limpeza.
                return

    def write(
        self,
        result: ScanResult,
        cancel=None,
        progress: Callable[[int, int], None] | None = None,
    ) -> None:
        if self.path.exists():
            self.path.unlink()
        total = max(1, result.total_files + result.total_dirs)
        conn = sqlite3.connect(self.path)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.executescript(SCHEMA)
            with conn:
                conn.execute(
                    "INSERT INTO scans VALUES (1, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        result.started_at or time.time(),
                        json.dumps(
                            [root.path for root in result.roots],
                            ensure_ascii=False,
                        ),
                        result.total_size,
                        result.total_files,
                        result.total_dirs,
                        result.errors,
                        int(result.truncated),
                    ),
                )
                rows: list[tuple] = []
                fts_rows: list[tuple] = []
                node_id = 0
                processed = 0
                stack: list[tuple[Node, int | None, int | None, int]] = [
                    (root, None, None, 0) for root in reversed(result.roots)
                ]
                while stack:
                    if cancel is not None and cancel.is_set():
                        raise TaskCancelled()
                    node, parent_id, root_id, depth = stack.pop()
                    node_id += 1
                    if root_id is None:
                        root_id = node_id
                    rows.append(
                        (
                            node_id,
                            1,
                            parent_id,
                            root_id,
                            node.name,
                            _fold(node.name),
                            node.path,
                            path_key(node.path),
                            int(node.is_dir),
                            node.size,
                            node.mtime,
                            node.files,
                            node.dirs,
                            depth,
                            node.error,
                        )
                    )
                    fts_rows.append((node_id, _fold(node.name)))
                    processed += 1
                    for child in reversed(node.children):
                        stack.append((child, node_id, root_id, depth + 1))
                    if len(rows) >= 5000:
                        conn.executemany(
                            "INSERT INTO nodes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            rows,
                        )
                        conn.executemany(
                            "INSERT INTO nodes_fts(rowid, name_fold) VALUES (?,?)",
                            fts_rows,
                        )
                        rows.clear()
                        fts_rows.clear()
                        if progress is not None:
                            progress(processed, total)
                if rows:
                    conn.executemany(
                        "INSERT INTO nodes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        rows,
                    )
                    conn.executemany(
                        "INSERT INTO nodes_fts(rowid, name_fold) VALUES (?,?)",
                        fts_rows,
                    )
            conn.executescript(INDEXES)
            conn.execute("INSERT INTO nodes_fts(nodes_fts) VALUES ('optimize')")
            conn.commit()
            if progress is not None:
                progress(processed, total)
        finally:
            conn.close()

    def search(
        self,
        query: str,
        filter_key: str = "all",
        sort_key: str = "size_desc",
        limit: int = 5000,
    ) -> SearchHits:
        if not self.path.exists():
            return SearchHits([], 0)
        tokens = [_fold(token) for token in query.split() if token.strip()]
        use_fts = bool(tokens) and all(len(token) >= 3 for token in tokens)
        from_sql = "nodes n"
        clauses = ["n.scan_id = 1"]
        params: list[object] = []
        if use_fts:
            from_sql = "nodes_fts CROSS JOIN nodes n ON nodes_fts.rowid = n.id"
            fts_query = " AND ".join(
                '"' + token.replace('"', '""') + '"' for token in tokens
            )
            clauses.append("nodes_fts MATCH ?")
            params.append(fts_query)
        else:
            for token in tokens:
                clauses.append("n.name_fold LIKE ?")
                params.append(f"%{token}%")
        if filter_key == "folders":
            clauses.append("n.is_dir = 1")
        elif filter_key == "files":
            clauses.append("n.is_dir = 0")
        elif filter_key == "large100":
            clauses.append("n.is_dir = 0 AND n.size >= ?")
            params.append(100 * 1024 * 1024)
        elif filter_key == "large1g":
            clauses.append("n.is_dir = 0 AND n.size >= ?")
            params.append(1024 * 1024 * 1024)
        order = {
            "size_asc": "n.size ASC, n.name_fold ASC",
            "name_asc": "n.name_fold ASC, n.size DESC",
            "name_desc": "n.name_fold DESC, n.size DESC",
            "recent": "n.mtime DESC, n.size DESC",
        }.get(sort_key, "n.size DESC, n.name_fold ASC")
        where = " AND ".join(clauses)
        conn = sqlite3.connect(self.path)
        try:
            conn.execute("PRAGMA query_only=ON")
            count = conn.execute(
                f"SELECT COUNT(*) FROM {from_sql} WHERE {where}",
                params,
            ).fetchone()[0]
            rows = conn.execute(
                f"SELECT n.path FROM {from_sql} WHERE {where} "
                f"ORDER BY {order} LIMIT ?",
                [*params, max(1, int(limit))],
            ).fetchall()
        finally:
            conn.close()
        return SearchHits([str(row[0]) for row in rows], int(count))


class IndexTask(Task):
    """Constrói o índice em segundo plano."""

    def __init__(self, result: ScanResult, index: SearchIndex) -> None:
        super().__init__()
        self.result = result
        self.index = index

    def execute(self) -> SearchIndex:
        try:
            self.index.write(
                self.result,
                cancel=self.cancel,
                progress=lambda done, total: self.signals.progress.emit((done, total)),
            )
        except Exception:
            self.index.delete()
            raise
        return self.index
