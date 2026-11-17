from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QLabel

from app.config import AppConfig
from app.pages import default_pages
from app.shell import MainWindow
from app.theme import init_theme
from appshell.pages import BasePage, PageSpec


class _SamplePage(BasePage):
    def __init__(self, state) -> None:
        super().__init__(state)
        layout = QLabel("conteúdo", self)
        layout.move(20, 20)


def _config(tmp_path: Path) -> AppConfig:
    return AppConfig(tmp_path / "config")


def test_main_window_builds_and_navigates(qapp, qtbot, tmp_path: Path) -> None:
    config = _config(tmp_path)
    theme = init_theme(qapp, config)
    pages = [
        PageSpec("inicio", "Início", "Página inicial", "home", _SamplePage),
        PageSpec("dados", "Dados", "Dados de exemplo", "database", _SamplePage),
    ]

    window = MainWindow(config, theme, pages)
    qtbot.addWidget(window)
    window.show()
    qtbot.wait(10)

    assert window._current_key == "inicio"
    window.navigate("dados", animate=False)
    assert window._current_key == "dados"
    assert window.stack.currentWidget() is window._pages["dados"]
    window.close()


def test_default_pages_are_registered(qapp, qtbot, tmp_path: Path) -> None:
    config = _config(tmp_path)
    init_theme(qapp, config)
    pages = default_pages()

    assert [spec.key for spec in pages] == [
        "dashboard",
        "analyzer",
        "recommendations",
        "logs",
        "settings",
    ]
