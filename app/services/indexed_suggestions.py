"""Sugestões calculadas diretamente no índice SQLite.

Este módulo é separado para evitar importação circular: ele é chamado por
``suggestions.build_suggestions`` apenas quando o resultado é lazy.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from bisect import bisect_right
from collections import defaultdict
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

    def claim(path: str, claimed: set[str]) -> None:
        claimed.add(normalize_path(path))

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
        claimed: set[str] = set()

        # As consultas abaixo trazem somente candidatos acima do limiar;
        # a exclusão dos caches/builds é feita nos poucos milhares de
        # candidatos, não em todos os 1,4 milhão de nós.
        stale_rows = conn.execute(
            f"SELECT {path_expr}, path, size FROM nodes WHERE scan_id = 1 "
            "AND is_dir = 0 AND size >= ? AND mtime < ? ORDER BY size DESC",
            (STALE_MIN, now - STALE_AGE),
        ).fetchall()
        stale = [
            (str(path_exact), str(path), int(size))
            for path_exact, path, size in stale_rows
            if not blocked(normalize_path(str(path_exact)), prefixes)
            and normalize_path(str(path_exact)) not in claimed
        ]
        if stale:
            total = sum(size for _exact, _path, size in stale)
            suggestions.append(
                Suggestion(
                    key="stale",
                    title="Arquivos grandes sem alteração há mais de 1 ano",
                    description=(
                        "Arquivos pesados que não são modificados há muito tempo. Bons candidatos "
                        "para arquivar em armazenamento externo ou revisar com o responsável."
                    ),
                    savings=total,
                    count=len(stale),
                    confidence="review",
                    icon="clock-outline",
                    note=(
                        "Abra os arquivos antes de mover. Arquivos de clientes, backups e mídias "
                        "podem ter valor histórico mesmo sem alterações recentes."
                    ),
                    paths=[path for _exact, path, _size in stale[:max_paths]],
                )
            )
            for exact, _path, _size in stale:
                claim(exact, claimed)

        duplicate_rows = conn.execute(
            f"SELECT {path_expr}, path, name_fold, size FROM nodes "
            "WHERE scan_id = 1 AND is_dir = 0 AND size >= ?",
            (DUP_MIN,),
        ).fetchall()
        groups: dict[tuple[str, int], list[str]] = defaultdict(list)
        for path_exact, path, name_fold, size in duplicate_rows:
            if blocked(normalize_path(str(path_exact)), prefixes):
                continue
            if normalize_path(str(path_exact)) in claimed:
                continue
            groups[(str(name_fold), int(size))].append(str(path))
        duplicate_groups = [
            (size, items)
            for (_name_fold, size), items in groups.items()
            if len(items) > 1
        ]
        duplicate_groups.sort(
            key=lambda item: item[0] * (len(item[1]) - 1),
            reverse=True,
        )
        if duplicate_groups:
            savings = 0
            count = 0
            paths: list[str] = []
            for size, items in duplicate_groups[:40]:
                savings += size * (len(items) - 1)
                count += len(items) - 1
                for path in items:
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
                for _size, items in duplicate_groups[:40]:
                    for path in items:
                        claim(path, claimed)

        archive_rows = conn.execute(
            f"SELECT {path_expr}, path, name, size FROM nodes "
            "WHERE scan_id = 1 AND is_dir = 0 AND size >= ? ORDER BY size DESC",
            (ARCHIVE_MIN,),
        ).fetchall()
        archives = [
            (str(path_exact), str(path), str(name), int(size))
            for path_exact, path, name, size in archive_rows
            if os.path.splitext(str(name))[1].lower() in ARCHIVE_EXT
            and not blocked(normalize_path(str(path_exact)), prefixes)
            and normalize_path(str(path_exact)) not in claimed
        ]
        if archives:
            suggestions.append(
                Suggestion(
                    key="archives",
                    title="Arquivos compactados muito grandes",
                    description=(
                        "Pacotes e imagens de disco com mais de 1 GB. Costumam ser candidatos "
                        "naturais a armazenamento externo ou à exclusão após extração."
                    ),
                    savings=sum(size for _exact, _path, _name, size in archives),
                    count=len(archives),
                    confidence="review",
                    icon="zip-box-outline",
                    note="Verifique se o conteúdo já foi extraído ou publicado antes de remover.",
                    paths=[
                        path for _exact, path, _name, _size in archives[:max_paths]
                    ],
                )
            )
            for exact, _path, _name, _size in archives:
                claim(exact, claimed)

        temp_rows = conn.execute(
            f"SELECT {path_expr}, path, name, size FROM nodes "
            "WHERE scan_id = 1 AND is_dir = 0 AND size >= ? ORDER BY size DESC",
            (TEMP_MIN,),
        ).fetchall()
        temps = [
            (str(path_exact), str(path), str(name), int(size))
            for path_exact, path, name, size in temp_rows
            if (
                os.path.splitext(str(name))[1].lower() in TEMP_EXT
                or str(name).startswith("~$")
            )
            and not blocked(normalize_path(str(path_exact)), prefixes)
            and normalize_path(str(path_exact)) not in claimed
        ]
        if temps:
            suggestions.append(
                Suggestion(
                    key="temp",
                    title="Arquivos temporários e backups antigos",
                    description=(
                        "Arquivos .tmp, .bak e similares que normalmente sobram de edições "
                        "interrompidas ou rotinas de backup."
                    ),
                    savings=sum(size for _exact, _path, _name, size in temps),
                    count=len(temps),
                    confidence="review",
                    icon="file-clock-outline",
                    note=(
                        "Backups .bak podem ser a última versão boa de um documento. "
                        "Confirme a data e o contexto antes de remover."
                    ),
                    paths=[path for _exact, path, _name, _size in temps[:max_paths]],
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
