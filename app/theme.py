"""Gerenciador de temas (dark_cyan / light_cyan) e folha de estilo próprio.

O qt_material fornece a base (paleta, controles nativos), e o QSS abaixo
acrescenta a identidade visual do app: cards, botões com hover, árvore,
barra de título, abas e estados de foco. Nada de cores hardcoded nos widgets.
"""

from __future__ import annotations

import re
from pathlib import Path
from string import Template
from typing import Any

from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette
from PySide6.QtCore import QObject, QRect, Signal
from PySide6.QtWidgets import QApplication

try:  # qt_material precisa ser importado depois do Qt
    import qt_material as _qt_material
    from qt_material import apply_stylesheet  # noqa: F401  (compatibilidade)

    QT_MATERIAL_AVAILABLE = True
except Exception:  # pragma: no cover - fallback para ambientes sem a lib
    _qt_material = None
    QT_MATERIAL_AVAILABLE = False


def _rgba(hex_color: str, alpha: float) -> str:
    c = QColor(hex_color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha:.2f})"


PALETTES: dict[str, dict[str, Any]] = {
    "dark": {
        "bg": "#070f13",
        "window": "#0b161b",
        "sidebar": "#091419",
        "surface": "#0f1e24",
        "surface_2": "#14272f",
        "surface_3": "#1a323b",
        "border": "#1b333d",
        "border_strong": "#2a4d5a",
        "text": "#e9f7f9",
        "muted": "#8babb4",
        "faint": "#5f818b",
        "primary": "#21ccdc",
        "primary_hover": "#54e3f0",
        "primary_pressed": "#12b4c3",
        "on_primary": "#03252a",
        "success": "#43d99a",
        "warn": "#f0b74f",
        "danger": "#ff6b78",
        "info": "#59b8ff",
        "selection": "rgba(33, 204, 220, 0.18)",
        "tree_alt": "rgba(255, 255, 255, 0.018)",
        "shadow": "#000000",
        "charts": ["#21ccdc", "#4f9cf9", "#8b7cf6", "#43d99a", "#f0b74f", "#ff7b9c"],
    },
    "light": {
        "bg": "#dcecef",
        "window": "#f7fbfc",
        "sidebar": "#f0f8f9",
        "surface": "#ffffff",
        "surface_2": "#eef7f8",
        "surface_3": "#e2f0f2",
        "border": "#d3e5e9",
        "border_strong": "#b5d4da",
        "text": "#103039",
        "muted": "#5c7b84",
        "faint": "#88a2a9",
        "primary": "#008e9c",
        "primary_hover": "#00a8b8",
        "primary_pressed": "#007681",
        "on_primary": "#ffffff",
        "success": "#108a5b",
        "warn": "#b37400",
        "danger": "#d64550",
        "info": "#1478c9",
        "selection": "rgba(0, 142, 156, 0.14)",
        "tree_alt": "rgba(16, 48, 57, 0.025)",
        "shadow": "#5c7b84",
        "charts": ["#008e9c", "#2f7ed8", "#7059d6", "#108a5b", "#b37400", "#c94f76"],
    },
}


