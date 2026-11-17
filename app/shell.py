"""Composição do DiskPilot sobre o shell genérico de ``appshell``."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QDialog

from appshell.pages import PageSpec
from appshell.shell import ShellOptions, ShellWindow
from appshell.theme import ThemeManager
from appshell.widgets.common import Toast
from appshell.widgets.sidebar import Sidebar
from appshell.widgets.title_bar import TitleBar

from . import APP_NAME, APP_TAGLINE
from .config import AppConfig
from .services.state import AppState
from .widgets.dialogs import ProfileDialog


class MainWindow(ShellWindow):
    """Janela do DiskPilot: shell genérico + chrome e atalhos do domínio."""

    def __init__(
        self,
        config: AppConfig,
        theme: ThemeManager,
        page_specs: list[PageSpec],
        state: AppState | None = None,
    ) -> None:
        state = state if state is not None else AppState(config)
        assets = Path(__file__).resolve().parent / "assets"
        icon_path = assets / "app_icon.ico"
        if not icon_path.exists():
            icon_path = assets / "app_icon.svg"
        icon = QIcon(str(icon_path)) if icon_path.exists() else None
        super().__init__(
            config,
            theme,
            page_specs,
            state,
            options=ShellOptions(
                title=APP_NAME,
                tagline=APP_TAGLINE,
                icon=icon,
                primary_page="dashboard",
                accept_drops=True,
                shortcuts={
                    "Ctrl+O": self._shortcut_add,
                    "Ctrl+F": self._shortcut_search,
                    "Ctrl+R": self._shortcut_rescan,
                },
            ),
            title_bar_factory=lambda title, tagline, parent: TitleBar(
                title, tagline, parent
            ),
            sidebar_factory=lambda pages, parent: Sidebar(
                config,
                pages,
                parent,
                brand_title=APP_NAME,
                brand_tagline=APP_TAGLINE,
                brand_icon="harddisk",
            ),
            toast_factory=lambda parent: Toast(parent),
            profile_requested=self._edit_profile,
            identity_changed=self._refresh_settings_identity,
            close_requested=state.shutdown,
            drop_filter=self._directories_from_mime,
            drop_handler=self._add_dropped_paths,
        )

    # ------------------------------------------------------------- atalhos
    def _shortcut_add(self) -> None:
        self.navigate("analyzer")
        analyzer = self._pages.get("analyzer")
        if analyzer is not None and hasattr(analyzer, "add_folders"):
            QTimer.singleShot(30, analyzer.add_folders)

    def _shortcut_search(self) -> None:
        self.navigate("analyzer")
        analyzer = self._pages.get("analyzer")
        if analyzer is not None and hasattr(analyzer, "focus_search"):
            QTimer.singleShot(60, analyzer.focus_search)

    def _shortcut_rescan(self) -> None:
        if self.state.roots:
            self.navigate("analyzer")
            self.state.start_scan(force=True)
        else:
            self._shortcut_add()

    # ------------------------------------------------------------ identidade
    def _refresh_settings_identity(self) -> None:
        settings = self._pages.get("settings")
        if settings is not None and hasattr(settings, "_refresh_identity"):
            settings._refresh_identity()

    def _edit_profile(self) -> None:
        dialog = ProfileDialog(self, self.config)
        result = dialog.exec()
        dialog.deleteLater()
        if result == QDialog.Accepted:
            self._refresh_identity()
            self.show_toast("Perfil atualizado.", "success")

    # ----------------------------------------------------------- drag & drop
    def _directories_from_mime(self, mime) -> list[str]:
        paths: list[str] = []
        if not mime.hasUrls():
            return paths
        for url in mime.urls():
            if not url.isLocalFile():
                continue
            path = url.toLocalFile()
            if os.path.isdir(path):
                paths.append(path)
        return paths

    def _add_dropped_paths(self, paths: list[str]) -> None:
        added = self.state.add_roots(paths, autoscan=True)
        self.navigate("analyzer")
        if added:
            noun = "pasta adicionada" if len(added) == 1 else "pastas adicionadas"
            self.show_toast(f"{len(added)} {noun}. Iniciando análise…", "info")
        else:
            self.show_toast("As pastas arrastadas já estão na análise.", "info")
