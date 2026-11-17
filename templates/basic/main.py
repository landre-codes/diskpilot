"""{{ project_name }} — aplicação de exemplo sobre o appshell."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from app import APP_NAME, __version__
from app.context import AppContext
from app.pages import app_pages
from appshell.config import JsonSettings
from appshell.shell import ShellOptions, ShellWindow
from appshell.theme import init_theme
from appshell.widgets.common import Toast
from appshell.widgets.sidebar import Sidebar
from appshell.widgets.title_bar import TitleBar


def main() -> int:
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setOrganizationName(APP_NAME)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)

    config = JsonSettings(
        defaults={"notes": []},
        fallback_name="{{ project_slug }}",
    )
    theme = init_theme(app, config)
    context = AppContext(config)

    window = ShellWindow(
        config,
        theme,
        app_pages(),
        context,
        options=ShellOptions(
            title=APP_NAME,
            tagline="{{ tagline }}",
            primary_page="notes",
        ),
        title_bar_factory=lambda title, tagline, parent: TitleBar(
            title, tagline, parent
        ),
        sidebar_factory=lambda pages, parent: Sidebar(
            config,
            pages,
            parent,
            brand_title=APP_NAME,
            brand_tagline="{{ tagline }}",
            brand_icon="note-text-outline",
        ),
        toast_factory=lambda parent: Toast(parent),
        close_requested=context.shutdown,
    )
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
