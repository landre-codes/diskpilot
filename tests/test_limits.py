from __future__ import annotations

from app.services.limits import (
    BUDGET_FRACTION,
    BYTES_PER_ENTRY,
    DEFAULT_ENTRIES,
    MAX_ENTRIES,
    MIN_ENTRIES,
    RESERVE_BYTES,
    estimate_max_entries,
)


def test_estimate_max_entries_respects_hard_ceiling() -> None:
    available = 64 * 1024**3

    assert estimate_max_entries(available_bytes=available) == MAX_ENTRIES


def test_estimate_max_entries_respects_memory_budget() -> None:
    available = 4 * 1024**3
    expected = int(
        (available - RESERVE_BYTES) * BUDGET_FRACTION / BYTES_PER_ENTRY
    )

    assert estimate_max_entries(available_bytes=available) == max(
        MIN_ENTRIES, min(MAX_ENTRIES, expected)
    )


def test_estimate_max_entries_never_goes_below_floor() -> None:
    assert estimate_max_entries(available_bytes=0) == MIN_ENTRIES


def test_estimate_max_entries_falls_back_without_memory_data(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.services.limits.available_memory_bytes", lambda: None
    )

    assert estimate_max_entries() == DEFAULT_ENTRIES


def test_manual_override_can_reduce_but_not_exceed_budget() -> None:
    available = 8 * 1024**3

    assert estimate_max_entries(
        available_bytes=available, override=500_000
    ) == 500_000
    assert estimate_max_entries(
        available_bytes=0, override=5_000_000
    ) == MIN_ENTRIES
