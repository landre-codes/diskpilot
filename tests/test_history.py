from __future__ import annotations

from pathlib import Path

from app.services.history import (
    HISTORY_LIMIT,
    compare_snapshots,
    merge_snapshot,
    sanitize_history,
)
from app.services.model import Node, ScanResult, Suggestion


def _result(
    root: Path,
    size: int,
    *,
    started_at: float,
    files: int = 1,
    dirs: int = 1,
    safe: int = 0,
    review: int = 0,
    truncated: bool = False,
) -> ScanResult:
    node = Node(
        path=str(root),
        name=root.name,
        is_dir=True,
        size=size,
        files=files,
        dirs=dirs,
    )
    suggestions = []
    if safe:
        suggestions.append(
            Suggestion(
                key="caches",
                title="Caches",
                description="",
                savings=safe,
                count=1,
                confidence="safe",
                icon="broom",
            )
        )
    if review:
        suggestions.append(
            Suggestion(
                key="duplicates",
                title="Duplicatas",
                description="",
                savings=review,
                count=1,
                confidence="review",
                icon="content-duplicate",
            )
        )
    return ScanResult(
        roots=[node],
        total_size=size,
        total_files=files,
        total_dirs=dirs,
        started_at=started_at,
        truncated=truncated,
        suggestions=suggestions,
    )


def test_merge_snapshot_dedupes_sorts_and_limits(tmp_path: Path) -> None:
    root = tmp_path / "dados"
    history: list[dict] = []
    first = _result(root, 1000, started_at=10.0)
    second = _result(root, 600, started_at=20.0)

    history = merge_snapshot(history, first, index_entries=10)
    assert len(history) == 1
    history = merge_snapshot(history, first, index_entries=10)
    assert len(history) == 1
    history = merge_snapshot(history, second, index_entries=8)
    assert [entry["total_size"] for entry in history] == [1000, 600]

    many = [
        {
            "started_at": float(number),
            "total_size": number,
            "index_entries": number,
        }
        for number in range(1, HISTORY_LIMIT + 10)
    ]
    limited = merge_snapshot(many, _result(root, 1, started_at=999.0))
    assert len(limited) == HISTORY_LIMIT
    assert limited[-1]["started_at"] == 999.0


def test_compare_reports_reduction_and_identified_savings(
    tmp_path: Path,
) -> None:
    root = tmp_path / "dados"
    history = merge_snapshot(
        [], _result(root, 1000, started_at=10.0), index_entries=10
    )
    history = merge_snapshot(
        history,
        _result(
            root,
            600,
            started_at=20.0,
            safe=200,
            review=100,
        ),
        index_entries=8,
    )

    comparison = compare_snapshots(history)

    assert comparison["available"] is True
    assert comparison["comparable"] is True
    assert comparison["reclaimed"] == 400
    assert comparison["increase"] == 0
    assert comparison["net_delta"] == -400
    assert comparison["identified_safe"] == 200
    assert comparison["identified_review"] == 100
    assert comparison["identified_total"] == 300
    assert comparison["roots"][0]["reclaimed"] == 400


def test_compare_flags_root_change(tmp_path: Path) -> None:
    history = merge_snapshot(
        [], _result(tmp_path / "antiga", 1000, started_at=10.0)
    )
    history = merge_snapshot(
        history, _result(tmp_path / "nova", 600, started_at=20.0)
    )

    comparison = compare_snapshots(history)

    assert comparison["available"] is True
    assert comparison["comparable"] is False
    assert comparison["reclaimed"] == 0
    assert "raízes" in comparison["reason"]
    assert {row["status"] for row in comparison["roots"]} == {
        "nova raiz",
        "raiz removida",
    }


def test_compare_flags_truncated_snapshot(tmp_path: Path) -> None:
    root = tmp_path / "dados"
    history = merge_snapshot(
        [],
        _result(root, 1000, started_at=10.0, truncated=True),
    )
    history = merge_snapshot(
        history, _result(root, 600, started_at=20.0)
    )

    comparison = compare_snapshots(history)

    assert comparison["comparable"] is False
    assert comparison["reclaimed"] == 0
    assert "truncado" in comparison["reason"]


def test_compare_with_one_snapshot_reports_identificado(
    tmp_path: Path,
) -> None:
    history = merge_snapshot(
        [],
        _result(
            tmp_path / "dados",
            1000,
            started_at=10.0,
            safe=200,
            review=100,
        ),
    )

    comparison = compare_snapshots(history)

    assert comparison["available"] is False
    assert "insuficiente" in comparison["reason"]
    assert comparison["identified_total"] == 300


def test_sanitize_history_can_drop_roots(tmp_path: Path) -> None:
    history = merge_snapshot(
        [], _result(tmp_path / "dados", 1000, started_at=10.0)
    )

    sanitized = sanitize_history(history, include_roots=False)

    assert sanitized
    assert "roots" not in sanitized[0]
    assert sanitized[0]["total_size"] == 1000
