from __future__ import annotations

from pathlib import Path

from app.services.index_store import SearchIndex
from app.services.model import Node, ScanResult


def _result() -> ScanResult:
    root = Node(path="C:/raiz", name="raiz", is_dir=True, dirs=1)
    root.children = [
        Node(path="C:/raiz/agulha.txt", name="agulha.txt", is_dir=False, size=10, files=1),
        Node(path="C:/raiz/pasta", name="pasta", is_dir=True, dirs=1, size=20),
        Node(path="C:/raiz/pasta/agulha_grande.bin", name="agulha_grande.bin", is_dir=False, size=20, files=1),
    ]
    return ScanResult(
        roots=[root],
        total_size=50,
        total_files=2,
        total_dirs=2,
    )


def test_search_index_writes_and_queries(tmp_path: Path) -> None:
    index = SearchIndex.create(tmp_path / "index")
    try:
        index.write(_result())

        all_hits = index.search("agulha")
        files = index.search("agulha", "files")
        folders = index.search("agulha", "folders")

        assert all_hits.matches == 2
        assert len(all_hits.paths) == 2
        assert files.matches == 2
        assert folders.matches == 0
    finally:
        index.delete()


def test_search_index_reopens_for_another_connection(tmp_path: Path) -> None:
    index = SearchIndex.create(tmp_path / "index")
    try:
        index.write(_result())
        reopened = SearchIndex(index.path)
        assert reopened.search("pasta").matches == 1
    finally:
        index.delete()
