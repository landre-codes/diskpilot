from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from app.services.indexed_suggestions import build_indexed_suggestions
from app.services.index_store import SearchIndex


def _legacy_index(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
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
        "INSERT INTO nodes VALUES "
        "(1,1,NULL,1,'raiz','raiz','C:\\raiz','c:\\raiz',1,4096,0,1,2,0,'')"
    )
    conn.execute(
        "INSERT INTO nodes VALUES "
        "(2,1,1,1,'node_modules','node_modules',"
        "'C:\\raiz\\node_modules','c:\\raiz\\node_modules',1,4096,0,1,1,1,'')"
    )
    conn.commit()
    conn.close()


def test_indexed_suggestions_support_legacy_index_without_path_exact(
    tmp_path: Path,
) -> None:
    path = tmp_path / "legacy.sqlite"
    _legacy_index(path)

    suggestions = build_indexed_suggestions(str(path))

    assert [suggestion.key for suggestion in suggestions] == ["caches"]
    assert suggestions[0].savings == 4096
    assert suggestions[0].paths == ["C:\\raiz\\node_modules"]
    nodes = SearchIndex(path).nodes_by_paths(["C:\\raiz\\node_modules"])
    assert [node.path for node in nodes] == ["C:\\raiz\\node_modules"]


def test_indexed_suggestions_classifies_candidate_categories(
    tmp_path: Path,
) -> None:
    path = tmp_path / "candidates.sqlite"
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE nodes (
            id INTEGER PRIMARY KEY,
            scan_id INTEGER NOT NULL,
            parent_id INTEGER,
            root_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            name_fold TEXT NOT NULL,
            path TEXT NOT NULL,
            path_exact TEXT NOT NULL,
            path_key TEXT NOT NULL,
            is_dir INTEGER NOT NULL,
            size INTEGER NOT NULL,
            mtime REAL NOT NULL,
            files INTEGER NOT NULL,
            dirs INTEGER NOT NULL,
            depth INTEGER NOT NULL,
            error TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO nodes VALUES "
        "(1,1,NULL,1,'raiz','raiz','C:\\raiz','C:\\raiz','c:\\raiz',1,0,0,4,5,0,'')"
    )
    rows = [
        (2, "antigo.bin", "C:\\raiz\\antigo.bin", 201 * 1024 * 1024, 0),
        (3, "dup.bin", "C:\\raiz\\a\\dup.bin", 11 * 1024 * 1024, 0),
        (4, "dup.bin", "C:\\raiz\\b\\dup.bin", 11 * 1024 * 1024, 0),
        (5, "grande.iso", "C:\\raiz\\grande.iso", 1024 * 1024 * 1024, time.time()),
        (6, "resto.tmp", "C:\\raiz\\resto.tmp", 21 * 1024 * 1024, time.time()),
    ]
    conn.executemany(
        "INSERT INTO nodes (id, scan_id, parent_id, root_id, name, name_fold, "
        "path, path_exact, path_key, is_dir, size, mtime, files, dirs, "
        "depth, error) VALUES (?,1,1,1,?,?,?,?,?,0,?,?,1,0,1,'')",
        [
            (
                node_id,
                name,
                name,
                path_text,
                path_text,
                path_text.lower(),
                size,
                mtime,
            )
            for node_id, name, path_text, size, mtime in rows
        ],
    )
    conn.commit()
    conn.close()

    suggestions = build_indexed_suggestions(str(path))
    keys = {suggestion.key for suggestion in suggestions}

    assert {"stale", "duplicates", "archives", "temp"} <= keys
    assert next(s for s in suggestions if s.key == "duplicates").count == 1


def test_indexed_suggestions_handle_many_cache_prefixes(
    tmp_path: Path,
) -> None:
    path = tmp_path / "many.sqlite"
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE nodes (
            id INTEGER PRIMARY KEY,
            scan_id INTEGER NOT NULL,
            parent_id INTEGER,
            root_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            name_fold TEXT NOT NULL,
            path TEXT NOT NULL,
            path_exact TEXT NOT NULL,
            path_key TEXT NOT NULL,
            is_dir INTEGER NOT NULL,
            size INTEGER NOT NULL,
            mtime REAL NOT NULL,
            files INTEGER NOT NULL,
            dirs INTEGER NOT NULL,
            depth INTEGER NOT NULL,
            error TEXT NOT NULL
        )
        """
    )
    conn.executemany(
        "INSERT INTO nodes VALUES (?,1,1,2,'node_modules','node_modules',?,?,?,1,1,0,1,1,2,'')",
        [
            (
                index + 2,
                f"C:/raiz/p{index}/node_modules",
                f"c:/raiz/p{index}/node_modules",
                f"c:/raiz/p{index}/node_modules",
            )
            for index in range(20000)
        ],
    )
    conn.commit()
    conn.close()

    suggestions = build_indexed_suggestions(str(path))

    assert suggestions
    assert suggestions[0].key == "caches"
    assert suggestions[0].count == 20000
    assert len(suggestions[0].paths) == 60
