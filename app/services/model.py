"""Modelo de dados da análise de disco."""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass(slots=True)
class Node:
    path: str
    name: str
    is_dir: bool
    size: int = 0
    mtime: float = 0.0
    files: int = 0
    dirs: int = 0
    error: str = ""
    is_symlink: bool = False
    children: list["Node"] = field(default_factory=list, repr=False)
    node_id: int = 0
    children_loaded: bool = True
    children_total: int = 0
    children_loader: Any = field(default=None, repr=False, compare=False)

    def ensure_children(self) -> list["Node"]:
        """Carrega filhos sob demanda para resultados indexados."""
        if self.children_loaded:
            return self.children
        loader = self.children_loader
        if loader is None:
            self.children_loaded = True
            return self.children
        loaded = list(loader(self) or [])
        self.children = loaded
        if not self.children_total:
            self.children_total = len(loaded)
        self.children_loaded = True
        self.children_loader = None
        return self.children

    @property
    def entries(self) -> int:
        return self.files + self.dirs

    @property
    def extension(self) -> str:
        if self.is_dir:
            return ""
        dot = self.name.rfind(".")
        return self.name[dot + 1 :].lower() if dot > 0 else ""


@dataclass(slots=True)
class Suggestion:
    key: str
    title: str
    description: str
    savings: int
    count: int
    confidence: str
    icon: str
    note: str = ""
    paths: list[str] = field(default_factory=list, repr=False)

    @property
    def safe(self) -> bool:
        return self.confidence == "safe"


@dataclass(slots=True)
class ScanProgress:
    files: int = 0
    dirs: int = 0
    bytes_seen: int = 0
    current: str = ""
    roots_done: int = 0
    roots_total: int = 0


@dataclass(slots=True)
class ScanWarning:
    """Aviso agregado da varredura, sem caminhos completos por padrão."""

    operation: str
    category: str
    count: int = 1


@dataclass(slots=True)
class ScanResult:
    roots: list[Node] = field(default_factory=list)
    total_size: int = 0
    total_files: int = 0
    total_dirs: int = 0
    errors: int = 0
    elapsed: float = 0.0
    started_at: float = 0.0
    truncated: bool = False
    suggestions: list[Suggestion] = field(default_factory=list)
    warnings: list[ScanWarning] = field(default_factory=list)
    lazy: bool = False
    index_path: str = ""
    index: Any = field(default=None, repr=False, compare=False)

    @property
    def safe_savings(self) -> int:
        return sum(s.savings for s in self.suggestions if s.confidence == "safe")

    @property
    def review_savings(self) -> int:
        return sum(s.savings for s in self.suggestions if s.confidence != "safe")

    def largest_paths(self, limit: int | None = None) -> list[Node]:
        if self.lazy and self.index is not None:
            return self.index.top_root_items(limit)
        nodes = (child for root in self.roots for child in root.children)
        if limit is None:
            return sorted(nodes, key=lambda n: n.size, reverse=True)
        return heapq.nlargest(limit, nodes, key=lambda n: n.size)


def walk_nodes(node: Node) -> Iterator[Node]:
    """Pré-ordem iterativa para evitar estouro de recursão."""
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        children = current.ensure_children()
        if children:
            stack.extend(reversed(children))


def all_nodes(result: ScanResult) -> Iterator[Node]:
    for root in result.roots:
        yield from walk_nodes(root)


def top_items(
    result: ScanResult, limit: int = 100
) -> tuple[list[Node], list[Node]]:
    """Os maiores diretórios e arquivos, em ordem decrescente de tamanho.

    Uma única travessia mantém dois heaps com os ``limit`` maiores de cada
    categoria, sem ordenar a árvore inteira. Em resultados indexados, a
    consulta é feita no SQLite.
    """
    if limit <= 0:
        return [], []
    if result.lazy and result.index is not None:
        return result.index.top_items(limit)
    dir_heap: list[tuple[int, str, Node]] = []
    file_heap: list[tuple[int, str, Node]] = []
    for node in all_nodes(result):
        heap = dir_heap if node.is_dir else file_heap
        item = (node.size, node.path, node)
        if len(heap) < limit:
            heapq.heappush(heap, item)
        elif item > heap[0]:
            heapq.heapreplace(heap, item)
    dirs = [item[2] for item in sorted(dir_heap, reverse=True)]
    files = [item[2] for item in sorted(file_heap, reverse=True)]
    return dirs, files
