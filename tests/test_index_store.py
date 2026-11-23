from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

import pytest

import app.services.index_store as index_store
from app.services.index_store import IndexBuildError, SearchIndex
from app.services.model import Node, ScanResult, ScanWarning
from appshell.tasks import TaskCancelled
from appshell.utils import normalize_path


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


def test_search_index_treats_like_wildcards_literally(tmp_path: Path) -> None:
    result = _flat_result(
        tmp_path,
        ["a_b.txt", "axb.txt", "100%.txt", "100x.txt", "comum.txt"],
    )
    index = SearchIndex.create(tmp_path / "index")
    try:
        index.write(result)

        assert {Path(path).name for path in index.search("_", "files").paths} == {
            "a_b.txt"
        }
        assert {Path(path).name for path in index.search("%", "files").paths} == {
            "100%.txt"
        }
        assert index.search("z", "files").matches == 0
    finally:
        index.delete()


def test_search_index_cancels_before_query(tmp_path: Path) -> None:
    index = SearchIndex.create(tmp_path / "index")
    cancel = threading.Event()
    try:
        index.write(_result())
        cancel.set()
        with pytest.raises(TaskCancelled):
            index.search("agulha", cancel=cancel)
    finally:
        index.delete()


def test_search_index_load_result_roundtrip(tmp_path: Path) -> None:
    result = _result()
    result.elapsed = 4.2
    result.started_at = 1234.0
    result.warnings = [ScanWarning("list_dir", "permission_denied", 3)]
    index = SearchIndex.create(tmp_path / "index")
    try:
        index.write(result)
        loaded = index.load_result()

        assert loaded is not None
        assert loaded.total_size == 50
        assert loaded.total_files == 2
        assert loaded.total_dirs == 2
        assert loaded.elapsed == pytest.approx(4.2)
        assert loaded.started_at == pytest.approx(1234.0)
        assert [(warning.operation, warning.category, warning.count) for warning in loaded.warnings] == [
            ("list_dir", "permission_denied", 3)
        ]
        assert [root.name for root in loaded.roots] == ["raiz"]
        assert {child.name for child in loaded.roots[0].children} == {
            "agulha.txt",
            "pasta",
            "agulha_grande.bin",
        }
    finally:
        index.delete()


def test_search_index_summary_roundtrip(tmp_path: Path) -> None:
    result = _result()
    index = SearchIndex.create(tmp_path / "index")
    try:
        index.write(result)
        assert index.load_summary() is None

        summary = {
            "started_at": 1234.0,
            "suggestions": [{"key": "caches", "paths": ["C:/cache"]}],
        }
        assert index.store_summary(summary) is True
        assert index.load_summary() == summary

        index.delete()
        assert index.load_summary() is None
    finally:
        index.delete()


def test_search_index_ignores_invalid_summary(tmp_path: Path) -> None:
    result = _result()
    index = SearchIndex.create(tmp_path / "index")
    try:
        index.write(result)
        conn = sqlite3.connect(index.path)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) "
                "VALUES ('summary_json', ?)",
                ("{invalido",),
            )
            conn.commit()
        finally:
            conn.close()

        assert index.load_summary() is None
    finally:
        index.delete()


def _flat_result(root_path: Path, names: list[str]) -> ScanResult:
    root = Node(path=str(root_path), name=root_path.name, is_dir=True, dirs=1)
    root.children = [
        Node(
            path=str(root_path / name),
            name=name,
            is_dir=False,
            size=1,
            files=1,
        )
        for name in names
    ]
    return ScanResult(
        roots=[root],
        total_size=len(names),
        total_files=len(names),
        total_dirs=1,
    )




class _CancelAfter:
    def __init__(self, calls: int) -> None:
        self.calls = 0
        self.limit = calls

    def is_set(self) -> bool:
        self.calls += 1
        return self.calls >= self.limit


