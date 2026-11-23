"""Sugestões calculadas diretamente no índice SQLite.

Este módulo é separado para evitar importação circular: ele é chamado por
``suggestions.build_suggestions`` apenas quando o resultado é lazy.
"""

from __future__ import annotations

import heapq
import logging
import os
import sqlite3
import time
from bisect import bisect_right
from collections.abc import Iterator
from pathlib import Path

from appshell.utils import normalize_path

from .model import Suggestion


logger = logging.getLogger("diskpilot.suggestions")


def build_indexed_suggestions(
    index_path: str, max_paths: int = 60
) -> list[Suggestion]:
    """Versão SQLite das heurísticas, sem carregar todos os nós em RAM."""
    from .suggestions import (
        ARCHIVE_EXT,
        ARCHIVE_MIN,
        DUP_MIN,
        REVIEW_BUILD_NAMES,
        SAFE_CACHE_NAMES,
        STALE_AGE,
        STALE_MIN,
        TEMP_EXT,
        TEMP_MIN,
        _is_under,
    )

    now = time.time()
    try:
        conn = sqlite3.connect(index_path)
        columns = {
            str(row[1])
            for row in conn.execute("PRAGMA table_info(nodes)")
        }
        path_expr = "path_exact" if "path_exact" in columns else "path"
        if path_expr == "path":
            logger.info(
                "índice legado sem path_exact; sugestões usarão a coluna path"
            )
    except sqlite3.Error:
        logger.exception("falha ao abrir o índice para sugestões")
        return []

    def prefixes_for(items: list[tuple[str, int]]) -> list[str]:
        prefixes = []
        for path, _size in items:
            base = normalize_path(path)
            prefixes.append(base if base.endswith(os.sep) else base + os.sep)
        return prefixes

    def blocked(path: str, prefixes: list[str]) -> bool:
        if not prefixes:
            return False
        index = bisect_right(prefixes, path) - 1
        return index >= 0 and path.startswith(prefixes[index])

    suggestions: list[Suggestion] = []
    try:
        cache_names = sorted(SAFE_CACHE_NAMES)
        placeholders = ",".join("?" for _ in cache_names)
        rows = conn.execute(
            f"SELECT path, size FROM nodes WHERE scan_id = 1 AND is_dir = 1 "
            f"AND name_fold IN ({placeholders}) AND size > 0",
            cache_names,
        ).fetchall()
        cache_dirs = sorted(
            [(str(path), int(size)) for path, size in rows],
            key=lambda item: len(Path(item[0]).parts),
        )
        chosen_cache: list[tuple[str, int]] = []
        chosen_cache_keys: set[str] = set()
        for path, size in cache_dirs:
            if _is_under(path, chosen_cache_keys):
                continue
            chosen_cache.append((path, size))
            chosen_cache_keys.add(normalize_path(path))
        if chosen_cache:
            chosen_cache.sort(key=lambda item: item[1], reverse=True)
            suggestions.append(
                Suggestion(
                    key="caches",
                    title="Caches regeneráveis",
                    description=(
                        "Pastas de dependências e caches de ferramentas que podem ser "
                        "recriadas automaticamente. São a forma mais segura de recuperar espaço."
                    ),
                    savings=sum(size for _, size in chosen_cache),
                    count=len(chosen_cache),
                    confidence="safe",
                    icon="broom",
                    note=(
                        "Feche IDEs, servidores de desenvolvimento e terminais antes de remover. "
                        "Na próxima instalação/build, as pastas serão recriadas."
                    ),
                    paths=[path for path, _size in chosen_cache[:max_paths]],
                )
            )

        build_placeholders = ",".join("?" for _ in REVIEW_BUILD_NAMES)
        rows = conn.execute(
            f"SELECT path, size FROM nodes WHERE scan_id = 1 AND is_dir = 1 "
            f"AND name_fold IN ({build_placeholders}) AND size > 0",
            sorted(REVIEW_BUILD_NAMES),
        ).fetchall()
        build_dirs = sorted(
            [(str(path), int(size)) for path, size in rows],
            key=lambda item: len(Path(item[0]).parts),
        )
        chosen_build: list[tuple[str, int]] = []
        chosen_build_keys: set[str] = set()
        for path, size in build_dirs:
            if _is_under(path, chosen_cache_keys) or _is_under(
                path, chosen_build_keys
            ):
                continue
            chosen_build.append((path, size))
            chosen_build_keys.add(normalize_path(path))
        if chosen_build:
            chosen_build.sort(key=lambda item: item[1], reverse=True)
            suggestions.append(
                Suggestion(
                    key="build",
                    title="Artefatos de build e ambientes virtuais",
                    description=(
                        "Pastas build, dist, target e ambientes virtuais. Liberam bastante "
                        "espaço, mas podem ser necessárias para executar ou entregar um projeto."
                    ),
                    savings=sum(size for _, size in chosen_build),
                    count=len(chosen_build),
                    confidence="review",
                    icon="package-variant-closed",
                    note=(
                        "Confirme com a equipe se o artefato já foi publicado. Ambientes virtuais "
                        "podem ser recriados, mas exigem reinstalar dependências."
                    ),
                    paths=[path for path, _size in chosen_build[:max_paths]],
                )
            )

        prefixes = sorted(set(prefixes_for(chosen_cache + chosen_build)))
        conn.execute(
            "CREATE TEMP TABLE IF NOT EXISTS excluded(path TEXT PRIMARY KEY)"
        )

        def add_excluded(paths: list[str]) -> None:
            if paths:
                conn.executemany(
                    "INSERT OR IGNORE INTO excluded(path) VALUES (?)",
                    [(str(path),) for path in paths],
                )

        def fetch_batches(statement: str, params: tuple) -> Iterator[list[tuple]]:
            cursor = conn.execute(statement, params)
            while True:
                batch = cursor.fetchmany(2000)
                if not batch:
                    return
                yield batch

        # Stale: stream ordered by size; retém apenas os exemplos exibidos.
        stale_count = 0
        stale_total = 0
        stale_paths: list[str] = []
        for batch in fetch_batches(
            f"SELECT {path_expr}, path, size FROM nodes WHERE scan_id = 1 "
            "AND is_dir = 0 AND size >= ? AND mtime < ? ORDER BY size DESC",
            (STALE_MIN, now - STALE_AGE),
        ):
            stale_excluded: list[str] = []
            for path_exact, path, size in batch:
                exact = normalize_path(str(path_exact))
                if blocked(exact, prefixes):
                    continue
                stale_count += 1
                stale_total += int(size)
                if len(stale_paths) < max_paths:
                    stale_paths.append(str(path))
                stale_excluded.append(str(path_exact))
            add_excluded(stale_excluded)
        if stale_count:
            suggestions.append(
                Suggestion(
                    key="stale",
                    title="Arquivos grandes sem alteração há mais de 1 ano",
                    description=(
                        "Arquivos pesados que não são modificados há muito tempo. Bons candidatos "
                        "para arquivar em armazenamento externo ou revisar com o responsável."
                    ),
                    savings=stale_total,
                    count=stale_count,
                    confidence="review",
                    icon="clock-outline",
                    note=(
                        "Abra os arquivos antes de mover. Arquivos de clientes, backups e mídias "
                        "podem ter valor histórico mesmo sem alterações recentes."
                    ),
                    paths=stale_paths,
                )
            )

        # Duplicatas: stream ordenado por (nome, tamanho); guarda no heap
        # apenas os 40 grupos de maior economia.
        duplicate_top: list[tuple] = []
        duplicate_serial = 0
        current_key: tuple[str, int] | None = None
        current_count = 0
        current_size = 0
        current_exact: list[str] = []
        current_samples: list[str] = []

        def finish_duplicate_group() -> None:
            nonlocal duplicate_serial
            if current_key is None:
                return
            if current_count > 1:
                savings = current_size * (current_count - 1)
                duplicate_serial += 1
                heapq.heappush(
                    duplicate_top,
                    (
                        savings,
                        duplicate_serial,
                        current_size,
                        current_count,
                        list(current_samples),
                    ),
                )
                if len(duplicate_top) > 40:
                    heapq.heappop(duplicate_top)
                add_excluded(current_exact)
            current_exact.clear()
            current_samples.clear()

        for batch in fetch_batches(
            f"SELECT {path_expr}, path, name_fold, size FROM nodes "
            "WHERE scan_id = 1 AND is_dir = 0 AND size >= ? "
            f"AND {path_expr} NOT IN (SELECT path FROM excluded) "
            f"ORDER BY name_fold, size, {path_expr}",
            (DUP_MIN,),
        ):
            for path_exact, path, name_fold, size in batch:
                exact = normalize_path(str(path_exact))
                if blocked(exact, prefixes):
                    continue
                key = (str(name_fold), int(size))
                if current_key is not None and key != current_key:
                    finish_duplicate_group()
                if key != current_key:
                    current_key = key
                    current_count = 0
                    current_size = int(size)
                current_count += 1
                current_exact.append(str(path_exact))
                if len(current_samples) < max_paths:
                    current_samples.append(str(path))
        finish_duplicate_group()
        if duplicate_top:
            groups = sorted(duplicate_top, key=lambda item: item[0], reverse=True)
            savings = sum(item[0] for item in groups)
            count = sum(item[3] - 1 for item in groups)
            paths: list[str] = []
            for _savings, _serial, _size, _count, samples in groups:
                for path in samples:
                    if len(paths) < max_paths:
                        paths.append(path)
            if count:
                suggestions.append(
                    Suggestion(
                        key="duplicates",
                        title="Possíveis arquivos duplicados",
                        description=(
                            "Arquivos com mesmo nome e exatamente o mesmo tamanho. Podem ser cópias "
                            "redundantes — confirme o conteúdo antes de remover."
                        ),
                        savings=savings,
                        count=count,
                        confidence="review",
                        icon="content-duplicate",
                        note=(
                            "O app compara nome e tamanho, não o conteúdo. Abra os arquivos ou "
                            "confirme com a equipe antes de apagar e mantenha ao menos uma cópia."
                        ),
                        paths=paths,
                    )
                )

        archive_count = 0
        archive_total = 0
        archive_paths: list[str] = []
        archive_excluded: list[str] = []
        for batch in fetch_batches(
            f"SELECT {path_expr}, path, name, size FROM nodes "
            "WHERE scan_id = 1 AND is_dir = 0 AND size >= ? "
            f"AND {path_expr} NOT IN (SELECT path FROM excluded) "
            "ORDER BY size DESC",
            (ARCHIVE_MIN,),
        ):
            for path_exact, path, name, size in batch:
                if os.path.splitext(str(name))[1].lower() not in ARCHIVE_EXT:
                    continue
                exact = normalize_path(str(path_exact))
                if blocked(exact, prefixes):
                    continue
                archive_count += 1
                archive_total += int(size)
                if len(archive_paths) < max_paths:
                    archive_paths.append(str(path))
                archive_excluded.append(str(path_exact))
        if archive_count:
            suggestions.append(
                Suggestion(
                    key="archives",
                    title="Arquivos compactados muito grandes",
                    description=(
                        "Pacotes e imagens de disco com mais de 1 GB. Costumam ser candidatos "
                        "naturais a armazenamento externo ou à exclusão após extração."
                    ),
                    savings=archive_total,
                    count=archive_count,
                    confidence="review",
                    icon="zip-box-outline",
                    note="Verifique se o conteúdo já foi extraído ou publicado antes de remover.",
                    paths=archive_paths,
                )
            )
            add_excluded(archive_excluded)

        temp_count = 0
        temp_total = 0
        temp_paths: list[str] = []
        for batch in fetch_batches(
            f"SELECT {path_expr}, path, name, size FROM nodes "
            "WHERE scan_id = 1 AND is_dir = 0 AND size >= ? "
            f"AND {path_expr} NOT IN (SELECT path FROM excluded) "
            "ORDER BY size DESC",
            (TEMP_MIN,),
        ):
            for path_exact, path, name, size in batch:
                if not (
                    os.path.splitext(str(name))[1].lower() in TEMP_EXT
                    or str(name).startswith("~$")
                ):
                    continue
                exact = normalize_path(str(path_exact))
                if blocked(exact, prefixes):
                    continue
                temp_count += 1
                temp_total += int(size)
                if len(temp_paths) < max_paths:
                    temp_paths.append(str(path))
        if temp_count:
            suggestions.append(
                Suggestion(
                    key="temp",
                    title="Arquivos temporários e backups antigos",
                    description=(
                        "Arquivos .tmp, .bak e similares que normalmente sobram de edições "
                        "interrompidas ou rotinas de backup."
                    ),
                    savings=temp_total,
                    count=temp_count,
                    confidence="review",
                    icon="file-clock-outline",
                    note=(
                        "Backups .bak podem ser a última versão boa de um documento. "
                        "Confirme a data e o contexto antes de remover."
                    ),
                    paths=temp_paths,
                )
            )
    except sqlite3.Error:
        logger.exception("falha ao calcular sugestões indexadas")
        return []
    finally:
        conn.close()

    suggestions.sort(
        key=lambda s: (0 if s.confidence == "safe" else 1, -s.savings)
    )
    return suggestions
