from __future__ import annotations

from appshell.utils import format_duration


def test_format_duration_uses_hh_mm_ss() -> None:
    assert format_duration(0) == "00:00:00"
    assert format_duration(3.4) == "00:00:03"
    assert format_duration(65) == "00:01:05"
    assert format_duration(3725) == "01:02:05"
    assert format_duration(None) == "00:00:00"