def test_search_index_cancels_during_query(tmp_path: Path) -> None:
    names = [f"arquivo_{number}.txt" for number in range(20_000)]
    index = SearchIndex.create(tmp_path / "index")
    try:
        index.write(_flat_result(tmp_path, names))
        with pytest.raises(TaskCancelled):
            index.search("a", "files", cancel=_CancelAfter(3))
    finally:
        index.delete()


def test_index_accepts_case_variants_that_share_path_key(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        index_store,
        "path_key",
        lambda path: normalize_path(path).casefold(),
    )
    result = _flat_result(tmp_path, ["Relatorio.txt", "relatorio.txt"])
    index = SearchIndex.create(tmp_path / "index")
    try:
        index.write(result)

        hits = index.search("relatorio")
        assert hits.matches == 2
        assert len({normalize_path(path) for path in hits.paths}) == 2
        assert index.stats.rows == 3
        assert index.stats.case_collision_groups == 1
        assert index.stats.case_collision_paths == 2
        assert len(index.stats.sample_hashes) == 2
    finally:
        index.delete()


def test_index_rejects_exact_duplicate_paths_without_leaking_paths(
    tmp_path: Path,
) -> None:
    duplicate = str(tmp_path / "duplicado.txt")
    root = Node(path=str(tmp_path), name=tmp_path.name, is_dir=True, dirs=1)
    root.children = [
        Node(path=duplicate, name="duplicado.txt", is_dir=False, size=1, files=1),
        Node(path=duplicate, name="duplicado.txt", is_dir=False, size=1, files=1),
    ]
    result = ScanResult(
        roots=[root],
        total_size=2,
        total_files=2,
        total_dirs=1,
    )
    index = SearchIndex.create(tmp_path / "index")
    try:
        with pytest.raises(IndexBuildError) as caught:
            index.write(result)

        assert caught.value.code == "duplicate_path"
        assert caught.value.details["groups"] == 1
        assert caught.value.details["rows"] == 2
        assert len(caught.value.details["sample_hashes"]) == 1
        assert duplicate not in str(caught.value)
        assert not index.path.exists()
        assert not Path(str(index.path) + "-wal").exists()
        assert not Path(str(index.path) + "-shm").exists()
    finally:
        index.delete()


def test_index_handles_multiple_insert_batches(tmp_path: Path) -> None:
    names = [f"arquivo_{number}.bin" for number in range(5100)]
    result = _flat_result(tmp_path, names)
    index = SearchIndex.create(tmp_path / "index")
    try:
        index.write(result)

        assert index.stats.rows == 5101
        assert index.path.exists()
        assert index.search("arquivo_5099").matches == 1
    finally:
        index.delete()


def test_index_cancellation_removes_partial_database(tmp_path: Path) -> None:
    cancel = threading.Event()
    cancel.set()
    index = SearchIndex.create(tmp_path / "index")
    try:
        with pytest.raises(TaskCancelled):
            index.write(_flat_result(tmp_path, ["arquivo.bin"]), cancel=cancel)

        assert not index.path.exists()
        assert not Path(str(index.path) + "-wal").exists()
        assert not Path(str(index.path) + "-shm").exists()
    finally:
        index.delete()


def test_index_cancellation_after_first_batch_removes_database(
    tmp_path: Path,
) -> None:
    names = [f"arquivo_{number}.bin" for number in range(5100)]
    cancel = threading.Event()
    index = SearchIndex.create(tmp_path / "index")

    def stop_after_batch(done: int, total: int) -> None:
        if done >= 5000:
            cancel.set()

    try:
        with pytest.raises(TaskCancelled):
            index.write(
                _flat_result(tmp_path, names),
                cancel=cancel,
                progress=stop_after_batch,
            )

        assert not index.path.exists()
    finally:
        index.delete()


