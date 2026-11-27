from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QTreeWidgetItem

from app.config import AppConfig
from app.features.analyzer.tree import NODE_ROLE, FileTree, _IndexFilterTask
from app.services.index_store import SearchHits, SearchIndex
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


def test_visible_count_updates_after_collapse(
    qapp, qtbot, tmp_path: Path
) -> None:
    config = AppConfig(tmp_path / "config")
    init_theme(qapp, config)
    root = Node(path="C:/raiz", name="raiz", is_dir=True, dirs=3)
    for index in range(3):
        root.children.append(
            Node(
                path=f"C:/raiz/arquivo_{index}.bin",
                name=f"arquivo_{index}.bin",
                is_dir=False,
                size=10,
                files=1,
            )
        )
    result = ScanResult(
        roots=[root],
        total_size=30,
        total_files=3,
        total_dirs=1,
    )
    tree = FileTree()
    qtbot.addWidget(tree)
    tree.show()
    tree.set_result(result)
    qtbot.waitUntil(lambda: tree.shown >= 4, timeout=5000)

    item = tree.topLevelItem(0)
    tree.collapseItem(item)
    qtbot.waitUntil(lambda: tree.shown == 1, timeout=2000)
    tree.close()


def test_filtered_render_handles_deep_tree(qapp, qtbot, tmp_path: Path) -> None:
    config = AppConfig(tmp_path / "config")
    init_theme(qapp, config)
    root = Node(path="C:/raiz", name="raiz", is_dir=True, dirs=1)
    current = root
    for depth in range(3000):
        child = Node(
            path=f"C:/raiz/nivel_{depth}",
            name=f"nivel_{depth}",
            is_dir=True,
            dirs=1,
        )
        current.children = [child]
        current = child
    current.children = [
        Node(
            path="C:/raiz/alvo.txt",
            name="alvo.txt",
            is_dir=False,
            size=1,
            files=1,
        )
    ]
    result = ScanResult(
        roots=[root],
        total_size=1,
        total_files=1,
        total_dirs=3001,
    )

    tree = FileTree()
    qtbot.addWidget(tree)
    tree.show()
    tree.set_result(result)
    tree.set_query("alvo")
    qtbot.waitUntil(lambda: tree.matches != -1, timeout=10000)

    assert tree.matches == 1
    assert tree.shown >= 1

    found = False
    stack = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
    while stack:
        item = stack.pop()
        node = item.data(0, NODE_ROLE)
        if node is not None and getattr(node, "path", "") == "C:/raiz/alvo.txt":
            found = True
            break
        stack.extend(item.child(i) for i in range(item.childCount()))
    assert found
    # As duas rotinas auxiliares também precisam sobreviver à profundidade.
    paths = tree._expanded_paths()
    tree._restore_expanded(tree.topLevelItem(0), paths)
    tree._expand_all_budget = 10_000
    tree._expand_all_children(tree.topLevelItem(0))
    tree.close()




def test_expand_all_children_preserves_sibling_order(
    qapp, tmp_path: Path
) -> None:
    config = AppConfig(tmp_path / "config")
    init_theme(qapp, config)
    tree = FileTree()
    parent = QTreeWidgetItem(["raiz"])
    tree.addTopLevelItem(parent)
    children = []
    for index in range(4):
        node = Node(
            path=f"C:/raiz/dir_{index}",
            name=f"dir_{index}",
            is_dir=True,
            dirs=1,
        )
        child = QTreeWidgetItem([f"dir_{index}"])
        child.setData(0, NODE_ROLE, node)
        parent.addChild(child)
        children.append(child)

    tree._expand_all_budget = 2
    tree._expand_all_children(parent)

    assert [child.isExpanded() for child in children] == [
        True,
        True,
        False,
        False,
    ]
    tree.close()


class _SingleHitIndex:
    def __init__(self, path: str) -> None:
        self.path = path

    def search(self, *args, **kwargs) -> SearchHits:
        return SearchHits([self.path], 1)


def test_index_filter_preserves_exact_case_identity(qapp) -> None:
    root = Node(path=r"C:\raiz", name="raiz", is_dir=True, dirs=1)
    upper = Node(
        path=r"C:\raiz\Relatorio.txt",
        name="Relatorio.txt",
        is_dir=False,
        size=1,
        files=1,
    )
    lower = Node(
        path=r"C:\raiz\relatorio.txt",
        name="relatorio.txt",
        is_dir=False,
        size=1,
        files=1,
    )
    root.children = [upper, lower]
    result = ScanResult(
        roots=[root],
        total_size=2,
        total_files=2,
        total_dirs=1,
    )
    task = _IndexFilterTask(
        result,
        _SingleHitIndex(upper.path),
        "relatorio",
        "all",
        "name_asc",
        1,
    )

    filtered = task.execute()

    assert id(root) in filtered.included
    assert id(upper) in filtered.included
    assert id(lower) not in filtered.included


def test_tree_uses_sqlite_search_backend(qapp, qtbot, tmp_path: Path) -> None:
    config = AppConfig(tmp_path / "config")
    init_theme(qapp, config)
    root = Node(path="C:/raiz", name="raiz", is_dir=True, dirs=1)
    for index in range(500):
        root.children.append(
            Node(
                path=f"C:/raiz/arquivo_{index}.bin",
                name=f"arquivo_{index}.bin",
                is_dir=False,
                size=10,
                files=1,
            )
        )
    needle = Node(
        path="C:/raiz/agulha.txt",
        name="agulha.txt",
        is_dir=False,
        size=10,
        files=1,
    )
    root.children.append(needle)
    result = ScanResult(
        roots=[root],
        total_size=10,
        total_files=len(root.children),
        total_dirs=1,
    )
    search_index = SearchIndex.create(tmp_path / "index")
    try:
        search_index.write(result)
        tree = FileTree()
        qtbot.addWidget(tree)
        tree.show()
        tree.set_result(result)
        tree.set_search_index(search_index)
        tree.set_query("agulha")
        qtbot.waitUntil(lambda: tree.matches != -1, timeout=5000)

        assert tree.matches == 1
        assert tree.shown >= 1
        tree.close()
    finally:
        search_index.delete()
