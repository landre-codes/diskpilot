from __future__ import annotations

import os
from pathlib import Path

import app.services.scanner as scanner_module
from app.services.model import all_nodes
from app.services.scanner import scan_paths


def _make_tree(root: Path, files: int = 8) -> None:
    for index in range(3):
        folder = root / f"dir_{index}"
        folder.mkdir(parents=True)
        for file_index in range(files):
            (folder / f"file_{file_index}.bin").write_bytes(
                b"x" * (index + 1) * 10
            )


def test_parallel_roots_match_sequential_totals(tmp_path: Path) -> None:
    roots = []
    for index in range(3):
        root = tmp_path / f"root_{index}"
        _make_tree(root)
        roots.append(str(root))

    parallel = scan_paths(roots)
    sequential_files = 0
    sequential_dirs = 0
    sequential_size = 0
    for root in roots:
        result = scan_paths([root])
        sequential_files += result.total_files
        sequential_dirs += result.total_dirs
        sequential_size += result.total_size

    assert parallel.total_files == sequential_files
    assert parallel.total_dirs == sequential_dirs
    assert parallel.total_size == sequential_size
    assert len(parallel.roots) == 3
    assert not parallel.truncated


def test_parallel_budget_is_shared(tmp_path: Path) -> None:
    roots = []
    for index in range(3):
        root = tmp_path / f"root_{index}"
        _make_tree(root, files=10)
        roots.append(str(root))

    result = scan_paths(roots, max_entries=25)

    assert result.truncated
    assert result.total_files + result.total_dirs <= 25


def test_parallel_progress_aggregates_roots(tmp_path: Path) -> None:
    roots = []
    for index in range(3):
        root = tmp_path / f"root_{index}"
        _make_tree(root)
        roots.append(str(root))

    events = []
    result = scan_paths(roots, progress_cb=events.append)

    final = events[-1]
    assert final.roots_total == len(roots)
    assert final.roots_done == len(roots)
    assert final.files == result.total_files
    assert final.dirs == result.total_dirs
    assert final.bytes_seen == result.total_size


def test_permission_error_on_subfolder_is_counted_and_scan_continues(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "root"
    allowed = root / "permitida"
    blocked = root / "bloqueada"
    allowed.mkdir(parents=True)
    blocked.mkdir()
    (allowed / "visivel.bin").write_bytes(b"x" * 10)
    (blocked / "oculto.bin").write_bytes(b"x" * 99)

    real_scandir = scanner_module.os.scandir
    blocked_key = os.path.normcase(os.path.abspath(blocked))

    def fake_scandir(path):
        key = os.path.normcase(os.path.abspath(str(path)))
        if key == blocked_key:
            raise PermissionError(13, "Acesso negado", str(path))
        return real_scandir(path)

    monkeypatch.setattr(scanner_module.os, "scandir", fake_scandir)
    result = scan_paths([str(root)])

    assert result.errors == 1
    assert result.total_files == 1
    blocked_node = next(
        node for node in all_nodes(result) if node.path == str(blocked)
    )
    assert "Acesso negado" in blocked_node.error


def test_inaccessible_root_does_not_abort_other_roots(
    tmp_path: Path, monkeypatch
) -> None:
    blocked = tmp_path / "raiz_bloqueada"
    allowed = tmp_path / "raiz_permitida"
    blocked.mkdir()
    allowed.mkdir()
    (blocked / "oculto.bin").write_bytes(b"x" * 99)
    (allowed / "visivel.bin").write_bytes(b"x" * 10)

    real_scandir = scanner_module.os.scandir
    blocked_key = os.path.normcase(os.path.abspath(blocked))

    def fake_scandir(path):
        key = os.path.normcase(os.path.abspath(str(path)))
        if key == blocked_key:
            raise PermissionError(13, "Acesso negado", str(path))
        return real_scandir(path)

    monkeypatch.setattr(scanner_module.os, "scandir", fake_scandir)
    result = scan_paths([str(blocked), str(allowed)])

    assert result.errors == 1
    assert result.total_files == 1
    blocked_node = next(
        node for node in all_nodes(result) if node.path == str(blocked)
    )
    assert "Acesso negado" in blocked_node.error
