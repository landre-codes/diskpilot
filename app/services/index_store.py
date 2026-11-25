"""Índice SQLite opcional para buscas em análises grandes.

O índice não substitui a árvore em memória nesta fase: ele funciona como um
sidecar para consultas de nome. A árvore continua no ``ScanResult`` e o resumo
detalhado é persistido na tabela ``meta`` para restaurar sugestões sem
recalcular todos os arquivos. Quando o volume cresce, a busca deixa de
percorrer ``Node.name`` em Python e passa a usar o FTS5 do SQLite.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import threading
import time
import unicodedata
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from appshell.tasks import Task, TaskCancelled
from appshell.utils import normalize_path, path_key

from .model import Node, ScanResult, ScanWarning


logger = logging.getLogger("diskpilot.index")


SCHEMA_VERSION = 1
MANAGED_INDEX_NAME = re.compile(r"^search-[0-9a-f]{32}\.sqlite$")


def is_managed_index(path: str | Path, base_dir: str | Path) -> bool:
    """True apenas para bancos nomeados pelo DiskPilot na pasta gerenciada."""
    try:
        base = Path(base_dir).resolve()
        target = Path(path).resolve(strict=False)
    except OSError:
        return False
    if target.parent != base:
        return False
    return bool(MANAGED_INDEX_NAME.match(target.name))


SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id          INTEGER PRIMARY KEY,
    created_at  REAL NOT NULL,
    elapsed     REAL NOT NULL DEFAULT 0,
    roots_json  TEXT NOT NULL,
    total_size  INTEGER NOT NULL,
    total_files INTEGER NOT NULL,
    total_dirs  INTEGER NOT NULL,
    errors      INTEGER NOT NULL,
    truncated   INTEGER NOT NULL,
    warnings_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS nodes (
    id         INTEGER PRIMARY KEY,
    scan_id    INTEGER NOT NULL,
    parent_id  INTEGER,
    root_id    INTEGER NOT NULL,
    name       TEXT NOT NULL,
    name_fold  TEXT NOT NULL,
    path       TEXT NOT NULL,
    path_exact TEXT NOT NULL,
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
CREATE INDEX IF NOT EXISTS idx_nodes_path_key
    ON nodes(scan_id, path_key);
CREATE UNIQUE INDEX IF NOT EXISTS idx_nodes_path_exact
    ON nodes(scan_id, path_exact);
"""


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _path_hash(path: str) -> str:
    """Hash curto para diagnóstico sem persistir o caminho completo."""
    return hashlib.sha256(path.encode("utf-8", "surrogatepass")).hexdigest()[:16]


@dataclass(slots=True)
class IndexStats:
    rows: int = 0
    elapsed_ms: float = 0.0
    case_collision_groups: int = 0
    case_collision_paths: int = 0
    sample_hashes: list[str] = field(default_factory=list)
    diagnostics_path: str = ""


class IndexBuildError(RuntimeError):
    """Falha de construção com código estável e detalhes sem caminhos."""

    def __init__(self, code: str, message: str, **details: object) -> None:
        self.code = code
        self.details = details
        summary = f"{code}: {message}"
        if details:
            summary += " " + json.dumps(details, ensure_ascii=False, sort_keys=True)
        super().__init__(summary)


