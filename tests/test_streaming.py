from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from app.config import AppConfig
from app.features.analyzer.tree import NODE_ROLE, FileTree, _IndexFilterTask
from app.services.index_store import SearchIndex
from app.services.model import Node, ScanResult
from app.services.scanner import ScanCancelled, stream_scan_paths
from app.services.suggestions import build_suggestions
from appshell.theme import init_theme


def _tree(tmp_path: Path) -> Path:
    root = tmp_path / "dados"
    (root / "projetos" / "cache").mkdir(parents=True)
    (root / "projetos" / "cache" / "a.bin").write_bytes(b"a" * 10)
    (root / "projetos" / "cache" / "b.bin").write_bytes(b"b" * 20)
    (root / "fotos").mkdir()
    (root / "fotos" / "grande.jpg").write_bytes(b"x" * 30)
    return root


def _index(tmp_path: Path) -> SearchIndex:
    return SearchIndex.create(tmp_path / "indice")


def test_stream_scan_builds_lazy_result_and_children(
    tmp_path: Path,
) -> None:
    root = _tree(tmp_path)
    index = _index(tmp_path)
    try:
        result = stream_scan_paths([str(root)], index, threading.Event())

        assert result.lazy is True
        assert result.index is index
        assert result.total_files == 3
        assert result.total_dirs == 4
        assert result.roots[0].children_loaded is False
        assert result.roots[0].children_total == 2

        children = index.children_for_node(result.roots[0], "name_asc")
        assert [child.name for child in children] == ["fotos", "projetos"]
        assert all(child.children_loaded is False for child in children)

        restored = index.load_result(lazy=True)
        assert restored is not None
        assert restored.lazy is True
        assert restored.total_files == 3
        assert restored.roots[0].children_loaded is False
    finally:
        index.delete()


def test_stream_scan_applies_entry_budget_and_keeps_index_valid(
    tmp_path: Path,
) -> None:
    root = _tree(tmp_path)
    index = _index(tmp_path)
    try:
        result = stream_scan_paths(
            [str(root)], index, threading.Event(), max_entries=3
        )

        assert result.truncated is True
        assert result.total_files + result.total_dirs <= 3
        restored = index.load_result(lazy=True)
        assert restored is not None
        assert restored.truncated is True
    finally:
        index.delete()