QSS_TEMPLATE = Template(
    """
* {
    font-family: "Segoe UI", "Noto Sans", sans-serif;
    font-size: 13px;
    color: $text;
    outline: none;
}
QWidget { background: transparent; }
QFrame { background: transparent; border: none; }
QMainWindow { background: transparent; }
QToolTip {
    background: $surface_2;
    color: $text;
    border: 1px solid $border_strong;
    border-radius: 6px;
    padding: 5px 8px;
}

/* ---------------------------------------------------------- janela */
QFrame#WindowShell {
    background: $window;
    border: 1px solid $border;
    border-radius: 16px;
}
QFrame#WindowShell[windowMaximized="true"] {
    border-radius: 0px;
    border: none;
}
QFrame#TitleBar {
    background: $window;
    border: none;
    border-bottom: 1px solid $border;
    border-top-left-radius: 16px;
    border-top-right-radius: 16px;
}
QFrame#TitleBar[windowMaximized="true"] {
    border-top-left-radius: 0px;
    border-top-right-radius: 0px;
}
QWidget#Sidebar {
    background: $sidebar;
    border: none;
    border-right: 1px solid $border;
    border-bottom-left-radius: 16px;
}
QWidget#Sidebar[windowMaximized="true"] { border-bottom-left-radius: 0px; }
QWidget#ContentArea { background: transparent; }
QLabel#AppTitle { font-size: 14px; font-weight: 600; }
QLabel#AppStatus { color: $muted; font-size: 12px; }

/* --------------------------------------------------------- botões */
QPushButton {
    text-transform: none;
    background: $surface_2;
    color: $text;
    border: 1px solid $border;
    border-radius: 9px;
    padding: 0px 14px;
    min-height: 34px;
}
QPushButton:hover { background: $surface_3; border-color: $border_strong; }
QPushButton:pressed { background: $surface; }
QPushButton:disabled { color: $faint; border-color: $border; background: $surface; }
QPushButton#Primary {
    background: $primary;
    color: $on_primary;
    border: 1px solid $primary;
    font-weight: 600;
    padding: 0px 16px;
    min-height: 36px;
}
QPushButton#Primary:hover { background: $primary_hover; border-color: $primary_hover; }
QPushButton#Primary:pressed { background: $primary_pressed; border-color: $primary_pressed; }
QPushButton#Primary:disabled { background: $surface_3; color: $faint; border-color: $border; }
QPushButton#Ghost {
    background: transparent;
    border: 1px solid $border_strong;
    color: $text;
    padding: 0px 14px;
    min-height: 34px;
}
QPushButton#Ghost:hover { background: $surface_2; border-color: $primary; color: $primary; }
QPushButton#Ghost:pressed { background: $surface; }
QPushButton#Soft {
    background: $surface_2;
    border: 1px solid $border;
    color: $text;
}
QPushButton#Soft:hover { background: $surface_3; border-color: $border_strong; }
QPushButton#DangerGhost {
    background: transparent;
    border: 1px solid $border_strong;
    color: $danger;
}
QPushButton#DangerGhost:hover { background: $surface_2; border-color: $danger; }
QPushButton#Link {
    background: transparent;
    border: none;
    color: $primary;
    padding: 2px 4px;
    min-height: 24px;
    text-align: left;
}
QPushButton#Link:hover { color: $primary_hover; text-decoration: underline; }
QPushButton#ThemeOption {
    background: $surface;
    border: 1px solid $border;
    border-radius: 11px;
    padding: 0px 14px;
    min-height: 52px;
    text-align: left;
    font-weight: 600;
}
QPushButton#ThemeOption:hover { border-color: $border_strong; background: $surface_2; }
QPushButton#ThemeOption:checked {
    background: $primary_soft;
    border: 1px solid $primary;
    color: $primary;
}
QPushButton#IconButton {
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 4px;
    min-height: 30px;
}
QPushButton#IconButton:hover { background: $surface_2; }
QPushButton#IconButton:pressed { background: $surface_3; }
QPushButton#IconButton:disabled { background: transparent; }
QPushButton#WindowButton {
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 0px;
    min-height: 0px;
}
QPushButton#WindowButton:hover { background: $surface_2; }
QPushButton#WindowButton:pressed { background: $surface_3; }
QPushButton#WindowClose {
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 0px;
    min-height: 0px;
}
QPushButton#WindowClose:hover { background: $danger; }
QPushButton#WindowClose:pressed { background: $danger; }
QPushButton#ChipClose {
    background: transparent;
    border: none;
    border-radius: 7px;
    padding: 0px;
    min-height: 0px;
}
QPushButton#ChipClose:hover { background: $danger_soft; }

/* --------------------------------------------------------- entradas */
QLineEdit {
    background: $surface;
    color: $text;
    border: 1px solid $border;
    border-radius: 9px;
    padding: 0px 10px;
    min-height: 36px;
    selection-background-color: $primary;
    selection-color: $on_primary;
}
QLineEdit:hover { border-color: $border_strong; }
QLineEdit:focus { border-color: $primary; background: $surface_2; }
QLineEdit:disabled { color: $faint; background: $surface; }
QLineEdit#Search {
    padding-left: 4px;
    min-height: 38px;
    background: $surface;
}
QLineEdit#Search:focus { background: $surface; }
QTextEdit, QPlainTextEdit {
    background: $surface;
    border: 1px solid $border;
    border-radius: 9px;
    padding: 8px;
    selection-background-color: $primary;
    selection-color: $on_primary;
}
QComboBox {
    background: $surface;
    border: 1px solid $border;
    border-radius: 9px;
    padding: 0px 28px 0px 12px;
    min-height: 36px;
}
QComboBox:hover { border-color: $border_strong; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox::down-arrow { image: none; width: 0px; height: 0px; }
QComboBox QAbstractItemView {
    background: $surface;
    border: 1px solid $border_strong;
    border-radius: 8px;
    padding: 4px;
    outline: none;
    selection-background-color: $selection;
    selection-color: $text;
}
QMenu {
    background: $surface;
    border: 1px solid $border_strong;
    border-radius: 10px;
    padding: 6px;
}
QMenu::item {
    background: transparent;
    padding: 7px 28px 7px 12px;
    border-radius: 6px;
    color: $text;
}
QMenu::item:selected { background: $primary_soft; color: $primary; }
QMenu::item:disabled { color: $faint; }
QMenu::separator { height: 1px; background: $border; margin: 5px 8px; }
QMenu::indicator { width: 0px; height: 0px; }
QCheckBox { spacing: 8px; color: $text; }
QCheckBox:checked { color: $text; }
QCheckBox::indicator {
    width: 17px; height: 17px; border-radius: 4px;
    border: 1px solid $border_strong; background: $surface;
}
QCheckBox::indicator:hover { border-color: $primary; }
QCheckBox::indicator:checked {
    background: $primary;
    border-color: $primary;
    image: url("$check_icon");
}

/* ------------------------------------------------------------ abas */
QLabel#PageTitle { font-size: 26px; font-weight: 700; letter-spacing: -0.5px; }
QLabel#PageSubtitle { color: $muted; font-size: 13px; }
QLabel#SectionTitle { font-size: 15px; font-weight: 600; letter-spacing: 0.1px; }
QLabel#Eyebrow {
    color: $primary;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.2px;
}
QLabel#Muted { color: $muted; }
QLabel#Faint { color: $faint; font-size: 12px; }
QLabel#Value { font-size: 23px; font-weight: 700; }
QLabel#ValueSmall { font-size: 17px; font-weight: 600; }
QLabel#Unit { color: $muted; font-size: 12px; font-weight: 500; }
QLabel#RowTitle { font-size: 13px; font-weight: 600; }
QLabel#RowSub { color: $muted; font-size: 11px; }
QLabel#RowValue { font-size: 13px; font-weight: 600; }
QLabel#InfoValue { color: $text; font-size: 12px; font-weight: 600; }
QLabel#InfoLabel { color: $muted; font-size: 12px; }
QLabel#HeroValue { font-size: 32px; font-weight: 700; letter-spacing: -0.8px; }
QLabel#HeroLabel { color: $muted; font-size: 11px; font-weight: 700; letter-spacing: 0.8px; }
QLabel#HeroSmall { color: $text; font-size: 17px; font-weight: 700; }

/* ---------------------------------------------------------- cards */
QFrame#Card {
    background: $surface;
    border: 1px solid $border;
    border-radius: 14px;
}
QFrame#Card:hover { border-color: $border_strong; }
QFrame#StatCard {
    background: $surface;
    border: 1px solid $border;
    border-radius: 14px;
}
QFrame#StatCard:hover { border-color: $border_strong; }
QFrame#HeroCard {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 $surface_2, stop:1 $surface);
    border: 1px solid $border_strong;
    border-radius: 16px;
}
QFrame#SuggestionCard {
    background: $surface;
    border: 1px solid $border;
    border-radius: 14px;
}
QFrame#SuggestionCard:hover { border-color: $border_strong; }
QFrame#EmptyCard {
    background: $surface;
    border: 1px dashed $border_strong;
    border-radius: 16px;
}
QFrame#IconTile {
    background: $primary_soft;
    border: none;
    border-radius: 11px;
}
QFrame#IconTileWarn { background: $warn_soft; border: none; border-radius: 11px; }
QFrame#IconTileDanger { background: $danger_soft; border: none; border-radius: 11px; }
QFrame#IconTileSuccess { background: $success_soft; border: none; border-radius: 11px; }
QFrame#Pill {
    background: $surface_2;
    border: 1px solid $border;
    border-radius: 10px;
}
QFrame#Pill:hover { border-color: $border_strong; }
QFrame#Toast {
    background: $surface_2;
    border: 1px solid $border_strong;
    border-radius: 11px;
}
QFrame#Divider { background: $border; border: none; max-height: 1px; min-height: 1px; }
QFrame#VSep { background: $border; border: none; max-width: 1px; min-width: 1px; }

QLabel#Badge, QLabel#BadgeSuccess, QLabel#BadgeWarn, QLabel#BadgeDanger, QLabel#BadgeInfo {
    border-radius: 8px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}
QLabel#Badge { background: $surface_3; color: $muted; }
QLabel#BadgeSuccess { background: $success_soft; color: $success; }
QLabel#BadgeWarn { background: $warn_soft; color: $warn; }
QLabel#BadgeDanger { background: $danger_soft; color: $danger; }
QLabel#BadgeInfo { background: $info_soft; color: $info; }

/* ------------------------------------------------------------ árvore */
QTreeWidget, QTreeView, QListWidget {
    background: $surface;
    alternate-background-color: $tree_alt;
    border: 1px solid $border;
    border-radius: 12px;
    padding: 2px;
    selection-background-color: $selection;
    selection-color: $text;
}
QTreeWidget::item, QTreeView::item { min-height: 33px; border: none; }
QTreeWidget::item:hover, QTreeView::item:hover { background: $surface_2; }
QTreeWidget::item:selected, QTreeView::item:selected {
    background: $selection;
    color: $text;
}
QTreeWidget::branch { background: transparent; }
QHeaderView { background: transparent; }
QHeaderView::section {
    background: $surface_2;
    color: $muted;
    border: none;
    border-bottom: 1px solid $border;
    padding: 7px 10px;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
}
QHeaderView::section:hover { color: $text; }
QListWidget { padding: 4px; }
QListWidget::item { padding: 6px 8px; border-radius: 6px; }

/* -------------------------------------------------------- progresso */
QProgressBar {
    background: $border;
    border: none;
    border-radius: 3px;
    max-height: 6px;
    min-height: 6px;
    text-align: center;
}
QProgressBar::chunk {
    background: $primary;
    border-radius: 3px;
}
QProgressBar#ScanBar {
    background: $surface_3;
    border-radius: 3px;
    max-height: 5px;
    min-height: 5px;
}
QProgressBar#ScanBar::chunk { background: $primary; border-radius: 3px; }

/* ------------------------------------------------------- scrollbars */
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: $border_strong;
    border-radius: 4px;
    min-height: 32px;
}
QScrollBar::handle:vertical:hover { background: $primary; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: $border_strong;
    border-radius: 4px;
    min-width: 32px;
}
QScrollBar::handle:horizontal:hover { background: $primary; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
QScrollArea { border: none; background: transparent; }

/* ---------------------------------------------------------- dialog */
QDialog { background: transparent; }
QFrame#DialogCard {
    background: $window;
    border: 1px solid $border_strong;
    border-radius: 16px;
}
QLabel#DialogTitle { font-size: 19px; font-weight: 700; }
QLabel#DialogSubtitle { color: $muted; font-size: 12px; }
QFrame#DialogHeader {
    background: transparent;
    border: none;
    border-bottom: 1px solid $border;
}
QFrame#DialogFooter {
    background: transparent;
    border: none;
    border-top: 1px solid $border;
}
QTreeView#FolderTree {
    background: $surface;
    border: 1px solid $border;
    border-radius: 10px;
}
QTreeView#FolderTree::item { min-height: 30px; }
QListWidget#QuickPlaces { background: transparent; border: none; border-radius: 0px; }
QListWidget#QuickPlaces::item { min-height: 32px; color: $muted; }
QListWidget#QuickPlaces::item:hover { background: $surface_2; color: $text; }
QListWidget#QuickPlaces::item:selected { background: $primary_soft; color: $primary; }

/* -------------------------------------------------------- diversos */
QLabel#PathText { color: $muted; font-size: 11px; }
QFrame#Chip {
    background: $surface_2;
    border: 1px solid $border;
    border-radius: 10px;
}
QLabel#ChipText { color: $text; font-size: 12px; }
QLabel#ChipClose { color: $muted; font-size: 14px; font-weight: 700; }
QLabel#ChipClose:hover { color: $danger; }
QFrame#ScanBanner {
    background: $primary_soft;
    border: 1px solid $primary_soft_strong;
    border-radius: 10px;
}
QLabel#ScanText { color: $primary; font-size: 12px; }
QFrame#InlineInfo {
    background: $surface_2;
    border: 1px solid $border;
    border-radius: 10px;
}
QFrame#TintSuccess { background: $success_soft; border: 1px solid $success_soft_strong; border-radius: 12px; }
QFrame#TintWarn { background: $warn_soft; border: 1px solid $warn_soft_strong; border-radius: 12px; }
QFrame#TintDanger { background: $danger_soft; border: 1px solid $danger_soft_strong; border-radius: 12px; }
QFrame#TintPrimary { background: $primary_soft; border: 1px solid $primary_soft_strong; border-radius: 12px; }
"""
)