def test_merge_indexes_accepts_legacy_source_without_path_exact(
    tmp_path: Path,
) -> None:
    legacy_path = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(legacy_path)
    conn.executescript(
        """
        CREATE TABLE scans (
            id INTEGER PRIMARY KEY,
            created_at REAL NOT NULL,
            elapsed REAL NOT NULL DEFAULT 0,
            roots_json TEXT NOT NULL,
            total_size INTEGER NOT NULL,
            total_files INTEGER NOT NULL,
            total_dirs INTEGER NOT NULL,
            errors INTEGER NOT NULL,
            truncated INTEGER NOT NULL
        );
        CREATE TABLE nodes (
            id INTEGER PRIMARY KEY,
            scan_id INTEGER NOT NULL,
            parent_id INTEGER,
            root_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            name_fold TEXT NOT NULL,
            path TEXT NOT NULL,
            path_key TEXT NOT NULL,
            is_dir INTEGER NOT NULL,
            size INTEGER NOT NULL,
            mtime REAL NOT NULL,
            files INTEGER NOT NULL,
            dirs INTEGER NOT NULL,
            depth INTEGER NOT NULL,
            error TEXT NOT NULL
        );
        """
    )
    conn.execute(
        "INSERT INTO scans VALUES (1, 0, 0, '[\"C:/legado\"]', 1, 1, 1, 0, 0)"
    )
    conn.execute(
        "INSERT INTO nodes VALUES "
        "(1,1,NULL,1,'legado','legado','C:/legado','c:/legado',1,1,0,1,1,0,'')"
    )
    conn.execute(
        "INSERT INTO nodes VALUES "
        "(2,1,1,1,'a.bin','a.bin','C:/legado/a.bin','c:/legado/a.bin',0,1,0,1,0,1,'')"
    )
    conn.commit()
    conn.close()

    target = SearchIndex.create(tmp_path / "merged")
    fresh = SearchIndex.create(tmp_path / "new")
    fresh.write(_result())
    try:
        SearchIndex.merge_indexes(
            [SearchIndex(legacy_path), fresh],
            target,
        )
        result = target.load_result(lazy=True)
        assert result is not None
        assert {root.path for root in result.roots} == {"C:/legado", "C:/raiz"}
    finally:
        target.delete()
        fresh.delete()


def test_index_diagnostics_are_opt_in(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        index_store,
        "path_key",
        lambda path: normalize_path(path).casefold(),
    )
    monkeypatch.delenv("DISKPILOT_INDEX_DIAGNOSTICS", raising=False)
    result = _flat_result(tmp_path, ["Relatorio.txt", "relatorio.txt"])
    base = tmp_path / "index"
    index = SearchIndex.create(base)
    index2 = None
    try:
        index.write(result)
        assert not list(base.glob("*.diagnostics.json"))

        monkeypatch.setenv("DISKPILOT_INDEX_DIAGNOSTICS", "1")
        index2 = SearchIndex.create(base)
        index2.write(result)
        files = list(base.glob("*.diagnostics.json"))
        assert len(files) == 1
        payload = json.loads(files[0].read_text(encoding="utf-8"))
        paths = {
            variant["path"]
            for group in payload["case_groups"]
            for variant in group["variants"]
        }
        assert any(path.endswith("Relatorio.txt") for path in paths)
        assert any(path.endswith("relatorio.txt") for path in paths)
        assert index2.stats.diagnostics_path == str(files[0])
    finally:
        index.delete()
        if index2 is not None:
            index2.delete()


