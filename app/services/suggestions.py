"""Heurísticas para sugerir liberação de espaço com segurança."""

from __future__ import annotations

import os
import time
from collections import defaultdict
from pathlib import Path

from .model import Node, ScanResult, Suggestion, walk_nodes


SAFE_CACHE_NAMES = {
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".next",
    ".nuxt",
    ".turbo",
    ".parcel-cache",
    ".sass-cache",
    ".eslintcache",
    "coverage",
    ".nyc_output",
}

REVIEW_BUILD_NAMES = {
    "build",
    "dist",
    "target",
    ".gradle",
    ".venv",
    "venv",
    "env",
    "bin",
    "obj",
}

ARCHIVE_EXT = {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".tgz", ".iso"}
TEMP_EXT = {".tmp", ".temp", ".crdownload", ".part", ".partial", ".bak", ".old"}
STALE_AGE = 365 * 24 * 3600
STALE_MIN = 200 * 1024 * 1024
DUP_MIN = 10 * 1024 * 1024
ARCHIVE_MIN = 1024 * 1024 * 1024
TEMP_MIN = 20 * 1024 * 1024


def _collect_roots_nodes(result: ScanResult) -> list[Node]:
    return list(result.roots)


def _is_under(path: str, parents: set[str]) -> bool:
    if not parents:
        return False
    current = Path(path)
    for parent in current.parents:
        if os.path.normcase(str(parent)) in parents:
            return True
    return False


