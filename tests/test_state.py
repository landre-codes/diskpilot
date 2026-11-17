from __future__ import annotations

from pathlib import Path

from app.config import AppConfig
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