def test_stream_scan_cancel_removes_partial_index(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    index = _index(tmp_path)
    cancel = threading.Event()
    cancel.set()
    try:
        with pytest.raises(ScanCancelled):
            stream_scan_paths([str(root)], index, cancel)

        assert not index.path.exists()
        assert not Path(str(index.path) + "-wal").exists()
    finally:
        index.delete()


def test_merge_indexes_consolidates_lazy_roots(tmp_path: Path) -> None:
    first = tmp_path / "primeira"
    second = tmp_path / "segunda"
    first.mkdir()
    second.mkdir()
    (first / "a.bin").write_bytes(b"x" * 10)
    (second / "b.bin").write_bytes(b"x" * 20)
    base = _index(tmp_path)
    extra = _index(tmp_path)
    merged = SearchIndex.create(tmp_path / "indice")
    try:
        stream_scan_paths([str(first)], base, threading.Event())
        stream_scan_paths([str(second)], extra, threading.Event())

        SearchIndex.merge_indexes([base, extra], merged, threading.Event())
        result = merged.load_result(lazy=True)

        assert result is not None
        assert result.lazy is True
        assert [root.name for root in result.roots] == ["primeira", "segunda"]
        assert result.total_files == 2
        assert result.total_size == 30
        assert merged.stats.rows == 4
        assert merged.search("a.bin").matches == 1
        assert merged.search("b.bin").matches == 1
    finally:
        base.delete()
        extra.delete()
        merged.delete()


def test_lazy_tree_expands_children_from_index(
    qapp, qtbot, tmp_path: Path
) -> None:
    init_theme(qapp, AppConfig(tmp_path / "config"))
    root = _tree(tmp_path)
    index = _index(tmp_path)
    try:
        result = stream_scan_paths([str(root)], index, threading.Event())
        tree = FileTree()
        qtbot.addWidget(tree)
        tree.show()
        tree.set_result(result)
        tree.set_search_index(index)
        item = tree.topLevelItem(0)
        assert item is not None

        item.setExpanded(True)
        qtbot.waitUntil(lambda: item.childCount() >= 2, timeout=3000)

        names = {
            item.child(i).data(0, NODE_ROLE).name
            for i in range(item.childCount())
            if item.child(i).data(0, NODE_ROLE) is not None
        }
        assert {"fotos", "projetos"}.issubset(names)
        tree.close()
    finally:
        index.delete()


def test_lazy_index_filter_builds_partial_forest(
    qapp, qtbot, tmp_path: Path
) -> None:
    init_theme(qapp, AppConfig(tmp_path / "config"))
    root = _tree(tmp_path)
    index = _index(tmp_path)
    try:
        result = stream_scan_paths([str(root)], index, threading.Event())
        task = _IndexFilterTask(
            result,
            index,
            "a.bin",
            "all",
            "name_asc",
            1,
        )

        filtered = task.execute()

        assert filtered.matches == 1
        assert filtered.roots is not None
        assert filtered.roots
        assert filtered.limited is False
    finally:
        index.delete()


def test_indexed_suggestions_match_memory_suggestions(
    tmp_path: Path,
) -> None:
    base = tmp_path / "dados"
    base.mkdir()
    root = Node(
        path=str(base), name="dados", is_dir=True, dirs=1, mtime=time.time()
    )
    cache = Node(
        path=str(base / "node_modules"),
        name="node_modules",
        is_dir=True,
        dirs=1,
        size=100 * 1024 * 1024,
        files=10,
    )
    build = Node(
        path=str(base / "build"),
        name="build",
        is_dir=True,
        dirs=1,
        size=200 * 1024 * 1024,
        files=5,
    )
    first = Node(
        path=str(base / "a.dat"),
        name="a.dat",
        is_dir=False,
        size=20 * 1024 * 1024,
        files=1,
        mtime=time.time(),
    )
    second_dir = Node(
        path=str(base / "sub"), name="sub", is_dir=True, dirs=1, files=1,
        size=20 * 1024 * 1024,
    )
    second = Node(
        path=str(base / "sub" / "a.dat"),
        name="a.dat",
        is_dir=False,
        size=20 * 1024 * 1024,
        files=1,
        mtime=time.time(),
    )
    old = Node(
        path=str(base / "old.iso"),
        name="old.iso",
        is_dir=False,
        size=300 * 1024 * 1024,
        files=1,
        mtime=0.0,
    )
    archive = Node(
        path=str(base / "big.zip"),
        name="big.zip",
        is_dir=False,
        size=2 * 1024**3,
        files=1,
        mtime=time.time(),
    )
    temp = Node(
        path=str(base / "x.tmp"),
        name="x.tmp",
        is_dir=False,
        size=30 * 1024 * 1024,
        files=1,
        mtime=time.time(),
    )
    second_dir.children = [second]
    root.children = [cache, build, first, second_dir, old, archive, temp]
    root.size = sum(child.size for child in root.children)
    result = ScanResult(
        roots=[root],
        total_size=root.size,
        total_files=5,
        total_dirs=4,
    )
    memory = build_suggestions(result)
    index = _index(tmp_path)
    try:
        index.write(result)
        lazy = index.load_result(lazy=True)
        assert lazy is not None
        indexed = build_suggestions(lazy)

        assert [(item.key, item.savings, item.count) for item in indexed] == [
            (item.key, item.savings, item.count) for item in memory
        ]
        assert [item.key for item in indexed] == [
            "caches",
            "archives",
            "stale",
            "build",
            "temp",
            "duplicates",
        ]
    finally:
        index.delete()


def test_stream_scan_accepts_failed_root(tmp_path: Path) -> None:
    missing = tmp_path / "nao_existe"
    index = _index(tmp_path)
    try:
        result = stream_scan_paths([str(missing)], index, threading.Event())

        assert result.total_files == 0
        assert result.total_dirs == 0
        assert len(result.roots) == 1
        assert result.roots[0].error
        restored = index.load_result(lazy=True)
        assert restored is not None
        assert restored.roots[0].error
    finally:
        index.delete()


def test_state_scan_uses_lazy_index_and_summary(
    qapp, qtbot, tmp_path: Path
) -> None:
    from app.services.state import AppState

    config = AppConfig(tmp_path / "config")
    state = AppState(config)
    root = _tree(tmp_path)
    results = []
    ready = []
    state.scanFinished.connect(results.append)
    state.searchIndexReady.connect(ready.append)

    state.add_roots([str(root)], autoscan=True)
    qtbot.waitUntil(lambda: bool(results) and bool(ready), timeout=5000)

    assert state.last_result is not None
    assert state.last_result.lazy is True
    assert state.last_result.index is not None
    assert state.last_result.roots[0].children_loaded is False
    assert state.search_index is not None
    assert state.summary["total_files"] == 3
    assert state.summary["top_dirs"]
    state.shutdown()


def test_merge_failure_removes_target_and_keeps_sources(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repetida"
    root.mkdir()
    child = Node(
        path=str(root / "a.bin"),
        name="a.bin",
        is_dir=False,
        size=1,
        files=1,
    )
    root_node = Node(
        path=str(root),
        name=root.name,
        is_dir=True,
        size=1,
        files=1,
        dirs=1,
    )
    root_node.children = [child]
    repeated = ScanResult(
        roots=[root_node],
        total_size=1,
        total_files=1,
        total_dirs=1,
    )
    first = _index(tmp_path)
    second = _index(tmp_path)
    target = SearchIndex.create(tmp_path / "indice")
    try:
        first.write(repeated)
        second.write(repeated)
        with pytest.raises(Exception):
            SearchIndex.merge_indexes([first, second], target, threading.Event())
        assert not target.path.exists()
        assert first.path.exists()
        assert second.path.exists()
    finally:
        first.delete()
        second.delete()
        target.delete()
