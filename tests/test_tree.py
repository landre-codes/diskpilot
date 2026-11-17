from __future__ import annotations

from pathlib import Path

from app.config import AppConfig
from app.features.analyzer.tree import FileTree
from app.services.model import Node, ScanResult
from appshell.theme import init_theme


def test_search_finds_item_after_30k_nodes(qapp, qtbot, tmp_path: Path) -> None:
    config = AppConfig(tmp_path / "config")
    init_theme(qapp, config)
    root = Node(path="C:/raiz", name="raiz", is_dir=True, dirs=1)
    total = 0
    for index in range(30_050):
        child = Node(
            path=f"C:/raiz/arquivo_{index}.bin",
            name=f"arquivo_{index}.bin",
            is_dir=False,
            size=10,
            files=1,
        )
        root.children.append(child)
        total += child.size
    needle = Node(
        path="C:/raiz/agulha.txt",
        name="agulha.txt",
        is_dir=False,
        size=10,
        files=1,
    )
    root.children.append(needle)
    total += needle.size
    result = ScanResult(
        roots=[root],
        total_size=total,
        total_files=len(root.children),
        total_dirs=1,
    )

    tree = FileTree()
    qtbot.addWidget(tree)
    tree.show()
    tree.set_result(result)
    tree.set_query("agulha")
    qtbot.waitUntil(lambda: tree.matches != -1, timeout=10000)

    assert tree.matches == 1
    assert tree.shown >= 1
    tree.close()
