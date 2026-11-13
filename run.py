"""Ponto de entrada do DiskPilot."""

from __future__ import annotations

import ctypes
import logging
import sys
import traceback

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from app import APP_NAME, __version__
from app.config import AppConfig
from app.i18n import install_pt_br
from app.input_guard import CtrlWheelGuard
from app.logging_setup import configure_logging
from app.pages import default_pages
from app.shell import MainWindow
from app.single_instance import SingleInstanceGuard
from app.theme import init_theme


def _configure_logging(config: AppConfig) -> None:
    directory = configure_logging(config, stream=True)
    logging.getLogger("diskpilot").info("logs em %s", directory)


def _install_exception_hook() -> None:
    def hook(exc_type, exc_value, exc_tb):
        logging.critical("exceção não tratada", exc_info=(exc_type, exc_value, exc_tb))
        traceback.print_exception(exc_type, exc_value, exc_tb)

    sys.excepthook = hook


def _set_windows_app_id() -> None:
    if sys.platform.startswith("win"):
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "DiskPilot.StorageManager.1"
            )
        except Exception:
            pass


def main() -> int:
    _set_windows_app_id()
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setOrganizationName(APP_NAME)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setApplicationDisplayName(APP_NAME)

    install_pt_br(app)
    guard = SingleInstanceGuard(app)
    if not guard.acquire():
        return 0
    app.aboutToQuit.connect(guard.close)

    input_guard = CtrlWheelGuard(app)
    app.installEventFilter(input_guard)
    app.aboutToQuit.connect(input_guard.stop)

    config = AppConfig()
    _configure_logging(config)
    _install_exception_hook()
    logging.getLogger("diskpilot").info("iniciando %s %s", APP_NAME, __version__)
    theme = init_theme(app, config)
    window = MainWindow(config, theme, default_pages())
    guard.set_activation_callback(window.bring_to_front)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