def test_duplicate_diagnostics_are_opt_in(tmp_path: Path, monkeypatch) -> None:
    duplicate = str(tmp_path / "duplicado.txt")
    root = Node(path=str(tmp_path), name=tmp_path.name, is_dir=True, dirs=1)
    root.children = [
        Node(path=duplicate, name="duplicado.txt", is_dir=False, size=1, files=1),
        Node(path=duplicate, name="duplicado.txt", is_dir=False, size=1, files=1),
    ]
    result = ScanResult(
        roots=[root],
        total_size=2,
        total_files=2,
        total_dirs=1,
    )
    base = tmp_path / "index"
    index = SearchIndex.create(base)
    try:
        monkeypatch.delenv("DISKPILOT_INDEX_DIAGNOSTICS", raising=False)
        with pytest.raises(IndexBuildError):
            index.write(result)
        assert not list(base.glob("*.diagnostics.json"))

        monkeypatch.setenv("DISKPILOT_INDEX_DIAGNOSTICS", "1")
        index2 = SearchIndex.create(base)
        with pytest.raises(IndexBuildError) as caught:
            index2.write(result)
        diagnostics = Path(str(caught.value.details["diagnostics"]))
        payload = json.loads(diagnostics.read_text(encoding="utf-8"))
        group = payload["duplicate_groups"][0]
        assert group["path_exact"] == normalize_path(duplicate)
        assert group["nodes"][0]["path"] == duplicate
        assert not index2.path.exists()
        diagnostics.unlink()
    finally:
        index.delete()


def test_create_does_not_prune_existing_indexes(tmp_path: Path) -> None:
    base = tmp_path / "index"
    base.mkdir()
    existing = []
    for number in range(3):
        path = base / f"search-{number:032x}.sqlite"
        path.write_bytes(b"x")
        existing.append(path)

    created = SearchIndex.create(base)

    assert all(path.exists() for path in existing)
    assert created.path.parent == base
    assert created.path not in existing


def test_prune_protects_active_and_previous_snapshots(tmp_path: Path) -> None:
    import os
    import time

    base = tmp_path / "index"
    base.mkdir()
    names = [
        f"search-{number:032x}.sqlite" for number in range(4)
    ]
    # O mais antigo é o ativo; o segundo mais antigo é o rollback.
    age_days = [4, 3, 2, 1]
    files = []
    now = time.time()
    for name, days in zip(names, age_days):
        path = base / name
        path.write_bytes(b"x")
        stamp = now - days * 24 * 60 * 60
        os.utime(path, (stamp, stamp))
        files.append(path)

    removed = SearchIndex.prune(
        base,
        protected_paths=[files[0], files[1]],
        keep=1,
        min_age_seconds=0,
    )

    assert removed == 1
    assert files[0].exists()
    assert files[1].exists()
    assert not files[2].exists()
    assert files[3].exists()


def test_prune_ignores_unmanaged_files(tmp_path: Path) -> None:
    base = tmp_path / "index"
    base.mkdir()
    external = base / "search-bad.sqlite"
    external.write_bytes(b"x")
    other = base / "notes.sqlite"
    other.write_bytes(b"x")

    removed = SearchIndex.prune(base, min_age_seconds=0, keep=0)

    assert removed == 0
    assert external.exists()
    assert other.exists()


def test_delete_refuses_path_outside_managed_directory(tmp_path: Path) -> None:
    base = tmp_path / "index"
    base.mkdir()
    external = tmp_path / f"search-{'a' * 32}.sqlite"
    external.write_bytes(b"x")

    removed = SearchIndex(external).delete(managed_dir=base)

    assert removed is False
    assert external.exists()


def _update_index(path: Path, statement: str) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(statement)
        conn.commit()
    finally:
        conn.close()


def test_load_result_rejects_orphan_parent(tmp_path: Path) -> None:
    index = SearchIndex.create(tmp_path / "index")
    try:
        index.write(_result())
        _update_index(
            index.path,
            "UPDATE nodes SET parent_id = 9999 "
            "WHERE id = (SELECT id FROM nodes WHERE parent_id IS NOT NULL LIMIT 1)",
        )

        assert index.load_result() is None
    finally:
        index.delete()