def _duplicate_diagnostics(conn: sqlite3.Connection) -> tuple[int, int, list[str]]:
    """Conta grupos de caminhos exatamente repetidos e devolve hashes de amostra."""
    try:
        total = conn.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(n), 0)
            FROM (
                SELECT path_exact, COUNT(*) AS n
                FROM nodes
                WHERE scan_id = 1
                GROUP BY path_exact
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()
        groups = int(total[0] or 0)
        rows = int(total[1] or 0)
        if not groups:
            return 0, 0, []
        sample = conn.execute(
            """
            SELECT path_exact
            FROM nodes
            WHERE scan_id = 1 AND path_exact IN (
                SELECT path_exact
                FROM nodes
                WHERE scan_id = 1
                GROUP BY path_exact
                HAVING COUNT(*) > 1
                ORDER BY COUNT(*) DESC, path_exact
                LIMIT 5
            )
            ORDER BY path_exact
            """
        ).fetchall()
        hashes = list(dict.fromkeys(_path_hash(str(row[0])) for row in sample))
        return groups, rows, hashes
    except sqlite3.Error:
        return 0, 0, []


def _case_diagnostics(conn: sqlite3.Connection) -> tuple[int, int, list[str]]:
    """Conta colisões legítimas da chave case-insensitive, sem falhar o índice."""
    try:
        total = conn.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(n), 0)
            FROM (
                SELECT path_key, COUNT(DISTINCT path_exact) AS n
                FROM nodes
                WHERE scan_id = 1
                GROUP BY path_key
                HAVING COUNT(DISTINCT path_exact) > 1
            )
            """
        ).fetchone()
        groups = int(total[0] or 0)
        paths = int(total[1] or 0)
        if not groups:
            return 0, 0, []
        sample = conn.execute(
            """
            SELECT path_exact
            FROM nodes
            WHERE scan_id = 1 AND path_key IN (
                SELECT path_key
                FROM nodes
                WHERE scan_id = 1
                GROUP BY path_key
                HAVING COUNT(DISTINCT path_exact) > 1
                ORDER BY COUNT(DISTINCT path_exact) DESC, path_key
                LIMIT 5
            )
            ORDER BY path_key, path_exact
            """
        ).fetchall()
        hashes = [_path_hash(str(row[0])) for row in sample]
        return groups, paths, hashes[:10]
    except sqlite3.Error:
        return 0, 0, []


@dataclass(slots=True)
class SearchHits:
    paths: list[str]
    matches: int


class SearchIndex:
    """Arquivo SQLite independente, seguro para consultas em outra thread."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.stats = IndexStats()
        self.snapshot_roots: list[str] = []
        self._node_loader = self.children_for_node

    @classmethod
    def create(cls, base_dir: str | Path) -> "SearchIndex":
        base = Path(base_dir)
        base.mkdir(parents=True, exist_ok=True)
        # A poda não pertence à criação: o índice ativo e o de rollback podem
        # ser mais antigos que um arquivo órfão. A limpeza é feita depois da
        # publicação, com proteção explícita por identidade.
        return cls(base / f"search-{uuid.uuid4().hex}.sqlite")

    @classmethod
    def merge_indexes(
        cls,
        sources: list["SearchIndex"],
        target: "SearchIndex",
        cancel: threading.Event | None = None,
    ) -> None:
        """Consolida índices prontos em um novo snapshot, sem árvore em RAM."""
        if not sources:
            raise ValueError("nenhum índice para consolidar")
        conn = sqlite3.connect(target.path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.executescript(SCHEMA)

        def interrupted() -> int:
            return 1 if cancel is not None and cancel.is_set() else 0

        if cancel is not None:
            conn.set_progress_handler(interrupted, 2000)
        try:
            sources_data = []
            offset = 0
            total_nodes = 0
            total_size = 0
            total_files = 0
            total_dirs = 0
            errors = 0
            elapsed = 0.0
            started_at = 0.0
            truncated = False
            roots: list[str] = []
            warning_counts: dict[tuple[str, str], int] = {}
            for index, source in enumerate(sources):
                alias = f"src{index}"
                conn.execute(
                    f"ATTACH DATABASE ? AS {alias}", (str(source.path),)
                )
                max_id = int(
                    conn.execute(
                        f"SELECT COALESCE(MAX(id), 0) FROM {alias}.nodes"
                    ).fetchone()[0]
                )
                count = int(
                    conn.execute(
                        f"SELECT COUNT(*) FROM {alias}.nodes"
                    ).fetchone()[0]
                )
                node_columns = {
                    str(row[1])
                    for row in conn.execute(
                        f"PRAGMA {alias}.table_info(nodes)"
                    )
                }
                path_expr = (
                    "path_exact"
                    if "path_exact" in node_columns
                    else "path"
                )
                scan_columns = {
                    str(row[1])
                    for row in conn.execute(
                        f"PRAGMA {alias}.table_info(scans)"
                    )
                }
                warnings_expr = (
                    "warnings_json"
                    if "warnings_json" in scan_columns
                    else "'[]'"
                )
                scan = conn.execute(
                    f"SELECT created_at, elapsed, roots_json, total_size, "
                    f"total_files, total_dirs, errors, truncated, "
                    f"{warnings_expr} FROM {alias}.scans WHERE id = 1"
                ).fetchone()
                if scan is None:
                    raise IndexBuildError(
                        "merge_source", "índice de origem sem resumo"
                    )
                sources_data.append((alias, offset, path_expr))
                offset += max_id
                total_nodes += count
                started_at = started_at or float(scan[0] or 0.0)
                elapsed += float(scan[1] or 0.0)
                roots.extend(json.loads(scan[2] or "[]"))
                total_size += int(scan[3] or 0)
                total_files += int(scan[4] or 0)
                total_dirs += int(scan[5] or 0)
                errors += int(scan[6] or 0)
                truncated = truncated or bool(scan[7])
                try:
                    warning_rows = json.loads(scan[8] or "[]")
                except (TypeError, ValueError):
                    warning_rows = []
                if isinstance(warning_rows, list):
                    for warning in warning_rows:
                        if not isinstance(warning, dict):
                            continue
                        key = (
                            str(warning.get("operation", "")),
                            str(warning.get("category", "")),
                        )
                        warning_counts[key] = warning_counts.get(key, 0) + int(
                            warning.get("count", 1)
                        )

            for alias, shift, path_expr in sources_data:
                if cancel is not None and cancel.is_set():
                    raise TaskCancelled()
                conn.execute(
                    f"""
                    INSERT INTO nodes (
                        id, scan_id, parent_id, root_id, name, name_fold,
                        path, path_exact, path_key, is_dir, size, mtime,
                        files, dirs, depth, error
                    )
                    SELECT id + ?, 1,
                           CASE WHEN parent_id IS NULL
                                THEN NULL ELSE parent_id + ? END,
                           root_id + ?, name, name_fold, path, {path_expr},
                           path_key, is_dir, size, mtime, files, dirs,
                           depth, error
                    FROM {alias}.nodes
                    """,
                    (shift, shift, shift),
                )

            # FTS contentless: reconstruir a partir da tabela final é mais
            # seguro do que copiar rowids de fontes anexadas.
            conn.execute(
                "INSERT INTO nodes_fts(rowid, name_fold) "
                "SELECT id, name_fold FROM nodes"
            )

            conn.execute(
                "INSERT INTO scans VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    started_at or time.time(),
                    elapsed,
                    json.dumps(roots, ensure_ascii=False),
                    total_size,
                    total_files,
                    total_dirs,
                    errors,
                    int(truncated),
                    json.dumps(
                        [
                            {
                                "operation": operation,
                                "category": category,
                                "count": count,
                            }
                            for (operation, category), count in sorted(
                                warning_counts.items()
                            )
                        ],
                        ensure_ascii=False,
                    ),
                ),
            )
            conn.executescript(INDEXES)
            conn.execute("INSERT INTO nodes_fts(nodes_fts) VALUES ('optimize')")
            if cancel is not None and cancel.is_set():
                raise TaskCancelled()
            meta = [
                ("schema_version", str(SCHEMA_VERSION)),
                ("complete", "1"),
                ("node_count", str(total_nodes)),
                ("roots_json", json.dumps(roots, ensure_ascii=False)),
                ("created_at", str(time.time())),
            ]
            conn.executemany(
                "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", meta
            )
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            conn.commit()
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            target.snapshot_roots = roots
            target.stats = IndexStats(rows=total_nodes)
        except Exception as exc:
            try:
                conn.close()
            except sqlite3.Error:
                pass
            target.delete()
            if (
                isinstance(exc, sqlite3.OperationalError)
                and cancel is not None
                and cancel.is_set()
            ):
                raise TaskCancelled() from exc
            raise
        finally:
            if cancel is not None:
                try:
                    conn.set_progress_handler(None, 0)
                except sqlite3.Error:
                    pass
            conn.close()

    @staticmethod
    def prune(
        base_dir: str | Path,
        protected_paths: Iterable[str | Path] = (),
        keep: int = 1,
        min_age_seconds: float = 24 * 60 * 60,
    ) -> int:
        """Remove apenas órfãos gerenciados, antigos e não protegidos.

        ``keep`` preserva os arquivos não protegidos mais recentes. Idade e
        quota são critérios secundários; a proteção por caminho é soberana.
        """
        base = Path(base_dir)
        if not base.is_dir():
            return 0
        protected: set[Path] = set()
        for raw in protected_paths:
            if not raw:
                continue
            try:
                protected.add(Path(raw).resolve(strict=False))
            except OSError:
                continue
        candidates: list[tuple[float, Path]] = []
        for candidate in base.glob("search-*.sqlite"):
            if not is_managed_index(candidate, base):
                continue
            try:
                candidates.append((candidate.stat().st_mtime, candidate))
            except OSError:
                continue
        candidates.sort(key=lambda item: item[0], reverse=True)
        unprotected = [
            item
            for item in candidates
            if item[1].resolve(strict=False) not in protected
        ]
        now = time.time()
        removed = 0
        for mtime, old in unprotected[max(0, int(keep)) :]:
            if now - mtime < max(0.0, float(min_age_seconds)):
                continue
            if SearchIndex(old).delete(managed_dir=base):
                removed += 1
        for suffix in ("-wal", "-shm"):
            for auxiliary in base.glob(f"search-*{suffix}"):
                database = Path(str(auxiliary)[: -len(suffix)])
                if not is_managed_index(database, base) or database.exists():
                    continue
                try:
                    mtime = auxiliary.stat().st_mtime
                except OSError:
                    continue
                if now - mtime < max(0.0, float(min_age_seconds)):
                    continue
                try:
                    auxiliary.unlink()
                    removed += 1
                except OSError:
                    continue
        return removed

    def delete(self, managed_dir: str | Path | None = None) -> bool:
        """Remove o banco e auxiliares; fora da pasta gerenciada, recusa."""
        if managed_dir is not None and not is_managed_index(self.path, managed_dir):
            logger.warning(
                "recusa ao excluir índice fora do diretório gerenciado: %s",
                self.path,
            )
            return False
        removed = True
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(self.path) + suffix)
            for _attempt in range(4):
                try:
                    candidate.unlink()
                    break
                except FileNotFoundError:
                    break
                except OSError:
                    # A consulta pode estar em andamento no Windows.
                    time.sleep(0.05)
            else:
                removed = False
        return removed

    def _diagnostics_target(self) -> Path | None:
        raw = os.environ.get("DISKPILOT_INDEX_DIAGNOSTICS", "").strip()
        if not raw:
            return None
        if raw.lower() in {"1", "true", "yes", "on"}:
            return self.path.with_suffix(".diagnostics.json")
        target = Path(raw).expanduser()
        if raw.endswith(("/", "\\")) or target.is_dir():
            target = target / f"{self.path.stem}.diagnostics.json"
        return target

    def _write_diagnostics(
        self, conn: sqlite3.Connection, target: Path
    ) -> Path:
        """Grava caminhos completos somente quando o opt-in explícito existe."""
        duplicate_groups = []
        for path_exact, count in conn.execute(
            """
            SELECT path_exact, COUNT(*) AS n
            FROM nodes
            WHERE scan_id = 1
            GROUP BY path_exact
            HAVING COUNT(*) > 1
            ORDER BY n DESC, path_exact
            LIMIT 50
            """
        ).fetchall():
            nodes = conn.execute(
                """
                SELECT id, parent_id, root_id, path, path_key, is_dir, size
                FROM nodes
                WHERE scan_id = 1 AND path_exact = ?
                ORDER BY id
                LIMIT 20
                """,
                (path_exact,),
            ).fetchall()
            duplicate_groups.append(
                {
                    "path_exact": path_exact,
                    "count": count,
                    "nodes": [
                        {
                            "id": row[0],
                            "parent_id": row[1],
                            "root_id": row[2],
                            "path": row[3],
                            "path_key": row[4],
                            "is_dir": bool(row[5]),
                            "size": row[6],
                        }
                        for row in nodes
                    ],
                }
            )

        case_groups = []
        for path_key_value, count in conn.execute(
            """
            SELECT path_key, COUNT(DISTINCT path_exact) AS n
            FROM nodes
            WHERE scan_id = 1
            GROUP BY path_key
            HAVING COUNT(DISTINCT path_exact) > 1
            ORDER BY n DESC, path_key
            LIMIT 50
            """
        ).fetchall():
            variants = conn.execute(
                """
                SELECT path_exact, COUNT(*) AS n
                FROM nodes
                WHERE scan_id = 1 AND path_key = ?
                GROUP BY path_exact
                ORDER BY path_exact
                LIMIT 20
                """,
                (path_key_value,),
            ).fetchall()
            case_groups.append(
                {
                    "path_key": path_key_value,
                    "variant_count": count,
                    "variants": [
                        {"path": row[0], "count": row[1]} for row in variants
                    ],
                }
            )

        payload = {
            "generated_at": time.strftime(
                "%Y-%m-%dT%H:%M:%S", time.localtime()
            ),
            "scan_id": 1,
            "warning": (
                "Arquivo de diagnóstico local com caminhos completos. "
                "Gerado apenas porque DISKPILOT_INDEX_DIAGNOSTICS foi definido."
            ),
            "duplicate_groups": duplicate_groups,
            "case_groups": case_groups,
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        logger.warning("diagnóstico local do índice gravado em %s", target)
        return target

    def _try_write_diagnostics(
        self, conn: sqlite3.Connection
    ) -> Path | None:
        target = self._diagnostics_target()
        if target is None:
            return None
        try:
            return self._write_diagnostics(conn, target)
        except (OSError, sqlite3.Error) as exc:
            logger.warning("falha ao gravar diagnóstico local: %s", exc)
            return None

    def write(
        self,
        result: ScanResult,
        cancel: threading.Event | None = None,
        progress: Callable[[int, int], None] | None = None,
    ) -> None:
        started = time.monotonic()
        self.stats = IndexStats()
        self.snapshot_roots = [root.path for root in result.roots]
        if cancel is not None and cancel.is_set():
            raise TaskCancelled()
        if self.path.exists():
            self.path.unlink()
        total = max(1, result.total_files + result.total_dirs)
        conn = sqlite3.connect(self.path)
        processed = 0
        ok = False

        def interrupted() -> int:
            return 1 if cancel is not None and cancel.is_set() else 0

        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=FULL")
            if cancel is not None:
                conn.set_progress_handler(interrupted, 1000)
            conn.executescript(SCHEMA)
            with conn:
                conn.execute(
                    "INSERT INTO scans VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        result.started_at or time.time(),
                        result.elapsed,
                        json.dumps(
                            [root.path for root in result.roots],
                            ensure_ascii=False,
                        ),
                        result.total_size,
                        result.total_files,
                        result.total_dirs,
                        result.errors,
                        int(result.truncated),
                        json.dumps(
                            [
                                {
                                    "operation": warning.operation,
                                    "category": warning.category,
                                    "count": warning.count,
                                }
                                for warning in result.warnings
                            ],
                            ensure_ascii=False,
                        ),
                    ),
                )
                rows: list[tuple] = []
                fts_rows: list[tuple] = []
                node_id = 0
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
                            normalize_path(node.path),
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
                            "INSERT INTO nodes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
                        "INSERT INTO nodes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        rows,
                    )
                    conn.executemany(
                        "INSERT INTO nodes_fts(rowid, name_fold) VALUES (?,?)",
                        fts_rows,
                    )
            try:
                conn.executescript(INDEXES)
            except sqlite3.IntegrityError as exc:
                if "path_exact" in str(exc):
                    groups, duplicate_rows, hashes = _duplicate_diagnostics(conn)
                    details: dict[str, object] = {
                        "groups": groups,
                        "rows": duplicate_rows,
                        "sample_hashes": hashes,
                    }
                    diagnostics = self._try_write_diagnostics(conn)
                    if diagnostics is not None:
                        details["diagnostics"] = str(diagnostics)
                    raise IndexBuildError(
                        "duplicate_path",
                        "mais de um nó com o mesmo caminho exato",
                        **details,
                    ) from exc
                raise IndexBuildError("sqlite_integrity", str(exc)) from exc
            conn.execute("INSERT INTO nodes_fts(nodes_fts) VALUES ('optimize')")
            if cancel is not None and cancel.is_set():
                raise TaskCancelled()
            meta = [
                ("schema_version", str(SCHEMA_VERSION)),
                ("complete", "1"),
                ("node_count", str(processed)),
                ("roots_json", json.dumps(self.snapshot_roots, ensure_ascii=False)),
                ("created_at", str(time.time())),
            ]
            conn.executemany(
                "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", meta
            )
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            conn.commit()
            if cancel is not None and cancel.is_set():
                raise TaskCancelled()
            try:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except sqlite3.Error as exc:
                logger.warning("checkpoint do índice não concluído: %s", exc)
            case_groups, case_paths, hashes = _case_diagnostics(conn)
            diagnostics = (
                self._try_write_diagnostics(conn) if case_groups else None
            )
            self.stats = IndexStats(
                rows=processed,
                elapsed_ms=(time.monotonic() - started) * 1000.0,
                case_collision_groups=case_groups,
                case_collision_paths=case_paths,
                sample_hashes=hashes,
                diagnostics_path=str(diagnostics or ""),
            )
            ok = True
            if progress is not None:
                progress(processed, total)
        except TaskCancelled:
            raise
        except IndexBuildError:
            raise
        except sqlite3.OperationalError as exc:
            if cancel is not None and cancel.is_set():
                raise TaskCancelled() from exc
            raise IndexBuildError("sqlite_error", str(exc)) from exc
        except sqlite3.Error as exc:
            raise IndexBuildError("sqlite_error", str(exc)) from exc
        finally:
            try:
                conn.close()
            finally:
                if not ok:
                    self.delete()

    def _invalid(self, reason: str) -> None:
        logger.warning("índice persistido rejeitado: %s", reason)

    def load_result(
        self,
        cancel: threading.Event | None = None,
        lazy: bool = False,
    ) -> ScanResult | None:
        """Reconstrói o ScanResult persistido, se o banco estiver íntegro.

        A leitura é feita em lotes e respeita ``cancel``. Hierarquia órfã,
        ciclos, contagens incompatíveis e snapshots sem publicação confirmada
        são rejeitados em vez de produzir uma árvore aparentemente válida.
        """
        if cancel is not None and cancel.is_set():
            raise TaskCancelled()
        if not self.path.is_file():
            return None
        conn: sqlite3.Connection | None = None

        def interrupted() -> int:
            return 1 if cancel is not None and cancel.is_set() else 0

        try:
            conn = sqlite3.connect(self.path)
            conn.execute("PRAGMA query_only=ON")
            if cancel is not None:
                conn.set_progress_handler(interrupted, 1000)
            tables = {
                str(row[0])
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            if "scans" not in tables or "nodes" not in tables:
                self._invalid("tabelas obrigatórias ausentes")
                return None
            columns = {
                row[1] for row in conn.execute("PRAGMA table_info(scans)")
            }
            warnings_expr = (
                "warnings_json" if "warnings_json" in columns else "'[]'"
            )
            scan = conn.execute(
                "SELECT created_at, elapsed, roots_json, total_size, "
                "total_files, total_dirs, errors, truncated, "
                f"{warnings_expr} FROM scans WHERE id = 1"
            ).fetchone()
            if scan is None:
                self._invalid("registro da análise ausente")
                return None

            if "meta" in tables:
                meta = dict(
                    conn.execute("SELECT key, value FROM meta").fetchall()
                )
                if meta.get("complete") != "1":
                    self._invalid("snapshot sem confirmação de conclusão")
                    return None
                version = meta.get("schema_version")
                if version is not None:
                    try:
                        if int(version) != SCHEMA_VERSION:
                            self._invalid("versão de esquema incompatível")
                            return None
                    except (TypeError, ValueError):
                        self._invalid("versão de esquema inválida")
                        return None
            else:
                logger.info(
                    "índice legado sem metadados; aplicando validação estrutural"
                )

            total_files = int(scan[4])
            total_dirs = int(scan[5])
            minimum_nodes = total_files + total_dirs
            if minimum_nodes < 0:
                self._invalid("contadores negativos")
                return None
            actual_nodes = int(
                conn.execute(
                    "SELECT COUNT(*) FROM nodes WHERE scan_id = 1"
                ).fetchone()[0]
            )
            if actual_nodes < minimum_nodes:
                self._invalid("contagem de nós incompatível com o resumo")
                return None
            if "meta" in tables:
                raw_count = meta.get("node_count")
                if raw_count is not None:
                    try:
                        if int(raw_count) != actual_nodes:
                            self._invalid("metadados de contagem divergentes")
                            return None
                    except (TypeError, ValueError):
                        self._invalid("metadados de contagem inválidos")
                        return None

            try:
                raw_roots = json.loads(scan[2] or "[]")
            except (TypeError, ValueError):
                self._invalid("lista de raízes inválida")
                return None
            if not isinstance(raw_roots, list) or not raw_roots:
                self._invalid("snapshot sem raízes")
                return None
            expected_root_keys = {path_key(str(path)) for path in raw_roots}

            if lazy:
                root_rows = conn.execute(
                    "SELECT id, name, path, is_dir, size, mtime, files, dirs, "
                    "error FROM nodes WHERE scan_id = 1 AND parent_id IS NULL "
                    "ORDER BY id"
                ).fetchall()
                if len(root_rows) != len(raw_roots):
                    self._invalid("quantidade de raízes incompatível")
                    return None
                if {path_key(str(row[2])) for row in root_rows} != (
                    expected_root_keys
                ):
                    self._invalid(
                        "raízes restauradas não correspondem ao snapshot"
                    )
                    return None
                checks = (
                    (
                        "SELECT COUNT(*) FROM nodes WHERE scan_id = 1 "
                        "AND is_dir = 0",
                        total_files,
                        "quantidade de arquivos incompatível com o resumo",
                    ),
                    (
                        "SELECT COUNT(*) FROM nodes WHERE scan_id = 1 "
                        "AND is_dir = 1 AND dirs > 0",
                        total_dirs,
                        "quantidade de pastas incompatível com o resumo",
                    ),
                )
                for statement, expected, reason in checks:
                    if int(conn.execute(statement).fetchone()[0]) != expected:
                        self._invalid(reason)
                        return None
                malformed = conn.execute(
                    "SELECT "
                    "COALESCE(SUM(CASE WHEN is_dir = 0 AND files != 1 "
                    "THEN 1 ELSE 0 END), 0), "
                    "COALESCE(SUM(CASE WHEN parent_id IS NOT NULL AND "
                    "is_dir = 1 AND dirs <= 0 THEN 1 ELSE 0 END), 0), "
                    "COALESCE(SUM(CASE WHEN parent_id IS NULL AND "
                    "is_dir = 1 AND dirs = 0 AND files != 0 THEN 1 ELSE 0 END), 0) "
                    "FROM nodes WHERE scan_id = 1"
                ).fetchone()
                if any(int(value) for value in malformed):
                    self._invalid("contagens inválidas em nós")
                    return None
                zero_roots = int(
                    conn.execute(
                        "SELECT COUNT(*) FROM nodes WHERE scan_id = 1 "
                        "AND parent_id IS NULL AND is_dir = 1 "
                        "AND dirs = 0 AND files = 0"
                    ).fetchone()[0]
                )
                if actual_nodes - minimum_nodes != zero_roots:
                    self._invalid(
                        "nós sem contabilização não são raízes vazias"
                    )
                    return None
                orphaned = int(
                    conn.execute(
                        "SELECT COUNT(*) FROM nodes n LEFT JOIN nodes p "
                        "ON p.id = n.parent_id WHERE n.scan_id = 1 "
                        "AND n.parent_id IS NOT NULL AND p.id IS NULL"
                    ).fetchone()[0]
                )
                if orphaned:
                    self._invalid("nó órfão com parent_id inexistente")
                    return None
                cyclic = int(
                    conn.execute(
                        "SELECT COUNT(*) FROM nodes WHERE scan_id = 1 "
                        "AND parent_id IS NOT NULL AND parent_id >= id"
                    ).fetchone()[0]
                )
                if cyclic:
                    self._invalid("parent_id não anterior ao filho (ciclo)")
                    return None
                inconsistent = int(
                    conn.execute(
                        "SELECT COUNT(*) FROM nodes n LEFT JOIN nodes p "
                        "ON p.id = n.parent_id WHERE n.scan_id = 1 AND ("
                        "(n.parent_id IS NULL AND n.root_id != n.id) OR "
                        "(n.parent_id IS NOT NULL AND (p.id IS NULL OR "
                        "p.is_dir != 1 OR n.root_id != p.root_id)))"
                    ).fetchone()[0]
                )
                if inconsistent:
                    self._invalid("root_id inconsistente na hierarquia")
                    return None
                roots = []
                for row in root_rows:
                    node = self._row_to_node(row)
                    node.children_loaded = False
                    node.children_loader = self._node_loader
                    node.children_total = int(
                        conn.execute(
                            "SELECT COUNT(*) FROM nodes "
                            "WHERE scan_id = 1 AND parent_id = ?",
                            (node.node_id,),
                        ).fetchone()[0]
                    )
                    roots.append(node)
                warnings: list[ScanWarning] = []
                try:
                    raw_warnings = json.loads(scan[8] or "[]")
                    if isinstance(raw_warnings, list):
                        warnings = [
                            ScanWarning(
                                operation=str(item.get("operation", "")),
                                category=str(item.get("category", "")),
                                count=int(item.get("count", 1)),
                            )
                            for item in raw_warnings
                            if isinstance(item, dict)
                        ]
                except (TypeError, ValueError):
                    warnings = []
                self.snapshot_roots = [str(path) for path in raw_roots]
                self.stats = IndexStats(rows=actual_nodes)
                return ScanResult(
                    roots=roots,
                    total_size=int(scan[3]),
                    total_files=total_files,
                    total_dirs=total_dirs,
                    errors=int(scan[6]),
                    elapsed=float(scan[1] or 0.0),
                    started_at=float(scan[0] or 0.0),
                    truncated=bool(scan[7]),
                    warnings=warnings,
                    lazy=True,
                    index_path=str(self.path),
                    index=self,
                )

            directory_nodes: dict[int, Node] = {}
            directory_roots: dict[int, int] = {}
            roots: list[Node] = []
            file_count = 0
            counted_dirs = 0
            zero_roots = 0
            seen_nodes = 0
            cursor = conn.execute(
                "SELECT id, parent_id, root_id, name, path, is_dir, size, "
                "mtime, files, dirs, error FROM nodes "
                "WHERE scan_id = 1 ORDER BY id"
            )
            while True:
                if cancel is not None and cancel.is_set():
                    raise TaskCancelled()
                batch = cursor.fetchmany(5000)
                if not batch:
                    break
                for (
                    node_id,
                    parent_id,
                    root_id,
                    name,
                    path,
                    is_dir,
                    size,
                    mtime,
                    files,
                    dirs,
                    error,
                ) in batch:
                    key = int(node_id)
                    parent_key = int(parent_id) if parent_id is not None else None
                    root_key = int(root_id)
                    node = Node(
                        path=str(path),
                        name=str(name),
                        is_dir=bool(is_dir),
                        size=int(size),
                        mtime=float(mtime),
                        files=int(files),
                        dirs=int(dirs),
                        error=str(error or ""),
                    )
                    seen_nodes += 1
                    if parent_key is None:
                        if root_key != key:
                            self._invalid("root_id inválido em uma raiz")
                            return None
                        roots.append(node)
                        if node.is_dir:
                            directory_nodes[key] = node
                            directory_roots[key] = key
                            if node.dirs > 0:
                                counted_dirs += 1
                            elif node.files == 0:
                                zero_roots += 1
                            else:
                                self._invalid(
                                    "raiz sem pastas contabilizadas"
                                )
                                return None
                        else:
                            if node.files != 1:
                                self._invalid(
                                    "arquivo com contagem inválida"
                                )
                                return None
                            file_count += 1
                        continue
                    parent = directory_nodes.get(parent_key)
                    if parent is None:
                        self._invalid("nó órfão ou pai não processado")
                        return None
                    if root_key != directory_roots[parent_key]:
                        self._invalid("root_id inconsistente na hierarquia")
                        return None
                    parent.children.append(node)
                    if node.is_dir:
                        if node.dirs <= 0:
                            self._invalid(
                                "pasta sem contabilização fora de uma raiz"
                            )
                            return None
                        counted_dirs += 1
                        directory_nodes[key] = node
                        directory_roots[key] = root_key
                    else:
                        if node.files != 1:
                            self._invalid("arquivo com contagem inválida")
                            return None
                        file_count += 1
            if seen_nodes != actual_nodes:
                self._invalid("quantidade de nós divergente durante a leitura")
                return None
            if len(roots) != len(raw_roots):
                self._invalid("quantidade de raízes incompatível")
                return None
            if {path_key(root.path) for root in roots} != expected_root_keys:
                self._invalid("raízes restauradas não correspondem ao snapshot")
                return None
            if file_count != total_files:
                self._invalid("quantidade de arquivos incompatível com o resumo")
                return None
            if counted_dirs != total_dirs:
                self._invalid("quantidade de pastas incompatível com o resumo")
                return None
            if actual_nodes - minimum_nodes != zero_roots:
                self._invalid("nós sem contabilização não são raízes vazias")
                return None

            warnings: list[ScanWarning] = []
            try:
                raw_warnings = json.loads(scan[8] or "[]")
                if isinstance(raw_warnings, list):
                    warnings = [
                        ScanWarning(
                            operation=str(item.get("operation", "")),
                            category=str(item.get("category", "")),
                            count=int(item.get("count", 1)),
                        )
                        for item in raw_warnings
                        if isinstance(item, dict)
                    ]
            except (TypeError, ValueError):
                warnings = []
            self.snapshot_roots = [str(path) for path in raw_roots]
            self.stats = IndexStats(rows=actual_nodes)
            return ScanResult(
                roots=roots,
                total_size=int(scan[3]),
                total_files=total_files,
                total_dirs=total_dirs,
                errors=int(scan[6]),
                elapsed=float(scan[1] or 0.0),
                started_at=float(scan[0] or 0.0),
                truncated=bool(scan[7]),
                warnings=warnings,
            )
        except TaskCancelled:
            raise
        except sqlite3.OperationalError as exc:
            if cancel is not None and cancel.is_set():
                raise TaskCancelled() from exc
            logger.warning("falha ao carregar o índice persistido: %s", exc)
            return None
        except (sqlite3.Error, TypeError, ValueError) as exc:
            logger.warning("índice persistido inválido: %s", exc)
            return None
        finally:
            if conn is not None:
                if cancel is not None:
                    try:
                        conn.set_progress_handler(None, 0)
                    except sqlite3.Error:
                        pass
                conn.close()

    def remove_root(
        self,
        root_path: str,
        cancel: threading.Event | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> bool:
        """Remove uma raiz do snapshot sem reconstruir o índice."""
        if not self.path.is_file():
            return False
        if cancel is not None and cancel.is_set():
            raise TaskCancelled()
        key = path_key(root_path)
        conn = sqlite3.connect(self.path)
        try:
            if cancel is not None:
                conn.set_progress_handler(
                    lambda: 1 if cancel.is_set() else 0, 1000
                )
            if progress is not None:
                progress("Localizando pasta no índice…")
            row = conn.execute(
                "SELECT id FROM nodes WHERE scan_id = 1 "
                "AND parent_id IS NULL AND path_key = ? LIMIT 1",
                (key,),
            ).fetchone()
            if row is None:
                return False
            root_id = int(row[0])
            tables = {
                str(item[0])
                for item in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            if "nodes_fts" in tables:
                if progress is not None:
                    progress("Limpando índice de busca da pasta…")
                conn.execute(
                    "INSERT INTO nodes_fts(nodes_fts, rowid, name_fold) "
                    "SELECT 'delete', id, name_fold FROM nodes "
                    "WHERE scan_id = 1 AND root_id = ?",
                    (root_id,),
                )
            if cancel is not None and cancel.is_set():
                raise TaskCancelled()
            if progress is not None:
                progress("Removendo nós da pasta…")
            conn.execute(
                "DELETE FROM nodes WHERE scan_id = 1 AND root_id = ?",
                (root_id,),
            )
            if cancel is not None and cancel.is_set():
                raise TaskCancelled()
            roots = conn.execute(
                "SELECT path, size, files, dirs FROM nodes "
                "WHERE scan_id = 1 AND parent_id IS NULL ORDER BY id"
            ).fetchall()
            if not roots:
                conn.rollback()
                return False
            total_size = sum(int(item[1]) for item in roots)
            total_files = sum(int(item[2]) for item in roots)
            total_dirs = sum(int(item[3]) for item in roots)
            paths = [str(item[0]) for item in roots]
            node_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM nodes WHERE scan_id = 1"
                ).fetchone()[0]
            )
            conn.execute(
                "UPDATE scans SET roots_json = ?, total_size = ?, "
                "total_files = ?, total_dirs = ? WHERE id = 1",
                (
                    json.dumps(paths, ensure_ascii=False),
                    total_size,
                    total_files,
                    total_dirs,
                ),
            )
            if "meta" in tables:
                conn.execute("DELETE FROM meta WHERE key = 'summary_json'")
                conn.executemany(
                    "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                    (
                        ("node_count", str(node_count)),
                        (
                            "roots_json",
                            json.dumps(paths, ensure_ascii=False),
                        ),
                    ),
                )
            if progress is not None:
                progress("Publicando snapshot sem a pasta…")
            conn.commit()
            # Sem checkpoint aqui: ele pode bloquear em índices grandes.
            # O WAL é consolidado pelo próximo uso/publicação do índice.
            self.stats = IndexStats(rows=node_count)
            self.snapshot_roots = paths
            return True
        except TaskCancelled:
            try:
                conn.rollback()
            except sqlite3.Error:
                pass
            raise
        except sqlite3.Error:
            try:
                conn.rollback()
            except sqlite3.Error:
                pass
            if cancel is not None and cancel.is_set():
                raise TaskCancelled()
            logger.exception("falha ao remover raiz do índice")
            return False
        finally:
            conn.close()

    def store_summary(self, summary: dict[str, Any]) -> bool:
        """Grava o resumo detalhado na metadata do índice concluído."""
        if not isinstance(summary, dict) or not summary:
            return False
        if not self.path.is_file():
            return False
        payload = json.dumps(summary, ensure_ascii=False)
        conn = sqlite3.connect(self.path)
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS meta ("
                "key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) "
                "VALUES ('summary_json', ?)",
                (payload,),
            )
            conn.commit()
            try:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except sqlite3.Error as exc:
                logger.warning(
                    "checkpoint do resumo não concluído: %s", exc
                )
        except sqlite3.Error:
            logger.exception("falha ao gravar o resumo no índice")
            return False
        finally:
            conn.close()
        return True

    def load_summary(self) -> dict[str, Any] | None:
        """Lê o resumo detalhado persistido na metadata, se existir."""
        if not self.path.is_file():
            return None
        conn = sqlite3.connect(self.path)
        try:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = 'summary_json'"
            ).fetchone()
        except sqlite3.Error:
            return None
        finally:
            conn.close()
        if not row:
            return None
        try:
            payload = json.loads(str(row[0]))
        except (TypeError, ValueError):
            logger.warning("resumo persistido no índice é inválido")
            return None
        return payload if isinstance(payload, dict) else None

    def _row_to_node(self, row: tuple) -> Node:
        return Node(
            path=str(row[2]),
            name=str(row[1]),
            is_dir=bool(row[3]),
            size=int(row[4]),
            mtime=float(row[5]),
            files=int(row[6]),
            dirs=int(row[7]),
            error=str(row[8] or ""),
            node_id=int(row[0]),
            children_loaded=not bool(row[3]),
            children_loader=self._node_loader if bool(row[3]) else None,
        )

    def children_for_node(
        self,
        node: Node,
        sort_key: str = "size_desc",
        limit: int | None = None,
    ) -> list[Node]:
        """Filhos imediatos de um nó, ordenados e limitados no SQLite."""
        if not node.is_dir or node.node_id <= 0:
            node.children_loaded = True
            return []
        if not self.path.is_file():
            node.children_loaded = True
            return []
        order = {
            "size_asc": "size ASC, name_fold ASC",
            "name_asc": "name_fold ASC, size DESC",
            "name_desc": "name_fold DESC, size DESC",
            "recent": "mtime DESC, size DESC",
        }.get(sort_key, "size DESC, name_fold ASC")
        conn = sqlite3.connect(self.path)
        try:
            conn.execute("PRAGMA query_only=ON")
            total = int(
                conn.execute(
                    "SELECT COUNT(*) FROM nodes WHERE scan_id = 1 AND parent_id = ?",
                    (node.node_id,),
                ).fetchone()[0]
            )
            query = (
                "SELECT id, name, path, is_dir, size, mtime, files, dirs, error "
                "FROM nodes WHERE scan_id = 1 AND parent_id = ? "
                f"ORDER BY {order}"
            )
            params: list[object] = [node.node_id]
            if limit is not None:
                query += " LIMIT ?"
                params.append(max(1, int(limit)))
            rows = conn.execute(query, params).fetchall()
        finally:
            conn.close()
        node.children_total = total
        return [self._row_to_node(row) for row in rows]

    def nodes_by_paths(self, paths: Iterable[str]) -> list[Node]:
        """Nós exatos para montar apenas os ramos de uma busca filtrada."""
        normalized = sorted({normalize_path(str(path)) for path in paths})
        if not normalized:
            return []
        if not self.path.is_file():
            return []
        result: list[Node] = []
        conn = sqlite3.connect(self.path)
        try:
            conn.execute("PRAGMA query_only=ON")
            columns = {
                str(row[1])
                for row in conn.execute("PRAGMA table_info(nodes)")
            }
            path_column = (
                "path_exact" if "path_exact" in columns else "path"
            )
            for start in range(0, len(normalized), 400):
                chunk = normalized[start : start + 400]
                placeholders = ",".join("?" for _ in chunk)
                rows = conn.execute(
                    "SELECT id, name, path, is_dir, size, mtime, files, dirs, "
                    f"error FROM nodes WHERE scan_id = 1 AND {path_column} IN "
                    f"({placeholders})",
                    chunk,
                ).fetchall()
                for row in rows:
                    node = self._row_to_node(row)
                    node.children_loaded = True
                    node.children_loader = None
                    result.append(node)
        finally:
            conn.close()
        return result

    def top_items(self, limit: int = 100) -> tuple[list[Node], list[Node]]:
        """Maiores pastas e arquivos, consultados diretamente no SQLite."""
        if limit <= 0:
            return [], []
        if not self.path.is_file():
            return [], []
        conn = sqlite3.connect(self.path)
        try:
            conn.execute("PRAGMA query_only=ON")
            rows = conn.execute(
                "SELECT id, name, path, is_dir, size, mtime, files, dirs, error "
                "FROM nodes WHERE scan_id = 1 AND is_dir = ? "
                "ORDER BY size DESC, name_fold ASC LIMIT ?",
                (1, int(limit)),
            ).fetchall()
            dirs = [self._row_to_node(row) for row in rows]
            rows = conn.execute(
                "SELECT id, name, path, is_dir, size, mtime, files, dirs, error "
                "FROM nodes WHERE scan_id = 1 AND is_dir = 0 "
                "ORDER BY size DESC, name_fold ASC LIMIT ?",
                (int(limit),),
            ).fetchall()
            files = [self._row_to_node(row) for row in rows]
        finally:
            conn.close()
        for node in (*dirs, *files):
            node.children_loaded = True
            node.children_loader = None
        return dirs, files

    def top_root_items(self, limit: int | None = None) -> list[Node]:
        """Itens imediatamente abaixo das raízes, para o resumo do dashboard."""
        if not self.path.is_file():
            return []
        conn = sqlite3.connect(self.path)
        try:
            conn.execute("PRAGMA query_only=ON")
            query = (
                "SELECT id, name, path, is_dir, size, mtime, files, dirs, error "
                "FROM nodes WHERE scan_id = 1 AND parent_id IN "
                "(SELECT id FROM nodes WHERE scan_id = 1 AND parent_id IS NULL) "
                "ORDER BY size DESC, name_fold ASC"
            )
            params: list[object] = []
            if limit is not None:
                query += " LIMIT ?"
                params.append(max(1, int(limit)))
            rows = conn.execute(query, params).fetchall()
        finally:
            conn.close()
        result = [self._row_to_node(row) for row in rows]
        for node in result:
            node.children_loaded = True
            node.children_loader = None
        return result

    def search(
        self,
        query: str,
        filter_key: str = "all",
        sort_key: str = "size_desc",
        limit: int = 5000,
        cancel: threading.Event | None = None,
    ) -> SearchHits:
        if cancel is not None and cancel.is_set():
            raise TaskCancelled()
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
                literal = (
                    token.replace("!", "!!")
                    .replace("%", "!%")
                    .replace("_", "!_")
                )
                clauses.append("n.name_fold LIKE ? ESCAPE '!'")
                params.append(f"%{literal}%")
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

        def interrupted() -> int:
            return 1 if cancel is not None and cancel.is_set() else 0

        try:
            conn.execute("PRAGMA query_only=ON")
            if cancel is not None:
                conn.set_progress_handler(interrupted, 1000)
            count = conn.execute(
                f"SELECT COUNT(*) FROM {from_sql} WHERE {where}",
                params,
            ).fetchone()[0]
            rows = conn.execute(
                f"SELECT n.path FROM {from_sql} WHERE {where} "
                f"ORDER BY {order} LIMIT ?",
                [*params, max(1, int(limit))],
            ).fetchall()
        except sqlite3.OperationalError as exc:
            if cancel is not None and cancel.is_set():
                raise TaskCancelled() from exc
            raise
        finally:
            if cancel is not None:
                try:
                    conn.set_progress_handler(None, 0)
                except sqlite3.Error:
                    pass
            conn.close()
        return SearchHits([str(row[0]) for row in rows], int(count))


