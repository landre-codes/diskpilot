"""Ponto de entrada do DiskPilot."""

from __future__ import annotations

import ctypes
import faulthandler
import logging
import logging.handlers
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from app import APP_NAME, __version__
from app.config import AppConfig
from app.i18n import install_pt_br
from app.input_guard import CtrlWheelGuard
from app.pages import default_pages
from app.shell import MainWindow
from app.single_instance import SingleInstanceGuard
from app.theme import init_theme


_CRASH_FILE = None


def _configure_logging(config: AppConfig) -> None:
    global _CRASH_FILE
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    paths: list[Path] = []
    for candidate in (
        config.path.parent / "diskpilot.log",
        Path(__file__).resolve().parent / "diskpilot.log",
    ):
        if candidate not in paths:
            paths.append(candidate)
    for log_path in paths:
        try:
            handler = logging.handlers.RotatingFileHandler(
                log_path, maxBytes=1_000_000, backupCount=2, encoding="utf-8"
            )
            handler.setFormatter(formatter)
            root.addHandler(handler)
        except Exception:
            continue
    try:
        stream = logging.StreamHandler()
        stream.setFormatter(formatter)
        root.addHandler(stream)
    except Exception:
        pass

    # faulthandler captura abortos nativos e grava o stack Python no crash log.
    for crash_path in (
        Path(__file__).resolve().parent / "diskpilot-crash.log",
        config.path.parent / "diskpilot-crash.log",
    ):
        try:
            _CRASH_FILE = open(crash_path, "a", encoding="utf-8", buffering=1)
            faulthandler.enable(file=_CRASH_FILE, all_threads=True)
            break
        except Exception:
            _CRASH_FILE = None
            continue


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