def test_load_result_rejects_cycles(tmp_path: Path) -> None:
    result = _result()
    index = SearchIndex.create(tmp_path / "index")
    try:
        index.write(result)
        conn = sqlite3.connect(index.path)
        try:
            root_id = conn.execute(
                "SELECT id FROM nodes WHERE parent_id IS NULL"
            ).fetchone()[0]
            child_id = conn.execute(
                "SELECT id FROM nodes WHERE parent_id = ? LIMIT 1",
                (root_id,),
            ).fetchone()[0]
            conn.execute(
                "UPDATE nodes SET parent_id = ? WHERE id = ?",
                (child_id, root_id),
            )
            conn.execute(
                "UPDATE nodes SET parent_id = ? WHERE id = ?",
                (root_id, child_id),
            )
            conn.commit()
        finally:
            conn.close()

        assert index.load_result() is None
        assert index.load_result(lazy=True) is None
    finally:
        index.delete()


def test_load_result_lazy_rejects_self_parent(tmp_path: Path) -> None:
    index = SearchIndex.create(tmp_path / "index")
    try:
        index.write(_result())
        _update_index(
            index.path,
            "UPDATE nodes SET parent_id = id "
            "WHERE id = (SELECT id FROM nodes WHERE parent_id IS NOT NULL LIMIT 1)",
        )

        assert index.load_result(lazy=True) is None
    finally:
        index.delete()


def test_load_result_rejects_inconsistent_totals(tmp_path: Path) -> None:
    index = SearchIndex.create(tmp_path / "index")
    try:
        index.write(_result())
        _update_index(
            index.path,
            "UPDATE scans SET total_files = total_files + 1 WHERE id = 1",
        )

        assert index.load_result() is None
    finally:
        index.delete()


def test_load_result_rejects_incomplete_snapshot(tmp_path: Path) -> None:
    index = SearchIndex.create(tmp_path / "index")
    try:
        index.write(_result())
        _update_index(
            index.path,
            "UPDATE meta SET value = '0' WHERE key = 'complete'",
        )

        assert index.load_result() is None
    finally:
        index.delete()


def test_load_result_cancels_before_reading(tmp_path: Path) -> None:
    index = SearchIndex.create(tmp_path / "index")
    cancel = threading.Event()
    try:
        index.write(_result())
        cancel.set()
        with pytest.raises(TaskCancelled):
            index.load_result(cancel=cancel)
    finally:
        index.delete()


def test_load_result_cancels_during_batches(tmp_path: Path) -> None:
    names = [f"arquivo_{number}.bin" for number in range(6000)]
    index = SearchIndex.create(tmp_path / "index")
    try:
        index.write(_flat_result(tmp_path, names))
        with pytest.raises(TaskCancelled):
            index.load_result(cancel=_CancelAfter(5))
    finally:
        index.delete()


def test_load_result_accepts_legacy_snapshot_without_meta(
    tmp_path: Path,
) -> None:
    index = SearchIndex.create(tmp_path / "index")
    try:
        index.write(_result())
        _update_index(index.path, "DROP TABLE meta")

        loaded = index.load_result()

        assert loaded is not None
        assert loaded.total_files == 2
        assert index.snapshot_roots == ["C:/raiz"]
    finally:
        index.delete()


def test_load_result_accepts_failed_root_without_entries(
    tmp_path: Path,
) -> None:
    root = Node(
        path="C:/inacessivel",
        name="inacessivel",
        is_dir=True,
        dirs=0,
        error="permissao negada",
    )
    result = ScanResult(roots=[root], total_files=0, total_dirs=0, errors=1)
    index = SearchIndex.create(tmp_path / "index")
    try:
        index.write(result)
        loaded = index.load_result()

        assert loaded is not None
        assert loaded.total_files == 0
        assert loaded.total_dirs == 0
        assert [node.name for node in loaded.roots] == ["inacessivel"]
        assert loaded.roots[0].error == "permissao negada"
    finally:
        index.delete()


def test_prune_removes_orphan_wal_without_database(tmp_path: Path) -> None:
    base = tmp_path / "index"
    base.mkdir()
    orphan = base / f"search-{'d' * 32}.sqlite-wal"
    orphan.write_bytes(b"x")

    removed = SearchIndex.prune(base, min_age_seconds=0, keep=0)

    assert removed == 1
    assert not orphan.exists()
