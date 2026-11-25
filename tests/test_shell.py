from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel

from app import APP_AUTHOR, APP_COPYRIGHT
from app.config import AppConfig
from app.features.analyzer.page import AnalyzerPage
from app.pages import default_pages
from app.services.model import ScanResult, ScanWarning
from app.services.state import AppState
from app.shell import MainWindow
from appshell.theme import init_theme
from appshell.widgets.sidebar import Sidebar
from appshell.pages import BasePage, PageSpec
from appshell.widgets.common import Chip


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

    assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert window.windowTitle() == "DiskPilot"
    assert window._current_key == "inicio"
    window.navigate("dados", animate=False)
    assert window._current_key == "dados"
    assert window.stack.currentWidget() is window._pages["dados"]
    window.close()


def test_first_show_reveals_window(qapp, qtbot, tmp_path: Path) -> None:
    config = _config(tmp_path)
    theme = init_theme(qapp, config)
    pages = [
        PageSpec("inicio", "Início", "Página inicial", "home", _SamplePage),
    ]
    window = MainWindow(config, theme, pages)
    qtbot.addWidget(window)
    initial = window.windowOpacity()
    window.show()
    if initial < 1.0:
        qtbot.waitUntil(lambda: window.windowOpacity() >= 0.99, timeout=2000)
    window.close()


def test_smooth_minimize_fades_and_restores(qapp, qtbot, tmp_path: Path) -> None:
    config = _config(tmp_path)
    theme = init_theme(qapp, config)
    pages = [
        PageSpec("inicio", "Início", "Página inicial", "home", _SamplePage),
    ]
    window = MainWindow(config, theme, pages)
    qtbot.addWidget(window)
    window.show()
    qtbot.wait(20)

    window.minimize_smooth()
    qtbot.wait(300)

    assert window.isMinimized()
    assert window.windowOpacity() == pytest.approx(1.0)

    window.showNormal()
    qtbot.wait(300)

    assert not window.isMinimized()
    assert window.windowOpacity() == pytest.approx(1.0)
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


def test_chip_shows_folder_name_and_full_path_tooltip(qapp) -> None:
    path = r"C:\dados\clientes_2026"
    chip = Chip(path, label="clientes_2026")

    assert chip.label.full_text() == "clientes_2026"
    assert chip.toolTip() == path


def test_rescan_requires_confirmation_while_scanning(
    qapp, tmp_path: Path, monkeypatch
) -> None:
    config = _config(tmp_path)
    init_theme(qapp, config)
    state = AppState(config)
    state.roots = [str(tmp_path)]
    state.is_scanning = True
    page = AnalyzerPage(state)
    page.toast = lambda *args, **kwargs: None
    calls = []
    monkeypatch.setattr(state, "start_scan", lambda **kwargs: calls.append(kwargs))
    answers = [QDialog.Rejected, QDialog.Accepted]

    class _Confirm:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def exec(self) -> int:
            return answers.pop(0)

        def deleteLater(self) -> None:
            pass

    monkeypatch.setattr("app.features.analyzer.page.ConfirmDialog", _Confirm)

    page._rescan()
    assert calls == []

    page._rescan()
    assert calls == [{"force": True}]
    state.shutdown()


def test_sidebar_shows_developer_credit(qapp, tmp_path: Path) -> None:
    config = _config(tmp_path)
    sidebar = Sidebar(
        config,
        [],
        brand_title="DiskPilot",
        brand_tagline="Gestor de espaço",
        brand_author=APP_AUTHOR,
        brand_credit=APP_COPYRIGHT,
        brand_icon="harddisk",
    )

    assert APP_AUTHOR == "Landre Codes"
    assert sidebar.author.text() == "© 2026 Landre Codes"
    assert APP_AUTHOR in sidebar.author.toolTip()
    assert APP_AUTHOR in sidebar.author.accessibleName()


def test_analyzer_shows_warning_action_and_memory_search_status(
    qapp, qtbot, tmp_path: Path
) -> None:
    config = _config(tmp_path)
    init_theme(qapp, config)
    state = AppState(config)
    state.roots = [str(tmp_path)]
    state.last_result = ScanResult(
        roots=[],
        total_size=10,
        total_files=1,
        total_dirs=1,
        errors=2,
        warnings=[ScanWarning("list_dir", "permission_denied", 2)],
    )
    page = AnalyzerPage(state)
    qtbot.addWidget(page)

    assert page.limit_banner.objectName() == "TintWarn"
    assert "memória RAM" in page.limit_banner.label.text()
    assert "entradas" in page.limit_banner.label.text()

    page._update_header()

    assert page.warnings_btn.isHidden() is False
    assert "2 avisos — ver detalhes" in page.warnings_btn.toolTip()
    page._on_search_index_failed("duplicate_path")
    assert "busca em memória" in page.header.subtitle.text()
    assert "mais lenta" in page.header.subtitle.toolTip()

    page.banner.show()
    page._on_results_cleared()
    assert page.banner.isHidden()
    state.shutdown()


def test_initial_focus_does_not_highlight_title_bar_menu(
    qapp, qtbot, tmp_path: Path
) -> None:
    config = _config(tmp_path)
    theme = init_theme(qapp, config)
    state = AppState(config)
    window = MainWindow(config, theme, default_pages(), state=state)
    qtbot.addWidget(window)
    window.show()
    qtbot.wait(30)

    assert window.title_bar.menu_button.hasFocus() is False
    window.close()
    state.shutdown()
