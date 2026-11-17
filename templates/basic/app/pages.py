"""Registro das páginas do aplicativo."""

from __future__ import annotations

from appshell.pages import PageSpec

from .features.notes import NotesPage


def app_pages() -> list[PageSpec]:
    return [
        PageSpec(
            "notes",
            "Notas",
            "Exemplo de página com worker e persistência",
            "note-text-outline",
            NotesPage,
        ),
    ]
