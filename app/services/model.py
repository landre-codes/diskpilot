"""Modelo de dados da análise de disco."""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Iterator


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

    @property
    def safe_savings(self) -> int:
        return sum(s.savings for s in self.suggestions if s.confidence == "safe")

    @property
    def review_savings(self) -> int:
        return sum(s.savings for s in self.suggestions if s.confidence != "safe")

    def largest_paths(self, limit: int | None = None) -> list[Node]:
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
        if current.children:
            stack.extend(reversed(current.children))


def all_nodes(result: ScanResult) -> Iterator[Node]:
    for root in result.roots:
        yield from walk_nodes(root)


def top_items(
    result: ScanResult, limit: int = 100
) -> tuple[list[Node], list[Node]]:
    """Os maiores diretórios e arquivos, em ordem decrescente de tamanho.

    Percorre a árvore uma vez por categoria; ``heapq.nlargest`` mantém apenas
    os ``limit`` maiores, sem ordenar todos os nós.
    """
    nodes = all_nodes(result)
    dirs = heapq.nlargest(
        limit, (node for node in nodes if node.is_dir), key=lambda n: (n.size, n.path)
    )
    nodes = all_nodes(result)
    files = heapq.nlargest(
        limit, (node for node in nodes if not node.is_dir), key=lambda n: (n.size, n.path)
    )
    return dirs, files
