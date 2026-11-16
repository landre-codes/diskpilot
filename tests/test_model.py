from __future__ import annotations

from app.services.model import Node, ScanResult, top_items


def test_top_items_single_pass_orders_dirs_and_files() -> None:
    root = Node(path="C:/root", name="root", is_dir=True)
    root.children = [
        Node(path="C:/root/dir_a", name="dir_a", is_dir=True, size=10),
        Node(path="C:/root/dir_b", name="dir_b", is_dir=True, size=30),
        Node(path="C:/root/a.bin", name="a.bin", is_dir=False, size=20),
        Node(path="C:/root/b.bin", name="b.bin", is_dir=False, size=40),
    ]
    result = ScanResult(roots=[root])

    dirs, files = top_items(result, limit=2)

    assert [(node.size, node.name) for node in dirs] == [(30, "dir_b"), (10, "dir_a")]
    assert [(node.size, node.name) for node in files] == [(40, "b.bin"), (20, "a.bin")]


def test_top_items_zero_limit() -> None:
    result = ScanResult(roots=[])
    assert top_items(result, limit=0) == ([], [])
