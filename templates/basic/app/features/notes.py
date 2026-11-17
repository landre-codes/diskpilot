"""Página de exemplo: lista de notas com carga em segundo plano."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QVBoxLayout,
)

from appshell.pages import BasePage
from appshell.tasks import Task, TaskRunner
from appshell.widgets.buttons import ActionButton
from appshell.widgets.common import Card, PageHeader


class _LoadNotesTask(Task):
    def __init__(self, notes: list[str]) -> None:
        super().__init__()
        self._notes = list(notes)

    def execute(self) -> list[str]:
        return list(self._notes)


class NotesPage(BasePage):
    page_id = "notes"
    page_title = "Notas"
    page_subtitle = "Exemplo de página com worker e persistência local"
    page_icon = "note-text-outline"

    def __init__(self, state) -> None:
        super().__init__(state)
        self._loaded = False
        self._runner = TaskRunner(self)
        self._runner.finished.connect(self._show_notes)
        self._runner.failed.connect(self._show_error)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)
        root.addWidget(PageHeader(self.page_title, self.page_subtitle, "EXEMPLO"))

        card = Card("Suas notas", "Os dados ficam no config.json do usuário.")
        row = QHBoxLayout()
        row.setSpacing(8)
        self.input = QLineEdit(self)
        self.input.setPlaceholderText("Escreva uma nota e pressione Enter…")
        self.input.returnPressed.connect(self._add_note)
        self.add_btn = ActionButton("Adicionar", "plus", "primary", self)
        self.add_btn.clicked.connect(self._add_note)
        row.addWidget(self.input, 1)
        row.addWidget(self.add_btn)
        card.body.addLayout(row)

        self.list = QListWidget(self)
        self.list.setAlternatingRowColors(True)
        card.body.addWidget(self.list, 1)
        root.addWidget(card, 1)

        notes = self.state.config.get("notes", [])
        self._runner.submit(_LoadNotesTask(notes if isinstance(notes, list) else []))

    def on_show(self) -> None:
        self.input.setFocus()

    def _show_notes(self, notes: list[str]) -> None:
        self.list.clear()
        self.list.addItems([str(note) for note in notes])
        self._loaded = True

    def _show_error(self, message: str) -> None:
        self._loaded = True
        self.toast(message or "Falha ao carregar as notas.", "danger")

    def _add_note(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        notes = self.state.config.get("notes", [])
        if not isinstance(notes, list):
            notes = []
        updated = [*notes, text]
        self.state.config.set("notes", updated)
        self.list.addItem(text)
        self.input.clear()
        self.toast("Nota adicionada.", "success")
