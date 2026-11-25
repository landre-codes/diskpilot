from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from app.config import AppConfig
from app.services.index_store import SearchIndex
from app.services import state as state_module
from app.services.model import Node, ScanResult, ScanWarning, Suggestion
from app.services.state import AppState, ScanTask
from appshell.utils import path_key


def test_app_state_scans_with_task_runner(qapp, qtbot, tmp_path: Path) -> None:
    config = AppConfig(tmp_path / "config")
    state = AppState(config)
    base = tmp_path / "dados"
    base.mkdir()
    for index in range(2):
        folder = base / f"dir_{index}"
        folder.mkdir()
        (folder / "arquivo.bin").write_bytes(b"x" * (index + 1) * 10)

    results = []
    busy = []
    state.scanFinished.connect(results.append)
    state.busyChanged.connect(busy.append)

    state.add_roots([str(base)], autoscan=True)
    qtbot.waitUntil(lambda: bool(results), timeout=5000)

    assert results[0].total_files == 2
    assert results[0].total_dirs == 3
    assert state.busy is False
    assert busy[0] is True
    assert busy[-1] is False
    state.shutdown()


def test_adding_root_merges_previous_result(qapp, qtbot, tmp_path: Path) -> None:
    config = AppConfig(tmp_path / "config")
    state = AppState(config)
    first = tmp_path / "primeira"
    second = tmp_path / "segunda"
    first.mkdir()
    second.mkdir()
    (first / "a.bin").write_bytes(b"x" * 10)
    (second / "b.bin").write_bytes(b"x" * 20)

    results = []
    state.scanFinished.connect(results.append)
    state.add_roots([str(first)], autoscan=True)
    qtbot.waitUntil(lambda: len(results) == 1, timeout=5000)
    first_result = state.last_result
    assert first_result is not None

    state.add_roots([str(second)], autoscan=True)
    qtbot.waitUntil(lambda: len(results) == 2, timeout=5000)

    merged = state.last_result
    assert merged is not None
    assert len(merged.roots) == 2
    assert [root.path for root in merged.roots] == [
        first_result.roots[0].path,
        str(second),
    ]
    assert merged.total_files == 2
    assert merged.total_size == 30
    state.shutdown()


def test_summary_persists_suggestions_in_index_across_restart(
    qapp, qtbot, tmp_path: Path
) -> None:
    config = AppConfig(tmp_path / "config")
    state = AppState(config)
    root = tmp_path / "dados"
    root.mkdir()
    result = _index_result(root)
    result.started_at = 1234.0
    result.suggestions = [
        Suggestion(
            key="caches",
            title="Caches regeneráveis",
            description="Pastas de cache que podem ser recriadas.",
            savings=1234,
            count=2,
            confidence="safe",
            icon="broom",
            note="Revise antes de remover.",
            paths=["C:/dados/cache-a", "C:/dados/cache-b"],
        )
    ]
    index = SearchIndex.create(config.path.parent / "index")
    result.index = index
    result.index_path = str(index.path)
    index.write(result)

    state._publish_stream_result(result)

    stored = index.load_summary()
    assert stored is not None
    assert stored["suggestions"][0]["paths"] == [
        "C:/dados/cache-a",
        "C:/dados/cache-b",
    ]
    persisted = config.get("scan.summary")
    assert "suggestions" not in persisted
    assert "top_dirs" not in persisted
    assert persisted["suggestion_count"] == 1
    state.shutdown()

    restored = AppState(config)
    try:
        qtbot.waitUntil(lambda: restored.last_result is not None, timeout=5000)
        suggestions = restored.suggestions
        assert len(suggestions) == 1
        assert suggestions[0].key == "caches"
        assert suggestions[0].savings == 1234
        assert suggestions[0].paths == ["C:/dados/cache-a", "C:/dados/cache-b"]
        assert restored.summary["suggestion_count"] == 1
    finally:
        restored.shutdown()


