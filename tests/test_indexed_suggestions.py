from __future__ import annotations

import sqlite3
from pathlib import Path

from app.services.indexed_suggestions import build_indexed_suggestions


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
