from __future__ import annotations

from pathlib import Path

from app.context import AppContext
from app.features.notes import NotesPage
from appshell.config import JsonSettings
from appshell.theme import init_theme


def test_notes_page_loads_and_persists(qapp, qtbot, tmp_path: Path) -> None:
    config = JsonSettings(tmp_path / "config", defaults={"notes": ["inicial"]})
    init_theme(qapp, config)
    page = NotesPage(AppContext(config))
    qtbot.addWidget(page)
    page.show()
    qtbot.waitUntil(lambda: page._loaded, timeout=3000)

    assert page.list.count() == 1
    page.input.setText("segunda nota")
    page._add_note()

    assert page.list.count() == 2
    assert config.get("notes") == ["inicial", "segunda nota"]
