"""Diagnóstico de ambiente e de geometria da janela.

Uso:
    py diagnostico.py

Gera ``diagnostico-diskpilot.txt`` ao lado deste arquivo (e imprime na tela).
Nenhum arquivo do usuário é lido ou alterado.
"""

from __future__ import annotations

import platform
import sys
import tempfile
from pathlib import Path

from PySide6 import __version__ as pyside_version
from PySide6.QtCore import QRect, QTimer, qVersion
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

LINHAS: list[str] = []


def linha(texto: str = "") -> None:
    LINHAS.append(texto)
    print(texto, flush=True)


def main() -> int:
    from app import APP_NAME, __version__ as app_version
    from app.config import AppConfig
    from app.pages import default_pages
    from app.shell import MainWindow
    from app.theme import init_theme

    linha("DiskPilot — diagnóstico")
    linha("=" * 60)
    linha(f"Python           : {sys.version.split()[0]} ({platform.machine()})")
    linha(f"Executável       : {sys.executable}")
    linha(f"SO               : {platform.platform()}")
    linha(f"PySide6          : {pyside_version}")
    linha(f"Qt               : {qVersion()}")
    linha(f"DiskPilot        : {app_version}")
    linha()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)

    screen = QGuiApplication.primaryScreen()
    if screen is not None:
        geo = screen.geometry()
        avail = screen.availableGeometry()
        linha(f"Tela primária    : {screen.name()}")
        linha(f"  geometry       : {geo.getRect()}")
        linha(f"  available      : {avail.getRect()}")
        linha(f"  devicePixelRatio: {screen.devicePixelRatio():.3f}")
        linha(f"  logicalDpi     : {screen.logicalDotsPerInch():.2f}")
        linha(f"  physicalDpi    : {screen.physicalDotsPerInch():.2f}")
        min_w, min_h = MainWindow._screen_limits(avail)
        padrao = MainWindow._default_geometry(avail)
        linha(f"  mínimo calculado: {min_w}x{min_h}")
        linha(f"  tamanho padrão  : {padrao.getRect()}")
    for extra in QGuiApplication.screens()[1:]:
        linha(f"Tela extra       : {extra.name()} {extra.geometry().getRect()} dpr={extra.devicePixelRatio():.2f}")
    linha()

    cfg = AppConfig(Path(tempfile.mkdtemp()) / ".diagnostico-config")
    theme = init_theme(app, cfg)
    win = MainWindow(cfg, theme, default_pages())
    win.show()

    resultado: list[str] = []

    def registrar(etapa: str) -> None:
        avail = win.screen().availableGeometry() if win.screen() else QRect()
        geo = win.geometry()
        dentro = avail.contains(geo) if not avail.isNull() else False
        resultado.append(
            f"{etapa:24s} geometria={geo.getRect()} dentro_da_tela={dentro} "
            f"maximizado={win._maximized}"
        )

    def etapa1() -> None:
        registrar("após show")
        win.title_bar.maximize_button.click()

    def etapa2() -> None:
        registrar("após maximizar")
        win.title_bar.maximize_button.click()

    def etapa3() -> None:
        registrar("após restaurar (1)")
        win.title_bar.maximize_button.click()

    def etapa4() -> None:
        registrar("após maximizar (2)")
        win.title_bar.maximize_button.click()

    def etapa5() -> None:
        registrar("após restaurar (2)")
        QTimer.singleShot(600, finalizar)

    def finalizar() -> None:
        registrar("estado final")
        linha("Ciclo da janela")
        linha("-" * 60)
        for item in resultado:
            linha("  " + item)
        win.close()
        destino = ROOT / "diagnostico-diskpilot.txt"
        try:
            destino.write_text("\n".join(LINHAS) + "\n", encoding="utf-8")
            linha()
            linha(f"Relatório salvo em: {destino}")
        except Exception as exc:  # pragma: no cover
            linha(f"Não foi possível salvar o relatório: {exc}")
        app.quit()

    QTimer.singleShot(700, etapa1)
    QTimer.singleShot(1100, etapa2)
    QTimer.singleShot(1500, etapa3)
    QTimer.singleShot(1900, etapa4)
    QTimer.singleShot(2300, etapa5)
    app.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
