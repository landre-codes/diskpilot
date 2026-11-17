from __future__ import annotations

from pathlib import Path

from app.config import AppConfig
from app.services.model import Node, ScanResult
from app.services import state as state_module
from app.services.state import AppState


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
    assert merged.roots[0] is first_result.roots[0]
    assert merged.total_files == 2
    assert merged.total_size == 30
    state.shutdown()


def test_state_builds_search_index_in_background(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(state_module, "INDEX_THRESHOLD", 1)
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