class IndexWriter:
    """Grava nós no SQLite durante a varredura, sem árvore completa em RAM.

    O scanner reserva o id do diretório ao abri-lo e atualiza os agregados ao
    fechá-lo. Assim a ordem dos ids continua sendo pré-ordem, e a árvore pode
    ser carregada sob demanda depois.
    """

    def __init__(
        self, index: SearchIndex, cancel: threading.Event | None = None
    ) -> None:
        self.index = index
        self.conn = sqlite3.connect(index.path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=FULL")
        self.conn.executescript(SCHEMA)
        if cancel is not None:
            self.conn.set_progress_handler(
                lambda: 1 if cancel.is_set() else 0, 1000
            )
        self._rows: list[tuple] = []
        self._fts_rows: list[tuple] = []
        self._updates: list[tuple] = []
        self._next_id = 0
        self._ok = False
        self._closed = False
        self.index.snapshot_roots = []

    @property
    def rows(self) -> int:
        return self._next_id

    def _flush(self) -> None:
        if self._rows:
            self.conn.executemany(
                "INSERT INTO nodes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                self._rows,
            )
            self._rows.clear()
        if self._fts_rows:
            self.conn.executemany(
                "INSERT INTO nodes_fts(rowid, name_fold) VALUES (?,?)",
                self._fts_rows,
            )
            self._fts_rows.clear()
        if self._updates:
            self.conn.executemany(
                "UPDATE nodes SET size = ?, files = ?, dirs = ? WHERE id = ?",
                self._updates,
            )
            self._updates.clear()

    def _append(
        self,
        node: Node,
        parent_id: int | None,
        root_id: int | None,
        depth: int,
        size: int,
        files: int,
        dirs: int,
    ) -> int:
        self._next_id += 1
        node_id = self._next_id
        node.node_id = node_id
        if root_id is None:
            root_id = node_id
        self._rows.append(
            (
                node_id,
                1,
                parent_id,
                root_id,
                str(node.name),
                _fold(str(node.name)),
                str(node.path),
                normalize_path(node.path),
                path_key(node.path),
                int(node.is_dir),
                int(size),
                float(node.mtime),
                int(files),
                int(dirs),
                int(depth),
                str(node.error or ""),
            )
        )
        self._fts_rows.append((node_id, _fold(str(node.name))))
        if len(self._rows) >= 5000:
            self._flush()
        return node_id

    def start_root(self, node: Node) -> int:
        if node.dirs > 0:
            node.children_loaded = False
            node.children_loader = self.index._node_loader
        return self._append(
            node,
            None,
            None,
            0,
            0,
            0,
            1 if node.dirs > 0 else 0,
        )

    def start_dir(
        self,
        node: Node,
        parent_id: int,
        root_id: int,
        depth: int,
    ) -> int:
        node.children_loaded = False
        node.children_loader = self.index._node_loader
        return self._append(node, parent_id, root_id, depth, 0, 0, 1)

    def add_file(
        self,
        node: Node,
        parent_id: int,
        root_id: int,
        depth: int,
    ) -> int:
        return self._append(
            node, parent_id, root_id, depth, node.size, 1, 0
        )

    def finish_dir(
        self, node_id: int, size: int, files: int, dirs: int
    ) -> None:
        self._updates.append((int(size), int(files), int(dirs), int(node_id)))
        if len(self._updates) >= 5000:
            self._flush()

    def finish(
        self,
        result: ScanResult,
        processed: int,
        cancel: threading.Event | None = None,
    ) -> None:
        def check() -> None:
            if cancel is not None and cancel.is_set():
                raise TaskCancelled()

        check()
        self._flush()
        check()
        started = time.monotonic()
        self.conn.execute(
            "INSERT INTO scans VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                result.started_at or time.time(),
                result.elapsed,
                json.dumps(
                    [root.path for root in result.roots],
                    ensure_ascii=False,
                ),
                result.total_size,
                result.total_files,
                result.total_dirs,
                result.errors,
                int(result.truncated),
                json.dumps(
                    [
                        {
                            "operation": warning.operation,
                            "category": warning.category,
                            "count": warning.count,
                        }
                        for warning in result.warnings
                    ],
                    ensure_ascii=False,
                ),
            ),
        )
        try:
            check()
            self.conn.executescript(INDEXES)
            check()
        except sqlite3.IntegrityError as exc:
            raise IndexBuildError("sqlite_integrity", str(exc)) from exc
        check()
        self.conn.execute("INSERT INTO nodes_fts(nodes_fts) VALUES ('optimize')")
        check()
        meta = [
            ("schema_version", str(SCHEMA_VERSION)),
            ("complete", "1"),
            ("node_count", str(processed)),
            (
                "roots_json",
                json.dumps(
                    [root.path for root in result.roots],
                    ensure_ascii=False,
                ),
            ),
            ("created_at", str(time.time())),
        ]
        self.conn.executemany(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", meta
        )
        self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        check()
        self.conn.commit()
        check()
        if cancel is None or not cancel.is_set():
            try:
                self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except sqlite3.Error as exc:
                logger.warning("checkpoint do índice não concluído: %s", exc)
        check()
        case_groups, case_paths, hashes = _case_diagnostics(self.conn)
        diagnostics = (
            self.index._try_write_diagnostics(self.conn)
            if case_groups
            else None
        )
        check()
        self.index.snapshot_roots = [root.path for root in result.roots]
        self.index.stats = IndexStats(
            rows=processed,
            elapsed_ms=(time.monotonic() - started) * 1000.0,
            case_collision_groups=case_groups,
            case_collision_paths=case_paths,
            sample_hashes=hashes,
            diagnostics_path=str(diagnostics or ""),
        )
        self._ok = True

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.conn.close()
        finally:
            if not self._ok:
                self.index.delete()

    def abort(self) -> None:
        self.close()

    def discard(self) -> None:
        """Fecha e remove o banco mesmo que a escrita já tenha sido concluída."""
        self._ok = False
        self.close()


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
        finally:
            # Libera a árvore assim que a escrita termina, mesmo que o sinal
            # para a thread da GUI ainda esteja na fila.
            self.result = None  # type: ignore[assignment]
        return self.index
