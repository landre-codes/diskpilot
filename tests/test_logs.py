from __future__ import annotations

from pathlib import Path

from app.config import AppConfig
from app.features.logs import (
    LogsPage,
    _LEVEL_ICON_NAMES,
    _display_line,
    _display_parts,
)
from app.services.state import AppState
from appshell.theme import init_theme


def test_level_icons_are_coherent_with_filter_icons() -> None:
    assert _LEVEL_ICON_NAMES["INFO"] == "information-outline"
    assert _LEVEL_ICON_NAMES["WARNING"] == "alert-outline"
    assert _LEVEL_ICON_NAMES["ERROR"] == "alert-octagon-outline"
    assert _LEVEL_ICON_NAMES["DEBUG"] == "bug-outline"


def test_display_parts_normalizes_date_and_level() -> None:
    level, text = _display_parts(
        "2026-11-18 15:19:18 INFO diskpilot.state: análise concluída"
    )

    assert level == "INFO"
    assert text == "18/11/2026 15:19:18 INFO diskpilot.state: análise concluída"
    assert "\ufffc" not in text
    assert _display_line(
        "2026-11-18 15:19:18 INFO diskpilot.state: ok"
    ) == "18/11/2026 15:19:18 INFO diskpilot.state: ok"


def test_display_parts_aliases_warn_and_critical() -> None:
    assert _display_parts(
        "2026-11-18 15:19:18 WARN diskpilot: atenção"
    )[0] == "WARNING"
    assert _display_parts(
        "2026-11-18 15:19:18 CRITICAL diskpilot: falha"
    )[0] == "ERROR"


def test_display_parts_handles_crash_lines() -> None:
    assert _display_parts(
        "Windows fatal exception: access violation", crash=True
    )[0] == "ERROR"
    assert _display_parts("Thread 0x1234 (most recent call first):", crash=True)[0] == "THREAD"
    level, text = _display_parts("detalhe técnico", crash=True)
    assert level == ""
    assert text == "  detalhe técnico"


def test_logs_page_renders_level_icons(qapp, tmp_path: Path) -> None:
    config = AppConfig(tmp_path / "config")
    init_theme(qapp, config)
    state = AppState(config)
    page = LogsPage(state)
    try:
        page._render_lines(
            [
                "2026-11-18 15:19:18 INFO diskpilot.state: ok",
                "2026-11-18 15:19:19 WARNING diskpilot.scanner: atencao",
                "2026-11-18 15:19:20 ERROR diskpilot.index: falha",
            ],
            False,
        )

        document_text = page.terminal.document().toPlainText()
        assert document_text.count("\ufffc") == 3
        assert "\ufffc" not in page._plain_text
        assert "INFO" in page._plain_text
        assert "ERROR" in page._plain_text
    finally:
        page.close()
        state.shutdown()
