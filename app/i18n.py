"""Internacionalização: pt_BR para os componentes nativos do Qt."""

from __future__ import annotations

from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
from PySide6.QtWidgets import QApplication


def install_pt_br(app: QApplication) -> list[QTranslator]:
    """Define pt_BR como locale padrão e carrega os tradutores do Qt.

    As strings próprias do DiskPilot já são escritas em português. O
    QTranslator cobre menus de contexto, diálogos internos do Qt, botões
    padrão, calendário, seletores de arquivo não nativos etc.
    """
    QLocale.setDefault(QLocale("pt_BR"))
    app.setLayoutDirection(QLocale("pt_BR").textDirection())

    translations_path = QLibraryInfo.path(QLibraryInfo.TranslationsPath)
    loaded: list[QTranslator] = []
    for name in ("qtbase_pt_BR", "qt_pt_BR"):
        translator = QTranslator(app)
        if translator.load(name, translations_path):
            app.installTranslator(translator)
            loaded.append(translator)
    return loaded