class ThemeManager(QObject):
    aboutToChange = Signal(str)
    changed = Signal(str)

    def __init__(self, app: QApplication, config: Any | None = None) -> None:
        super().__init__()
        self.app = app
        self.config = config
        self.key = "dark"
        self.colors: dict[str, Any] = dict(PALETTES["dark"])
        self.font_scale = 1.0
        self._qss_cache: dict[tuple[str, float], str] = {}
        self._font_px: int | None = None
        self._build_derived("dark")

    def _compute_font_scale(self) -> float:
        """Escala as fontes conforme a altura útil da tela.

        O Qt já aplica o fator de DPI; aqui adicionamos um ajuste leve para
        telas maiores ficarem mais legíveis sem exagerar em notebooks.
        """
        screen = None
        if self.config is not None:
            geometry = self.config.get("geometry", None)
            if isinstance(geometry, (list, tuple)) and len(geometry) == 4:
                try:
                    saved = QRect(
                        int(geometry[0]),
                        int(geometry[1]),
                        int(geometry[2]),
                        int(geometry[3]),
                    )
                    screen = QGuiApplication.screenAt(saved.center())
                except (TypeError, ValueError):
                    screen = None
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return 1.15
        height = max(480, screen.availableGeometry().height())
        factor = 1.15 + 0.10 * ((height / 1080.0) - 1.0)
        return max(1.12, min(1.30, factor))

    def fs(self, size: int) -> int:
        """Converte um tamanho de fonte de projeto para o tamanho atual."""
        return max(9, int(round(size * self.font_scale)))

    # ------------------------------------------------------------ internos
    def _build_derived(self, key: str) -> None:
        base = dict(PALETTES[key])
        check_name = "check_dark.svg" if key == "dark" else "check_light.svg"
        check_icon = (Path(__file__).resolve().parent / "assets" / check_name).as_posix()
        base["check_icon"] = check_icon
        base["primary_soft"] = _rgba(base["primary"], 0.12)
        base["primary_soft_strong"] = _rgba(base["primary"], 0.30)
        base["success_soft"] = _rgba(base["success"], 0.12)
        base["success_soft_strong"] = _rgba(base["success"], 0.30)
        base["warn_soft"] = _rgba(base["warn"], 0.13)
        base["warn_soft_strong"] = _rgba(base["warn"], 0.30)
        base["danger_soft"] = _rgba(base["danger"], 0.12)
        base["danger_soft_strong"] = _rgba(base["danger"], 0.30)
        base["info_soft"] = _rgba(base["info"], 0.12)
        base["info_soft_strong"] = _rgba(base["info"], 0.30)
        self.colors = base

    def color(self, role: str, alpha: float | None = None) -> str:
        value = str(self.colors.get(role, role))
        if alpha is None:
            return value
        return _rgba(value, alpha)

    def qcolor(self, role: str, alpha: int | None = None) -> QColor:
        c = QColor(str(self.colors.get(role, "#ff00ff")))
        if alpha is not None:
            c.setAlpha(alpha)
        return c

    def chart_colors(self) -> list[str]:
        return list(self.colors.get("charts", []))

    # ------------------------------------------------------------- público
    def apply(self, key: str | None = None, persist: bool = True) -> None:
        if key is None:
            key = self.key
        key = "light" if str(key).lower() == "light" else "dark"
        self.key = key
        self._build_derived(key)
        self.font_scale = self._compute_font_scale()
        self.aboutToChange.emit(key)

        cache_key = (key, round(self.font_scale, 3))
        qss = self._qss_cache.get(cache_key)
        if qss is None:
            qss = self._build_qss(key)
            self._qss_cache[cache_key] = qss
        # Uma única aplicação: o Qt repolê a árvore inteira a cada chamada.
        self.app.setStyleSheet(qss)
        self._apply_palette()
        px = self.fs(13)
        if px != self._font_px:
            font = QFont("Segoe UI")
            font.setPixelSize(px)
            self.app.setFont(font)
            self._font_px = px
        if self.config is not None and persist:
            try:
                if self.config.get("theme") != key:
                    self.config.set("theme", key)
            except Exception:
                pass
        self.changed.emit(key)

    def _build_qss(self, key: str) -> str:
        """Monta a folha de estilo completa do tema (com cache por tema)."""
        base = ""
        if QT_MATERIAL_AVAILABLE and _qt_material is not None:
            try:
                # O app usa qtawesome. A geração de ícones do qt_material grava
                # centenas de SVG em ~/.qt_material a cada troca e é o que
                # tornava a troca de tema lenta em máquinas com antivírus.
                original = getattr(_qt_material, "set_icons_theme", None)
                _qt_material.set_icons_theme = lambda *a, **k: None
                try:
                    base = (
                        _qt_material.build_stylesheet(
                            f"{key}_cyan.xml",
                            invert_secondary=(key == "light"),
                            export=True,
                        )
                        or ""
                    )
                finally:
                    if original is not None:
                        _qt_material.set_icons_theme = original
            except Exception:
                base = ""
        qss = QSS_TEMPLATE.safe_substitute(**self.colors)
        qss = re.sub(
            r"font-size:\s*(\d+)px",
            lambda match: f"font-size: {self.fs(int(match.group(1)))}px",
            qss,
        )
        return base + "\n" + qss

    def prewarm(self) -> None:
        """Pré-monta o QSS do outro tema, para a primeira troca ser rápida."""
        other = "light" if self.key == "dark" else "dark"
        cache_key = (other, round(self.font_scale, 3))
        if cache_key in self._qss_cache:
            return
        current = self.key
        try:
            self._build_derived(other)
            self._qss_cache[cache_key] = self._build_qss(other)
        except Exception:
            pass
        finally:
            self._build_derived(current)

    def _apply_palette(self) -> None:
        c = self.colors
        pal = QPalette()
        pal.setColor(QPalette.Window, QColor(c["window"]))
        pal.setColor(QPalette.WindowText, QColor(c["text"]))
        pal.setColor(QPalette.Base, QColor(c["surface"]))
        pal.setColor(QPalette.AlternateBase, QColor(c["surface_2"]))
        pal.setColor(QPalette.Text, QColor(c["text"]))
        pal.setColor(QPalette.Button, QColor(c["surface_2"]))
        pal.setColor(QPalette.ButtonText, QColor(c["text"]))
        pal.setColor(QPalette.Highlight, QColor(c["primary"]))
        pal.setColor(QPalette.HighlightedText, QColor(c["on_primary"]))
        pal.setColor(QPalette.ToolTipBase, QColor(c["surface_2"]))
        pal.setColor(QPalette.ToolTipText, QColor(c["text"]))
        pal.setColor(QPalette.PlaceholderText, QColor(c["muted"]))
        self.app.setPalette(pal)

    def toggle(self) -> str:
        new_key = "light" if self.key == "dark" else "dark"
        self.apply(new_key)
        return new_key


_THEME: ThemeManager | None = None


def init_theme(app: QApplication, config: Any | None = None) -> ThemeManager:
    global _THEME
    if QT_MATERIAL_AVAILABLE and _qt_material is not None:
        try:
            app.setStyle("Fusion")
            # Carrega as fontes uma única vez; o build por tema usa export=True.
            _qt_material.add_fonts()
        except Exception:
            pass
    _THEME = ThemeManager(app, config)
    key = "dark"
    if config is not None:
        key = config.theme
    _THEME.apply(key, persist=False)
    return _THEME


def get_theme() -> ThemeManager:
    if _THEME is None:
        raise RuntimeError("init_theme() deve ser chamado após criar a QApplication")
    return _THEME