def test_remove_root_reuses_current_snapshot(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    config = AppConfig(tmp_path / "config")
    state = AppState(config)
    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir()
    second.mkdir()
    result = _index_result(first)
    result.roots.append(_index_result(second).roots[0])
    result.total_size = 20
    result.total_files = 2
    result.total_dirs = 2
    result.started_at = 100.0
    index = SearchIndex.create(config.path.parent / "index")
    result.index = index
    result.index_path = str(index.path)
    result.lazy = True
    index.write(result)
    state.roots = [str(first), str(second)]
    state.search_index = index
    state.last_result = result
    config.set("scan.roots", [str(first), str(second)], save=True)
    started: list[dict] = []
    monkeypatch.setattr(
        state, "start_scan", lambda **kwargs: started.append(kwargs)
    )
    finished: list[object] = []
    failed: list[str] = []
    state.rootRemovalFinished.connect(finished.append)
    state.rootRemovalFailed.connect(failed.append)

    state.remove_root(str(first))
    qtbot.waitUntil(lambda: bool(finished) or bool(failed), timeout=5000)

    assert failed == []
    assert finished
    assert started == []
    assert [root.path for root in state.last_result.roots] == [str(second)]
    assert state.last_result.total_size == 10
    loaded = index.load_result(lazy=True)
    assert loaded is not None
    assert [root.path for root in loaded.roots] == [str(second)]
    assert config.get("scan.summary")["total_size"] == 10
    assert config.get("scan.roots") == [str(second)]
    state.shutdown()


def test_remove_root_failure_restores_roots(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    config = AppConfig(tmp_path / "config")
    state = AppState(config)
    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir()
    second.mkdir()
    result = _index_result(first)
    result.roots.append(_index_result(second).roots[0])
    result.total_size = 20
    result.total_files = 2
    result.total_dirs = 2
    index = SearchIndex.create(config.path.parent / "index")
    result.index = index
    result.index_path = str(index.path)
    result.lazy = True
    index.write(result)
    state.roots = [str(first), str(second)]
    state.search_index = index
    state.last_result = result
    config.set("scan.roots", [str(first), str(second)], save=True)
    failed: list[str] = []
    state.rootRemovalFailed.connect(failed.append)
    monkeypatch.setattr(
        SearchIndex,
        "remove_root",
        lambda self, path, cancel=None, progress=None: False,
    )

    state.remove_root(str(first))
    qtbot.waitUntil(lambda: bool(failed), timeout=5000)

    assert failed
    assert state.roots == [str(first), str(second)]
    assert config.get("scan.roots") == [str(first), str(second)]
    assert state.last_result is result
    state.shutdown()


def test_cancel_timeout_releases_ui(qapp, tmp_path: Path) -> None:
    config = AppConfig(tmp_path / "config")
    state = AppState(config)
    state.is_scanning = True
    state._generation = 3
    state._task = object()
    state._cancel = threading.Event()
    state._cancel.set()
    cancelled: list[bool] = []
    state.scanCancelled.connect(lambda: cancelled.append(True))

    state._on_cancel_timeout()

    assert cancelled == [True]
    assert state.is_scanning is False
    assert state._task is None
    assert state._cancel is None
    state.shutdown()


def test_cancel_discards_late_result(qapp, tmp_path: Path) -> None:
    config = AppConfig(tmp_path / "config")
    state = AppState(config)
    root = tmp_path / "dados"
    root.mkdir()
    index = SearchIndex.create(config.path.parent / "index")
    result = _index_result(root)
    result.index = index
    result.index_path = str(index.path)
    index.write(result)
    state._generation = 4
    state._cancel = threading.Event()
    state._cancel.set()
    state.is_scanning = True
    cancelled: list[bool] = []
    state.scanCancelled.connect(lambda: cancelled.append(True))

    state._on_result(4, result)

    assert cancelled == [True]
    assert state.last_result is None
    assert state.is_scanning is False
    assert not index.path.exists()
    state.shutdown()


def test_stream_publish_records_history_once(
    qapp, qtbot, tmp_path: Path
) -> None:
    config = AppConfig(tmp_path / "config")
    state = AppState(config)
    root = tmp_path / "dados"
    root.mkdir()
    index = SearchIndex.create(config.path.parent / "index")
    result = _index_result(root)
    result.started_at = 1234.0
    result.index = index
    result.index_path = str(index.path)
    index.write(result)

    state._publish_stream_result(result)

    history = config.get("scan.history")
    assert isinstance(history, list)
    assert len(history) == 1
    assert history[0]["total_size"] == result.total_size
    assert history[0]["roots"][0]["path"] == str(root)
    state.shutdown()

    restored = AppState(config)
    try:
        qtbot.waitUntil(lambda: restored.last_result is not None, timeout=5000)
        assert len(config.get("scan.history")) == 1
    finally:
        restored.shutdown()


def test_legacy_config_summary_restores_and_is_migrated(
    qapp, qtbot, tmp_path: Path
) -> None:
    config = AppConfig(tmp_path / "config")
    root = tmp_path / "dados"
    root.mkdir()
    result = _index_result(root)
    result.started_at = 1234.0
    index = SearchIndex.create(config.path.parent / "index")
    index.write(result)
    config.set("scan.index_path", str(index.path), save=False)
    config.set("scan.indexed_roots", [str(root)], save=False)
    config.set(
        "scan.summary",
        {
            "total_size": result.total_size,
            "total_files": result.total_files,
            "total_dirs": result.total_dirs,
            "started_at": result.started_at,
            "roots": [{"path": str(root)}],
            "index_path": str(index.path),
            "index_entries": 2,
            "suggestion_count": 1,
            "suggestions": [
                {
                    "key": "caches",
                    "title": "Caches regeneráveis",
                    "description": "Pastas de cache.",
                    "savings": 99,
                    "count": 1,
                    "confidence": "safe",
                    "icon": "broom",
                    "note": "Revise.",
                    "paths": ["C:/dados/cache-legado"],
                }
            ],
        },
        save=True,
    )

    state = AppState(config)
    try:
        qtbot.waitUntil(lambda: state.last_result is not None, timeout=5000)
        suggestions = state.suggestions
        assert [suggestion.key for suggestion in suggestions] == ["caches"]
        assert suggestions[0].paths == ["C:/dados/cache-legado"]
        assert index.load_summary() is not None
        persisted = config.get("scan.summary")
        assert "suggestions" not in persisted
    finally:
        state.shutdown()


def test_merge_results_preserves_warning_categories() -> None:
    base = ScanResult(
        roots=[],
        warnings=[ScanWarning("list_dir", "permission_denied", 1)],
    )
    extra = ScanResult(
        roots=[],
        warnings=[
            ScanWarning("list_dir", "permission_denied", 2),
            ScanWarning("stat_root", "not_found", 1),
        ],
    )

    merged = AppState._merge_results(base, extra)

    assert [
        (warning.operation, warning.category, warning.count)
        for warning in merged.warnings
    ] == [
        ("list_dir", "permission_denied", 3),
        ("stat_root", "not_found", 1),
    ]


class _DeletedIndex:
    def __init__(self) -> None:
        self.deleted = False
        self.path = "stale-index"

    def delete(self, managed_dir=None) -> bool:
        self.deleted = True
        return True


def test_stale_index_callback_is_discarded(qapp, tmp_path: Path) -> None:
    state = AppState(AppConfig(tmp_path / "config"))
    stale = _DeletedIndex()
    ready = []
    state.searchIndexReady.connect(ready.append)
    state._index_generation = 2

    state._on_index_ready(1, stale)

    assert stale.deleted is True
    assert ready == []
    state.shutdown()




def test_restore_reuses_summary_suggestions(qapp, qtbot, tmp_path: Path, monkeypatch) -> None:
    config = AppConfig(tmp_path / "config")
    root = tmp_path / "dados"
    root.mkdir()
    (root / "cache.bin").write_bytes(b"x" * 10)
    index = SearchIndex.create(tmp_path / "index")
    result = _index_result(root)
    result.started_at = 123.0
    index.write(result)
    config.roots = [str(root)]
    config.set(
        "scan.summary",
        {
            "started_at": 123.0,
            "roots": [{"path": str(root)}],
            "suggestion_count": 1,
            "suggestions": [
                {
                    "key": "caches",
                    "title": "Caches regeneráveis",
                    "description": "Teste",
                    "savings": 123,
                    "count": 1,
                    "confidence": "safe",
                    "icon": "broom",
                    "note": "",
                    "paths": [str(root / "cache.bin")],
                }
            ],
        },
        save=False,
    )
    config.set("scan.index_path", str(index.path), save=True)

    def fail_build(*_args, **_kwargs):
        raise AssertionError("não deveria recalcular sugestões no restore")

    monkeypatch.setattr(state_module, "build_suggestions", fail_build)
    state = AppState(config)
    restored = []
    state.scanFinished.connect(restored.append)
    qtbot.waitUntil(lambda: bool(restored), timeout=5000)
    try:
        assert state.last_result is not None
        assert [item.key for item in state.last_result.suggestions] == ["caches"]
        assert state.last_result.suggestions[0].savings == 123
    finally:
        state.shutdown()
        index.delete()


def test_state_restores_persisted_analysis(qapp, qtbot, tmp_path: Path) -> None:
    config = AppConfig(tmp_path / "config")
    state = AppState(config)
    base = tmp_path / "dados"
    base.mkdir()
    (base / "a.bin").write_bytes(b"x" * 10)
    (base / "b.bin").write_bytes(b"x" * 20)

    first_results = []
    index_ready = []
    state.scanFinished.connect(first_results.append)
    state.searchIndexReady.connect(index_ready.append)
    state.add_roots([str(base)], autoscan=True)
    qtbot.waitUntil(lambda: bool(first_results), timeout=5000)
    qtbot.waitUntil(lambda: bool(index_ready), timeout=5000)

    state.shutdown()
    assert config.get("scan.index_path", "")

    restored_state = AppState(config)
    restored = []
    restored_state.scanFinished.connect(restored.append)
    qtbot.waitUntil(lambda: bool(restored), timeout=5000)

    assert restored_state.last_result is not None
    assert restored_state.last_result.total_files == 2
    assert restored_state.last_result.total_size == 30
    assert restored_state.search_index is not None
    assert restored_state.search_index.search("a.bin").matches == 1
    assert config.get("scan.index_entries", 0) > 0
    restored_state.shutdown()




def test_restored_analysis_adds_only_new_root(qapp, qtbot, tmp_path: Path) -> None:
    config = AppConfig(tmp_path / "config")
    first = tmp_path / "primeira"
    second = tmp_path / "segunda"
    first.mkdir()
    second.mkdir()
    (first / "a.bin").write_bytes(b"x" * 10)
    (second / "b.bin").write_bytes(b"x" * 20)

    state = AppState(config)
    first_results = []
    first_index = []
    state.scanFinished.connect(first_results.append)
    state.searchIndexReady.connect(first_index.append)
    state.add_roots([str(first)], autoscan=True)
    qtbot.waitUntil(lambda: bool(first_results), timeout=5000)
    qtbot.waitUntil(lambda: bool(first_index), timeout=5000)
    state.shutdown()

    restored_state = AppState(config)
    restored = []
    restored_state.scanFinished.connect(restored.append)
    qtbot.waitUntil(lambda: bool(restored), timeout=5000)

    progress = []
    finished = []
    restored_state.scanProgress.connect(progress.append)
    restored_state.scanFinished.connect(finished.append)
    restored_state.add_roots([str(second)], autoscan=True)
    qtbot.waitUntil(lambda: bool(finished), timeout=5000)

    assert restored_state.last_result is not None
    assert restored_state.last_result.total_files == 2
    assert restored_state.last_result.total_size == 30
    assert progress
    assert progress[-1].roots_total == 1
    restored_state.shutdown()




def test_corrupt_persisted_index_falls_back(qapp, qtbot, tmp_path: Path) -> None:
    config = AppConfig(tmp_path / "config")
    index_dir = config.path.parent / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    corrupt = index_dir / "corrupt.sqlite"
    corrupt.write_bytes(b"not a sqlite database")
    config.set("scan.index_path", str(corrupt), save=True)

    state = AppState(config)
    failed = []
    state.searchIndexFailed.connect(failed.append)
    qtbot.waitUntil(lambda: bool(failed), timeout=5000)

    assert state.last_result is None
    assert failed
    state.shutdown()




def test_corrupt_persisted_index_is_unpublished_without_deletion(
    qapp, qtbot, tmp_path: Path
) -> None:
    config = AppConfig(tmp_path / "config")
    index_dir = config.path.parent / "index"
    index_dir.mkdir(parents=True)
    bad_index = index_dir / "search-bad.sqlite"
    bad_index.write_bytes(b"not a sqlite database")
    config.set("scan.index_path", str(bad_index))

    state = AppState(config)
    failed = []
    state.searchIndexFailed.connect(failed.append)
    qtbot.waitUntil(lambda: bool(failed), timeout=5000)

    assert state.last_result is None
    # O banco inválido não é apagado de imediato: ele fica preservado para
    # inspeção/recuperação e só pode ser removido pelo GC após a carência.
    assert bad_index.exists()
    assert config.get("scan.index_path", "") == ""
    state.shutdown()


def test_stream_publish_failure_preserves_previous_snapshot(
    qapp, tmp_path: Path, monkeypatch
) -> None:
    config = AppConfig(tmp_path / "config")
    state = AppState(config)
    old_root = tmp_path / "antiga"
    new_root = tmp_path / "nova"
    old_root.mkdir()
    new_root.mkdir()
    index_dir = config.path.parent / "index"
    old = SearchIndex.create(index_dir)
    old_result = _index_result(old_root)
    old.write(old_result)
    config.set("scan.index_path", str(old.path), save=False)
    config.set("scan.indexed_roots", [str(old_root)], save=False)
    config.set(
        "scan.summary",
        {"started_at": 1.0, "roots": [{"path": str(old_root)}]},
        save=False,
    )
    config.save()
    state.search_index = old
    state.last_result = old_result
    new = SearchIndex.create(index_dir)
    new_result = _index_result(new_root)
    new_result.index = new
    new_result.index_path = str(new.path)
    new.write(new_result)
    failed: list[str] = []
    finished: list[object] = []
    ready: list[object] = []
    state.scanFailed.connect(failed.append)
    state.scanFinished.connect(finished.append)
    state.searchIndexReady.connect(ready.append)
    monkeypatch.setattr(
        state, "_save_index_config", lambda _values: False
    )

    state._publish_stream_result(new_result)

    assert state.search_index is old
    assert state.last_result is old_result
    assert finished == []
    assert ready == []
    assert failed and "não persistida" in failed[0]
    assert old.path.exists()
    assert not new.path.exists()
    state.shutdown()
    old.delete()


def test_stream_summary_failure_preserves_previous_snapshot(
    qapp, tmp_path: Path, monkeypatch
) -> None:
    config = AppConfig(tmp_path / "config")
    state = AppState(config)
    old_root = tmp_path / "antiga"
    new_root = tmp_path / "nova"
    old_root.mkdir()
    new_root.mkdir()
    index_dir = config.path.parent / "index"
    old = SearchIndex.create(index_dir)
    old_result = _index_result(old_root)
    old.write(old_result)
    config.set("scan.index_path", str(old.path), save=False)
    config.set("scan.indexed_roots", [str(old_root)], save=False)
    config.set("scan.summary", {"started_at": 1.0}, save=False)
    config.save()
    state.search_index = old
    state.last_result = old_result
    new = SearchIndex.create(index_dir)
    new_result = _index_result(new_root)
    new_result.index = new
    new_result.index_path = str(new.path)
    new.write(new_result)
    failed: list[str] = []
    finished: list[object] = []
    ready: list[object] = []
    state.scanFailed.connect(failed.append)
    state.scanFinished.connect(finished.append)
    state.searchIndexReady.connect(ready.append)
    monkeypatch.setattr(
        SearchIndex, "store_summary", lambda self, summary: False
    )

    state._publish_stream_result(new_result)

    assert state.search_index is old
    assert state.last_result is old_result
    assert finished == []
    assert ready == []
    assert failed and "não persistida" in failed[0]
    assert old.path.exists()
    assert not new.path.exists()
    state.shutdown()
    old.delete()


def test_save_index_config_rolls_back_summary(
    qapp, tmp_path: Path, monkeypatch
) -> None:
    config = AppConfig(tmp_path / "config")
    state = AppState(config)
    previous = {"total_files": 1, "started_at": 10.0}
    config.set("scan.summary", previous, save=True)
    config.set("scan.index_path", "", save=True)

    def fail_save() -> None:
        raise OSError("disco cheio simulado")

    monkeypatch.setattr(config, "save", fail_save)

    assert (
        state._save_index_config(
            {
                "scan.summary": {"total_files": 2, "started_at": 20.0},
                "scan.index_path": "novo.sqlite",
            }
        )
        is False
    )
    assert config.get("scan.summary") == previous
    assert config.get("scan.index_path") == ""
    state.shutdown()


def test_stream_index_failure_does_not_start_memory_scan(
    qapp, tmp_path: Path, monkeypatch
) -> None:
    config = AppConfig(tmp_path / "config")
    state = AppState(config)
    state.roots = [str(tmp_path)]
    failed: list[str] = []
    state.scanFailed.connect(failed.append)

    def fail_create(_base):
        raise OSError("disco cheio simulado")

    monkeypatch.setattr(
        SearchIndex, "create", staticmethod(fail_create)
    )

    state.start_scan()

    assert failed
    assert "não foi possível criar o índice" in failed[0]
    assert state.is_scanning is False
    assert state._task is None
    state.shutdown()


def test_added_roots_wait_for_restore(qapp, tmp_path: Path, monkeypatch) -> None:
    state = AppState(AppConfig(tmp_path / "config"))
    state._restoring = True
    calls: list[dict] = []
    monkeypatch.setattr(
        state, "start_scan", lambda **kwargs: calls.append(kwargs)
    )

    state.scan_added([str(tmp_path)])
    assert calls == []
    assert state._pending_added_roots == [str(tmp_path)]

    state._restoring = False
    state._flush_pending_added()

    assert len(calls) == 1
    state.shutdown()


def test_state_discovers_managed_index_without_config_reference(
    qapp, qtbot, tmp_path: Path
) -> None:
    config = AppConfig(tmp_path / "config")
    root = tmp_path / "dados"
    root.mkdir()
    index = SearchIndex.create(config.path.parent / "index")
    result = _index_result(root)
    index.write(result)
    try:
        state = AppState(config)
        finished = []
        state.scanFinished.connect(finished.append)
        qtbot.waitUntil(lambda: bool(finished), timeout=5000)
        try:
            assert state.last_result is not None
            assert state.last_result.total_files == 1
            assert config.get("scan.index_path", "") == str(index.path)
        finally:
            state.shutdown()
    finally:
        index.delete()


def test_low_disk_space_blocks_streaming_scan(
    qapp, tmp_path: Path, monkeypatch
) -> None:
    config = AppConfig(tmp_path / "config")
    state = AppState(config)
    state.roots = [str(tmp_path)]
    failed: list[str] = []
    state.scanFailed.connect(failed.append)

    class _Usage:
        free = 0

    monkeypatch.setattr(
        state_module.shutil, "disk_usage", lambda _path: _Usage()
    )

    state.start_scan()

    assert failed
    assert "espaço livre insuficiente" in failed[0]
    assert state.is_scanning is False
    state.shutdown()


def test_state_builds_search_index_in_background(
    qapp, qtbot, tmp_path: Path
) -> None:
    config = AppConfig(tmp_path / "config")
    state = AppState(config)
    root = Node(path="C:/raiz", name="raiz", is_dir=True, dirs=1)
    root.children = [
        Node(
            path="C:/raiz/agulha.txt",
            name="agulha.txt",
            is_dir=False,
            size=10,
            files=1,
        )
    ]
    result = ScanResult(roots=[root], total_size=10, total_files=1, total_dirs=1)
    ready = []
    state.searchIndexReady.connect(ready.append)

    state._schedule_index(result)
    qtbot.waitUntil(lambda: bool(ready), timeout=5000)

    assert ready[0].search("agulha").matches == 1
    state.shutdown()


def _index_result(root: Path, name: str = "arquivo.bin", size: int = 10) -> ScanResult:
    node = Node(
        path=str(root),
        name=root.name,
        is_dir=True,
        size=size,
        files=1,
        dirs=1,
    )
    node.children = [
        Node(
            path=str(root / name),
            name=name,
            is_dir=False,
            size=size,
            files=1,
        )
    ]
    return ScanResult(
        roots=[node],
        total_size=size,
        total_files=1,
        total_dirs=1,
    )


def test_index_publish_failure_keeps_previous_snapshot(
    qapp, tmp_path: Path, monkeypatch
) -> None:
    config = AppConfig(tmp_path / "config")
    state = AppState(config)
    base = config.path.parent / "index"
    old_root = tmp_path / "antiga"
    new_root = tmp_path / "nova"
    old_root.mkdir()
    new_root.mkdir()
    old = SearchIndex.create(base)
    old.write(_index_result(old_root, "antigo.bin"))
    config.set("scan.index_path", str(old.path), save=False)
    config.set("scan.indexed_roots", [str(old_root)], save=False)
    config.save()
    state.search_index = old
    new = SearchIndex.create(base)
    new.write(_index_result(new_root, "novo.bin"))
    failed = []
    state.searchIndexFailed.connect(failed.append)
    state._index_generation = 1

    def fail_save() -> None:
        raise OSError("disco cheio simulado")

    with monkeypatch.context() as patch:
        patch.setattr(config, "save", fail_save)
        state._on_index_ready(1, new)

    assert state.search_index is None
    assert old.path.exists()
    assert config.get("scan.index_path", "") == str(old.path)
    assert config.get("scan.indexed_roots", []) == [str(old_root)]
    assert not new.path.exists()
    assert failed == ["falha ao publicar o índice de busca"]
    state.shutdown()


def test_restore_falls_back_to_previous_snapshot(
    qapp, qtbot, tmp_path: Path
) -> None:
    config = AppConfig(tmp_path / "config")
    base = tmp_path / "index"
    root = tmp_path / "valida"
    root.mkdir()
    valid = SearchIndex.create(base)
    valid.write(_index_result(root))
    broken = base / f"search-{'f' * 32}.sqlite"
    broken.write_bytes(b"nao e sqlite")
    config.set("scan.index_path", str(broken), save=False)
    config.set("scan.index_previous_path", str(valid.path), save=False)
    config.set("scan.indexed_roots", [str(root)], save=False)
    config.save()

    state = AppState(config)
    restored = []
    state.scanFinished.connect(restored.append)
    qtbot.waitUntil(lambda: bool(restored), timeout=5000)

    assert state.search_index is not None
    assert state.search_index.path == valid.path
    assert config.get("scan.index_path", "") == str(valid.path)
    assert config.get("scan.index_previous_path", "") == ""
    assert broken.exists()
    state.shutdown()


def test_missing_persisted_index_clears_reference(
    qapp, qtbot, tmp_path: Path
) -> None:
    config = AppConfig(tmp_path / "config")
    missing = (
        config.path.parent / "index" / f"search-{'e' * 32}.sqlite"
    )
    config.set("scan.index_path", str(missing))
    state = AppState(config)
    failed = []
    state.searchIndexFailed.connect(failed.append)

    qtbot.waitUntil(lambda: bool(failed), timeout=5000)

    assert failed == ["índice persistido ausente"]
    assert config.get("scan.index_path", "") == ""
    state.shutdown()


def test_restored_snapshot_reports_pending_roots(
    qapp, qtbot, tmp_path: Path
) -> None:
    first = tmp_path / "primeira"
    second = tmp_path / "segunda"
    first.mkdir()
    second.mkdir()
    config = AppConfig(tmp_path / "config")
    index = SearchIndex.create(tmp_path / "index")
    index.write(_index_result(first))
    config.roots = [str(first), str(second)]
    config.set("scan.index_path", str(index.path), save=False)
    config.set("scan.indexed_roots", [str(first)], save=False)
    config.save()

    state = AppState(config)
    restored = []
    pending = []
    state.scanFinished.connect(restored.append)
    state.rootsPending.connect(pending.append)
    qtbot.waitUntil(lambda: bool(restored), timeout=5000)

    assert [path_key(path) for path in state.pending_roots] == [
        path_key(str(second))
    ]
    assert pending
    assert [path_key(path) for path in pending[-1]] == [
        path_key(str(second))
    ]
    state.shutdown()


def test_scan_task_honors_the_shared_budget(qapp, tmp_path: Path) -> None:
    base = tmp_path / "dados"
    base.mkdir()
    for number in range(10):
        (base / f"arquivo_{number}.bin").write_bytes(b"x")

    task = ScanTask([str(base)], threading.Event(), max_entries=3)
    result = task.execute()

    assert result.truncated is True
    assert result.total_files + result.total_dirs <= 3
    assert len(result.roots) == 1


def test_index_gc_protects_active_previous_and_recent_orphans(
    qapp, tmp_path: Path
) -> None:
    config = AppConfig(tmp_path / "config")
    state = AppState(config)
    base = config.path.parent / "index"
    active = SearchIndex.create(base)
    active.write(_index_result(tmp_path / "ativa"))
    previous = SearchIndex.create(base)
    previous.write(_index_result(tmp_path / "anterior"))
    orphan = base / f"search-{'c' * 32}.sqlite"
    orphan.write_bytes(b"x")
    old = time.time() - 3 * 24 * 60 * 60
    os.utime(orphan, (old, old))
    config.set("scan.index_path", str(active.path), save=False)
    config.set("scan.index_previous_path", str(previous.path), save=False)
    config.save()
    state.search_index = active

    state._collect_index_garbage(
        protected_paths=[str(active.path), str(previous.path)]
    )

    assert active.path.exists()
    assert previous.path.exists()
    assert not orphan.exists()
    state.shutdown()


def test_clear_results_removes_managed_snapshots(
    qapp, tmp_path: Path
) -> None:
    config = AppConfig(tmp_path / "config")
    state = AppState(config)
    base = config.path.parent / "index"
    active = SearchIndex.create(base)
    active.write(_index_result(tmp_path / "ativa"))
    config.set("scan.index_path", str(active.path), save=False)
    config.set("scan.indexed_roots", [str(tmp_path / "ativa")], save=False)
    config.save()
    state.search_index = active

    state.clear_results()

    assert not active.path.exists()
    assert config.get("scan.index_path", "") == ""
    assert config.get("scan.indexed_roots", []) == []
    state.shutdown()


def test_index_prepare_failure_clears_stale_search_index(
    qapp, tmp_path: Path, monkeypatch
) -> None:
    state = AppState(AppConfig(tmp_path / "config"))
    state.search_index = object()
    failed = []
    state.searchIndexFailed.connect(failed.append)

    def fail_create(_base):
        raise OSError("disco cheio simulado")

    monkeypatch.setattr(SearchIndex, "create", staticmethod(fail_create))
    state._schedule_index(_index_result(tmp_path / "raiz"))

    assert state.search_index is None
    assert state.index_building is False
    assert failed and "disco cheio" in failed[0]
    state.shutdown()


def test_scan_added_uses_the_remaining_auto_limit(
    qapp, tmp_path: Path, monkeypatch
) -> None:
    state = AppState(AppConfig(tmp_path / "config"))
    base_root = Node(
        path=str(tmp_path),
        name=tmp_path.name,
        is_dir=True,
        dirs=1,
    )
    state.roots = [str(tmp_path)]
    state.last_result = ScanResult(
        roots=[base_root],
        total_files=1_400_000,
        total_dirs=1,
    )
    state._current_limit_entries = 2_000_000
    monkeypatch.setattr(state, "_can_merge_added", lambda _added: True)
    captured = {}
    monkeypatch.setattr(
        state,
        "start_scan",
        lambda **kwargs: captured.update(kwargs),
    )

    state.scan_added([str(tmp_path / "nova")])

    assert captured["merge"] is True
    assert captured["max_entries"] == 599_999
    state.shutdown()


def test_memory_engine_keeps_full_tree_and_index(
    qapp, qtbot, tmp_path: Path
) -> None:
    config = AppConfig(tmp_path / "config")
    config.set("scan.engine", "memory")
    state = AppState(config)
    root = tmp_path / "dados"
    root.mkdir()
    (root / "a.bin").write_bytes(b"x" * 10)
    results = []
    ready = []
    state.scanFinished.connect(results.append)
    state.searchIndexReady.connect(ready.append)

    state.add_roots([str(root)], autoscan=True)
    qtbot.waitUntil(lambda: bool(results) and bool(ready), timeout=5000)

    assert state.last_result is not None
    assert state.last_result.lazy is False
    assert state.last_result.roots[0].children_loaded is True
    assert state.last_result.roots[0].children[0].name == "a.bin"
    index = state.search_index
    assert index is not None
    assert index.load_summary() is not None
    persisted = config.get("scan.summary")
    assert "suggestions" not in persisted
    assert persisted["index_path"] == str(index.path)
    state.shutdown()


def _retention_state(qapp, tmp_path: Path):
    config = AppConfig(tmp_path / "config")
    state = AppState(config)
    base = config.path.parent / "index"
    active = SearchIndex.create(base)
    active.write(_index_result(tmp_path / "ativa"))
    previous = SearchIndex.create(base)
    previous.write(_index_result(tmp_path / "anterior"))
    config.set("scan.index_path", str(active.path), save=False)
    config.set("scan.index_previous_path", str(previous.path), save=False)
    config.set("scan.index_verified_at", time.time(), save=False)
    config.set("scan.index_previous_days", 7, save=False)
    config.set("scan.index_max_gb", 8, save=False)
    config.save()
    state.search_index = active
    return state, config, active, previous


def test_previous_index_expires_after_retention(qapp, tmp_path: Path) -> None:
    state, config, active, previous = _retention_state(qapp, tmp_path)
    old = time.time() - 8 * 24 * 60 * 60
    os.utime(previous.path, (old, old))

    state._enforce_index_retention()

    assert active.path.exists()
    assert not previous.path.exists()
    assert config.get("scan.index_previous_path", "") == ""
    state.shutdown()


def test_previous_index_is_kept_until_active_is_verified(
    qapp, tmp_path: Path
) -> None:
    state, config, active, previous = _retention_state(qapp, tmp_path)
    old = time.time() - 8 * 24 * 60 * 60
    os.utime(previous.path, (old, old))
    config.set("scan.index_verified_at", 0)
    config.save()

    state._enforce_index_retention()

    assert previous.path.exists()
    assert config.get("scan.index_previous_path", "") == str(previous.path)
    state.shutdown()


def test_index_quota_removes_previous_after_min_age(
    qapp, tmp_path: Path
) -> None:
    state, config, active, previous = _retention_state(qapp, tmp_path)
    old = time.time() - 2 * 24 * 60 * 60
    os.utime(previous.path, (old, old))
    config.set("scan.index_max_gb", 1e-9, save=True)

    state._enforce_index_retention()

    assert active.path.exists()
    assert not previous.path.exists()
    assert config.get("scan.index_previous_path", "") == ""
    state.shutdown()


def test_index_quota_never_deletes_active(qapp, tmp_path: Path) -> None:
    config = AppConfig(tmp_path / "config")
    state = AppState(config)
    base = config.path.parent / "index"
    active = SearchIndex.create(base)
    active.write(_index_result(tmp_path / "ativa"))
    config.set("scan.index_path", str(active.path), save=False)
    config.set("scan.index_previous_path", "", save=False)
    config.set("scan.index_max_gb", 1e-9, save=True)
    state.search_index = active

    state._enforce_index_retention()

    assert active.path.exists()
    assert config.get("scan.index_path", "") == str(active.path)
    state.shutdown()


def test_clear_previous_index_keeps_active(qapp, tmp_path: Path) -> None:
    state, config, active, previous = _retention_state(qapp, tmp_path)

    removed = state.clear_previous_index()

    assert removed is True
    assert active.path.exists()
    assert not previous.path.exists()
    assert config.get("scan.index_path", "") == str(active.path)
    assert config.get("scan.index_previous_path", "") == ""
    state.shutdown()