def build_suggestions(result: ScanResult, max_paths: int = 60) -> list[Suggestion]:
    """Analisa a árvore e devolve sugestões ordenadas por segurança/impacto."""
    now = time.time()
    all_files: list[Node] = []
    all_dirs: list[Node] = []
    for root in result.roots:
        for node in walk_nodes(root):
            if node.is_dir:
                all_dirs.append(node)
            else:
                all_files.append(node)

    # ---------------------------------------------------------- caches
    cache_dirs = [
        n
        for n in all_dirs
        if n.name.casefold() in SAFE_CACHE_NAMES and n.size > 0
    ]
    cache_dirs.sort(key=lambda n: len(Path(n.path).parts))
    chosen_cache: list[Node] = []
    chosen_cache_keys: set[str] = set()
    for node in cache_dirs:
        if _is_under(node.path, chosen_cache_keys):
            continue
        chosen_cache.append(node)
        chosen_cache_keys.add(os.path.normcase(node.path))

    build_dirs = [
        n
        for n in all_dirs
        if n.name.casefold() in REVIEW_BUILD_NAMES and n.size > 0
    ]
    build_dirs.sort(key=lambda n: len(Path(n.path).parts))
    chosen_build: list[Node] = []
    chosen_build_keys: set[str] = set()
    for node in build_dirs:
        if _is_under(node.path, chosen_cache_keys) or _is_under(
            node.path, chosen_build_keys
        ):
            continue
        chosen_build.append(node)
        chosen_build_keys.add(os.path.normcase(node.path))

    suggestions: list[Suggestion] = []
    if chosen_cache:
        total = sum(n.size for n in chosen_cache)
        suggestions.append(
            Suggestion(
                key="caches",
                title="Caches regeneráveis",
                description=(
                    "Pastas de dependências e caches de ferramentas que podem ser "
                    "recriadas automaticamente. São a forma mais segura de recuperar espaço."
                ),
                savings=total,
                count=len(chosen_cache),
                confidence="safe",
                icon="broom",
                note=(
                    "Feche IDEs, servidores de desenvolvimento e terminais antes de remover. "
                    "Na próxima instalação/build, as pastas serão recriadas."
                ),
                paths=[n.path for n in sorted(chosen_cache, key=lambda x: x.size, reverse=True)][
                    :max_paths
                ],
            )
        )

    if chosen_build:
        total = sum(n.size for n in chosen_build)
        suggestions.append(
            Suggestion(
                key="build",
                title="Artefatos de build e ambientes virtuais",
                description=(
                    "Pastas build, dist, target e ambientes virtuais. Liberam bastante "
                    "espaço, mas podem ser necessárias para executar ou entregar um projeto."
                ),
                savings=total,
                count=len(chosen_build),
                confidence="review",
                icon="package-variant-closed",
                note=(
                    "Confirme com a equipe se o artefato já foi publicado. Ambientes virtuais "
                    "podem ser recriados, mas exigem reinstalar dependências."
                ),
                paths=[n.path for n in sorted(chosen_build, key=lambda x: x.size, reverse=True)][
                    :max_paths
                ],
            )
        )

    claimed: set[str] = set()
    for node in chosen_cache + chosen_build:
        for child in walk_nodes(node):
            if not child.is_dir:
                claimed.add(os.path.normcase(child.path))

    # ------------------------------------------------- arquivos antigos
    stale = [
        n
        for n in all_files
        if n.size >= STALE_MIN
        and now - (n.mtime or 0) > STALE_AGE
        and os.path.normcase(n.path) not in claimed
    ]
    if stale:
        total = sum(n.size for n in stale)
        stale.sort(key=lambda n: n.size, reverse=True)
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
                paths=[n.path for n in stale[:max_paths]],
            )
        )
        for n in stale:
            claimed.add(os.path.normcase(n.path))

    # ------------------------------------------------------ duplicatas
    groups: dict[tuple[str, int], list[Node]] = defaultdict(list)
    for node in all_files:
        if node.size < DUP_MIN or os.path.normcase(node.path) in claimed:
            continue
        groups[(node.name.casefold(), node.size)].append(node)
    duplicate_groups = [items for items in groups.values() if len(items) > 1]
    duplicate_groups.sort(key=lambda items: items[0].size * (len(items) - 1), reverse=True)
    if duplicate_groups:
        savings = 0
        count = 0
        paths: list[str] = []
        for items in duplicate_groups[:40]:
            size = items[0].size
            savings += size * (len(items) - 1)
            count += len(items) - 1
            for node in items:
                if len(paths) < max_paths:
                    paths.append(node.path)
        suggestions.append(
            Suggestion(
                key="duplicates",
                title="Possíveis arquivos duplicados",
                description=(
                    "Arquivos com mesmo nome e exatamente o mesmo tamanho. Podem ser cópias "
                    "redundantes — uma verificação de conteúdo é recomendada."
                ),
                savings=savings,
                count=count,
                confidence="review",
                icon="content-duplicate",
                note=(
                    "O app compara nome e tamanho, não o conteúdo. Confirme com um utilitário "
                    "de hash antes de apagar e mantenha ao menos uma cópia."
                ),
                paths=paths,
            )
        )
        for items in duplicate_groups:
            for node in items:
                claimed.add(os.path.normcase(node.path))

    # ------------------------------------------------- arquivos compactados
    archives = [
        n
        for n in all_files
        if n.size >= ARCHIVE_MIN
        and os.path.splitext(n.name)[1].lower() in ARCHIVE_EXT
        and os.path.normcase(n.path) not in claimed
    ]
    if archives:
        archives.sort(key=lambda n: n.size, reverse=True)
        suggestions.append(
            Suggestion(
                key="archives",
                title="Arquivos compactados muito grandes",
                description=(
                    "Pacotes e imagens de disco com mais de 1 GB. Costumam ser candidatos "
                    "naturais a armazenamento externo ou à exclusão após extração."
                ),
                savings=sum(n.size for n in archives),
                count=len(archives),
                confidence="review",
                icon="zip-box-outline",
                note="Verifique se o conteúdo já foi extraído ou publicado antes de remover.",
                paths=[n.path for n in archives[:max_paths]],
            )
        )
        for n in archives:
            claimed.add(os.path.normcase(n.path))

    # ------------------------------------------------------- temporários
    temps = [
        n
        for n in all_files
        if n.size >= TEMP_MIN
        and (
            os.path.splitext(n.name)[1].lower() in TEMP_EXT
            or n.name.startswith("~$")
        )
        and os.path.normcase(n.path) not in claimed
    ]
    if temps:
        temps.sort(key=lambda n: n.size, reverse=True)
        suggestions.append(
            Suggestion(
                key="temp",
                title="Arquivos temporários e backups antigos",
                description=(
                    "Arquivos .tmp, .bak e similares que normalmente sobram de edições "
                    "interrompidas ou rotinas de backup."
                ),
                savings=sum(n.size for n in temps),
                count=len(temps),
                confidence="review",
                icon="file-clock-outline",
                note=(
                    "Backups .bak podem ser a última versão boa de um documento. "
                    "Confirme a data e o contexto antes de remover."
                ),
                paths=[n.path for n in temps[:max_paths]],
            )
        )

    suggestions.sort(
        key=lambda s: (0 if s.confidence == "safe" else 1, -s.savings)
    )
    return suggestions
