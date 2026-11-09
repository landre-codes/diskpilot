"""Diálogos do shell: seletor múltiplo de pastas e edição de perfil."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from PySide6.QtCore import QDir, QEvent, QModelIndex, QPoint, QStandardPaths, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QFileDialog,
    QFileSystemModel,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QToolTip,
    QTreeView,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..config import AppConfig
from ..icons import avatar_pixmap, circular_pixmap, icon
from ..services.exporter import (
    default_export_path,
    write_csv,
    write_xlsb,
    write_xlsx,
)
from ..services.model import ScanResult, top_items
from ..theme import get_theme
from ..utils import format_bytes, normalize_path, open_in_explorer, resolve_network_path
from .buttons import ActionButton, IconButton, SelectButton


class _DialogHeader(QFrame):
    def __init__(self, title: str, subtitle: str, dialog: QDialog) -> None:
        super().__init__(dialog)
        self.setObjectName("DialogHeader")
        self._dialog = dialog
        self._drag_offset = QPoint()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 14, 10, 14)
        lay.setSpacing(10)
        texts = QVBoxLayout()
        texts.setContentsMargins(0, 0, 0, 0)
        texts.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("DialogTitle")
        t.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        texts.addWidget(t)
        s = QLabel(subtitle)
        s.setObjectName("DialogSubtitle")
        s.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        texts.addWidget(s)
        lay.addLayout(texts, 1)
        close = IconButton("close", "Fechar", self, 17, 30, "danger")
        close.clicked.connect(dialog.reject)
        lay.addWidget(close)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint()
                - self._dialog.frameGeometry().topLeft()
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if event.buttons() & Qt.LeftButton and not self._drag_offset.isNull():
            self._dialog.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_offset = QPoint()
        super().mouseReleaseEvent(event)


class SheetDialog(QDialog):
    """Modal sem moldura do sistema, com card, sombra e arraste."""

    def __init__(
        self,
        parent: QWidget | None,
        title: str,
        subtitle: str = "",
        width: int = 860,
        height: int = 600,
    ) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self.setWindowModality(Qt.ApplicationModal)
        screen = parent.screen() if parent is not None else QGuiApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else None
        max_w = available.width() - 60 if available is not None else 1200
        max_h = available.height() - 60 if available is not None else 800
        self._width = max(420, min(width, max_w))
        self._height = max(260, min(height, max_h))
        self.setFixedSize(self._width + 36, self._height + 36)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)
        self.card = QFrame(self)
        self.card.setObjectName("DialogCard")
        outer.addWidget(self.card)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(38)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 130))
        self.card.setGraphicsEffect(shadow)
        root = QVBoxLayout(self.card)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.header = _DialogHeader(title, subtitle, self)
        root.addWidget(self.header)
        self.body = QVBoxLayout()
        self.body.setContentsMargins(20, 16, 20, 16)
        self.body.setSpacing(12)
        root.addLayout(self.body, 1)
        self.footer = QHBoxLayout()
        self.footer.setContentsMargins(20, 12, 20, 14)
        self.footer.setSpacing(8)
        foot = QFrame(self)
        foot.setObjectName("DialogFooter")
        foot.setLayout(self.footer)
        root.addWidget(foot)
        self._footer_frame = foot

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        parent = self.parentWidget()
        if parent:
            center = parent.window().frameGeometry().center()
            self.move(center - self.rect().center())
        else:
            screen = self.screen()
            if screen:
                self.move(screen.availableGeometry().center() - self.rect().center())
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            x = max(available.left() + 8, min(self.x(), available.right() - self.width() - 8))
            y = max(available.top() + 8, min(self.y(), available.bottom() - self.height() - 8))
            self.move(x, y)
        self.raise_()
        self.activateWindow()


class FolderPickerDialog(SheetDialog):
    """Seleção de uma ou várias pastas com navegação e atalhos."""

    def __init__(self, parent: QWidget | None, start_path: str = "") -> None:
        super().__init__(
            parent,
            "Adicionar pastas",
            "Escolha uma ou mais pastas na lista ou clique em “Adicionar esta pasta”. A análise é somente leitura.",
            920,
            610,
        )
        self._current_only = False
        self._current = start_path or QStandardPaths.writableLocation(
            QStandardPaths.HomeLocation
        )
        if not self._current or not Path(self._current).exists():
            self._current = str(Path.home())

        work = QHBoxLayout()
        work.setSpacing(14)
        self.body.addLayout(work, 1)

        # Atalhos ---------------------------------------------------------
        left = QVBoxLayout()
        left.setSpacing(6)
        left_title = QLabel("LOCAIS")
        left_title.setObjectName("Eyebrow")
        left.addWidget(left_title)
        self.places = QListWidget(self)
        self.places.setObjectName("QuickPlaces")
        self.places.setFixedWidth(230)
        left.addWidget(self.places, 1)
        work.addLayout(left)

        # Navegador -------------------------------------------------------
        right = QVBoxLayout()
        right.setSpacing(9)
        nav = QHBoxLayout()
        nav.setSpacing(6)
        self.up_btn = IconButton("arrow-up", "Subir um nível", self, 17, 32, "primary")
        self.up_btn.clicked.connect(self._go_up)
        nav.addWidget(self.up_btn)
        self.path_edit = QLineEdit(self)
        self.path_edit.setPlaceholderText("Caminho da pasta")
        self._path_action = self.path_edit.addAction(
            icon("folder-open-outline", get_theme().color("muted"), 16),
            QLineEdit.LeadingPosition,
        )
        self.path_edit.returnPressed.connect(self._go_typed)
        nav.addWidget(self.path_edit, 1)
        go = ActionButton("Ir", "arrow-right", "soft", self, 16)
        go.clicked.connect(self._go_typed)
        nav.addWidget(go)
        right.addLayout(nav)

        self.model = QFileSystemModel(self)
        self.model.setFilter(
            QDir.AllDirs | QDir.NoDotAndDotDot | QDir.Drives | QDir.Hidden
        )
        self.model.setRootPath(QDir.rootPath())
        self.tree = QTreeView(self)
        self.tree.setObjectName("FolderTree")
        self.tree.setModel(self.model)
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for column in (1, 2, 3):
            self.tree.setColumnHidden(column, True)
        self.tree.setColumnWidth(0, 560)
        self.tree.doubleClicked.connect(self._enter_index)
        right.addWidget(self.tree, 1)
        self.full_path_caption = QLabel("CAMINHO COMPLETO")
        self.full_path_caption.setObjectName("Eyebrow")
        right.addWidget(self.full_path_caption)
        path_row = QHBoxLayout()
        path_row.setSpacing(6)
        self.full_path_label = QLabel("")
        self.full_path_label.setObjectName("PathText")
        self.full_path_label.setWordWrap(True)
        self.full_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._full_path_value = ""
        path_row.addWidget(self.full_path_label, 1)
        self.copy_path_btn = IconButton(
            "content-copy", "Copiar caminho completo", self, 15, 28, "primary"
        )
        self.copy_path_btn.clicked.connect(self._copy_full_path)
        path_row.addWidget(self.copy_path_btn, 0, Qt.AlignTop)
        right.addLayout(path_row)
        self.tree.viewport().installEventFilter(self)
        hint = QLabel(
            "Dica: use Ctrl+clique para marcar várias pastas · duplo clique abre uma pasta"
        )
        hint.setObjectName("Faint")
        right.addWidget(hint)
        work.addLayout(right, 1)

        self.body.addStretch(0)
        self.add_current_btn = ActionButton(
            "Adicionar esta pasta", "folder-plus-outline", "soft", self, 16
        )
        self.add_current_btn.clicked.connect(self._accept_current)
        self.footer.addWidget(self.add_current_btn)
        self.selection_label = QLabel("Nenhuma pasta selecionada")
        self.selection_label.setObjectName("Muted")
        self.footer.addWidget(self.selection_label)
        self.footer.addStretch(1)
        cancel = ActionButton("Cancelar", "", "ghost", self)
        cancel.clicked.connect(self.reject)
        self.footer.addWidget(cancel)
        self.add_btn = ActionButton("Adicionar", "folder-plus-outline", "primary", self)
        self.add_btn.clicked.connect(self.accept)
        self.footer.addWidget(self.add_btn)

        self._populate_places()
        self.places.itemClicked.connect(self._place_clicked)
        self._navigate(self._current)
        self.tree.selectionModel().selectionChanged.connect(self._update_selection_label)
        get_theme().changed.connect(self._sync_icons)
        self._sync_icons()

    # ------------------------------------------------------------ localidades
    def _populate_places(self) -> None:
        self.places.clear()
        theme = get_theme()
        locations = [
            ("Início", QStandardPaths.writableLocation(QStandardPaths.HomeLocation)),
            (
                "Área de trabalho",
                QStandardPaths.writableLocation(QStandardPaths.DesktopLocation),
            ),
            (
                "Documentos",
                QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation),
            ),
            (
                "Downloads",
                QStandardPaths.writableLocation(QStandardPaths.DownloadLocation),
            ),
        ]
        seen: set[str] = set()
        for label, path in locations:
            if path and Path(path).exists():
                key = os.path.normcase(path)
                if key in seen:
                    continue
                seen.add(key)
                item = QListWidgetItem(icon("folder", theme.color("muted"), 16), label)
                item.setToolTip(path)
                item.setData(Qt.UserRole, path)
                self.places.addItem(item)
        for drive in QDir.drives():
            path = drive.absolutePath()
            resolved = resolve_network_path(path)
            key = os.path.normcase(resolved)
            if key in seen:
                continue
            seen.add(key)
            network = resolved.startswith("\\\\")
            item = QListWidgetItem(
                icon(
                    "server-network" if network else "harddisk",
                    theme.color("muted"),
                    16,
                ),
                resolved if network else path,
            )
            item.setToolTip(resolved if network else path)
            item.setData(Qt.UserRole, resolved)
            self.places.addItem(item)

    def _place_clicked(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.UserRole)
        if path:
            self._navigate(str(path))

    def _sync_icons(self, *_args: Any) -> None:
        theme = get_theme()
        self._path_action.setIcon(icon("folder-open-outline", theme.color("muted"), 16))
        for i in range(self.places.count()):
            item = self.places.item(i)
            path = str(item.data(Qt.UserRole) or "")
            if path.startswith("\\\\"):
                md = "server-network"
            elif len(path) <= 3:
                md = "harddisk"
            else:
                md = "folder"
            item.setIcon(icon(md, theme.color("muted"), 16))
            if os.path.normcase(path) == os.path.normcase(self._current):
                self.places.setCurrentItem(item)

    # ------------------------------------------------------------- navegação
    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self.tree.viewport() and event.type() == QEvent.ToolTip:
            index = self.tree.indexAt(event.pos())
            if index.isValid():
                path = self.model.filePath(index)
                if path:
                    QToolTip.showText(event.globalPos(), path, self.tree)
                    return True
        return super().eventFilter(obj, event)

    def _navigate(self, path: str) -> None:
        path = resolve_network_path(normalize_path(path))
        if not Path(path).exists() or not Path(path).is_dir():
            return
        self._current = path
        self.path_edit.setText(path)
        self.path_edit.setToolTip(path)
        if hasattr(self, "add_current_btn"):
            self.add_current_btn.setToolTip(f"Adicionar a pasta exibida: {path}")
        index = self.model.index(path)
        if index.isValid():
            self.tree.setRootIndex(index)
            self.tree.clearSelection()
            self._update_selection_label()
        self._update_full_path()
        self.up_btn.setEnabled(Path(path).parent != Path(path))

    def _go_up(self) -> None:
        parent = str(Path(self._current).parent)
        if os.path.normcase(parent) != os.path.normcase(self._current):
            self._navigate(parent)

    def _go_typed(self) -> None:
        self._navigate(self.path_edit.text().strip().strip('"'))

    def _enter_index(self, index: QModelIndex) -> None:
        path = self.model.filePath(index)
        if Path(path).is_dir():
            self._navigate(path)

    # ------------------------------------------------------------- seleção
    def _selected_rows(self) -> list[str]:
        model = self.tree.selectionModel()
        if model is None:
            return []
        paths: list[str] = []
        for index in model.selectedRows(0):
            path = self.model.filePath(index)
            if Path(path).is_dir():
                paths.append(normalize_path(path))
        return paths

    def selected_paths(self) -> list[str]:
        if self._current_only:
            return [normalize_path(self._current)]
        paths = self._selected_rows()
        seen: set[str] = set()
        unique: list[str] = []
        for path in paths:
            key = os.path.normcase(path)
            if key not in seen:
                seen.add(key)
                unique.append(path)
        return unique

    def _accept_current(self) -> None:
        self._current_only = True
        self.accept()

    def _update_full_path(self) -> None:
        if not hasattr(self, "full_path_label"):
            return
        selected = self._selected_rows()
        if len(selected) == 1:
            self.full_path_caption.setText("CAMINHO SELECIONADO")
            self._full_path_value = selected[0]
            text = selected[0]
        else:
            self.full_path_caption.setText("CAMINHO COMPLETO")
            self._full_path_value = self._current
            text = self._current
            if len(selected) > 1:
                text = f"{text}  ·  {len(selected)} pastas selecionadas"
        self.full_path_label.setText(text)
        self.full_path_label.setToolTip(self._full_path_value)

    def _copy_full_path(self) -> None:
        if not self._full_path_value:
            return
        QApplication.clipboard().setText(self._full_path_value)
        QToolTip.showText(
            self.copy_path_btn.mapToGlobal(self.copy_path_btn.rect().bottomLeft()),
            "Caminho copiado.",
            self.copy_path_btn,
        )

    def _update_selection_label(self, *_args: Any) -> None:
        count = len(self._selected_rows())
        if count:
            self.selection_label.setText(
                f"{count} pasta{'s' if count != 1 else ''} selecionada{'s' if count != 1 else ''}"
            )
        else:
            self.selection_label.setText("Nenhuma pasta selecionada")
        self.add_btn.setText(f"Adicionar {count}" if count else "Adicionar")
        self.add_btn.setEnabled(count > 0)
        self._update_full_path()


class TopItemsDialog(SheetDialog):
    """Ranking dos maiores diretórios e arquivos da última análise."""

    def __init__(self, parent: QWidget | None, result: ScanResult | None) -> None:
        super().__init__(
            parent,
            "Maiores itens",
            "Os 100 diretórios e os 100 arquivos que mais ocupam espaço.",
            1080,
            680,
        )
        self.scan_result = result
        self._kind = "dirs"
        self._size_filter = "all"
        self._selected_path = ""
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self._dirs, self._files = (
                top_items(result, 100) if result is not None else ([], [])
            )
        finally:
            QApplication.restoreOverrideCursor()
        self._total = max(1, result.total_size if result is not None else 0)

        selector_row = QHBoxLayout()
        selector_row.setSpacing(8)
        selector_caption = QLabel("Mostrar")
        selector_caption.setObjectName("Muted")
        selector_row.addWidget(selector_caption)
        self.kind_btn = SelectButton("folder", "Diretórios (100)", self)
        self.kind_btn.setMinimumWidth(190)
        self.kind_btn.setMaximumWidth(240)
        self.kind_btn.set_options(
            [
                ("dirs", f"Diretórios ({len(self._dirs)})", "folder"),
                ("files", f"Arquivos ({len(self._files)})", "file-outline"),
            ],
            "dirs",
        )
        self.kind_btn.changed.connect(self._show_kind)
        selector_row.addWidget(self.kind_btn)
        size_caption = QLabel("Tamanho")
        size_caption.setObjectName("Muted")
        selector_row.addWidget(size_caption)
        self.size_btn = SelectButton("filter-variant", "Todos", self)
        self.size_btn.setMinimumWidth(150)
        self.size_btn.setMaximumWidth(190)
        self.size_btn.set_options(
            [
                ("all", "Todos", "filter-variant"),
                ("large100", "> 100 MB", "file-alert-outline"),
                ("large1g", "> 1 GB", "database-alert-outline"),
            ],
            "all",
        )
        self.size_btn.changed.connect(self._show_size)
        selector_row.addWidget(self.size_btn)
        selector_row.addStretch(1)
        self.summary = QLabel("")
        self.summary.setObjectName("Muted")
        selector_row.addWidget(self.summary)
        self.body.addLayout(selector_row)

        self.tree = QTreeWidget(self)
        self.tree.setObjectName("TopTree")
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["#", "Tamanho", "%", "Caminho completo"])
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.tree.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.tree.setIndentation(0)
        header = self.tree.header()
        header.setStretchLastSection(False)
        for column, width in ((0, 42), (1, 92), (2, 62)):
            header.setSectionResizeMode(column, QHeaderView.Fixed)
            self.tree.setColumnWidth(column, width)
        header.setSectionResizeMode(3, QHeaderView.Interactive)
        self.tree.setTextElideMode(Qt.ElideMiddle)
        self.body.addWidget(self.tree, 1)

        self.path_label = QLabel("")
        self.path_label.setObjectName("PathText")
        self.path_label.setWordWrap(True)
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.path_label.setVisible(False)
        self.body.addWidget(self.path_label)

        note = QLabel(
            "Percentuais usam o espaço total analisado. Em diretórios, os valores "
            "são cumulativos e podem se sobrepor."
        )
        note.setObjectName("Faint")
        note.setWordWrap(True)
        self.body.addWidget(note)
        if result is not None and result.truncated:
            warning = QLabel(
                "A varredura foi limitada; o ranking considera apenas os itens visitados."
            )
            warning.setObjectName("Muted")
            warning.setWordWrap(True)
            self.body.addWidget(warning)

        self.tree.itemSelectionChanged.connect(self._track_selection)
        self.tree.itemDoubleClicked.connect(
            lambda item, _column: self._open_path(item.text(3))
        )

        self.copy_btn = ActionButton("Copiar caminho", "content-copy", "soft", self, 16)
        self.copy_btn.clicked.connect(self._copy_selected)
        self.footer.addWidget(self.copy_btn)
        self.open_btn = ActionButton(
            "Abrir no Explorer", "folder-open-outline", "ghost", self, 16
        )
        self.open_btn.clicked.connect(self._open_selected)
        self.footer.addWidget(self.open_btn)
        self.export_btn = ActionButton("Exportar", "export-variant", "soft", self, 16)
        self.export_btn.setToolTip("Exportar o ranking e o resumo da análise")
        self.export_btn.clicked.connect(self._export_menu)
        self.footer.addWidget(self.export_btn)
        self.status_label = QLabel("")
        self.status_label.setObjectName("Faint")
        self.footer.addWidget(self.status_label)
        self.footer.addStretch(1)
        close = ActionButton("Fechar", "", "primary", self)
        close.clicked.connect(self.accept)
        self.footer.addWidget(close)

        self._populate()
        self._update_actions()
        self.export_btn.setEnabled(result is not None)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        QTimer.singleShot(0, self._fit_path_width)

    def _export_menu(self) -> None:
        if self.scan_result is None:
            return
        theme = get_theme()
        menu = QMenu(self.export_btn)
        csv_action = menu.addAction(
            icon("file-delimited", theme.color("muted"), 16),
            "CSV — Top 100 (Excel/LibreOffice)",
        )
        xlsx_action = menu.addAction(
            icon("file-excel", theme.color("muted"), 16),
            "XLSX — pasta de trabalho do Excel",
        )
        xlsb_action = menu.addAction(
            icon("microsoft-excel", theme.color("muted"), 16),
            "XLSB — binário do Excel",
        )
        chosen = menu.exec(
            self.export_btn.mapToGlobal(QPoint(0, self.export_btn.height() + 5))
        )
        menu.deleteLater()
        if chosen is csv_action:
            self._export_csv()
        elif chosen is xlsx_action:
            self._export_xlsx()
        elif chosen is xlsb_action:
            self._export_xlsb()

    def _ask_export(self, title: str, prefix: str, extension: str) -> str:
        path, _ = QFileDialog.getSaveFileName(
            self,
            f"Exportar {title}",
            default_export_path(prefix, extension),
            f"{title} (*.{extension})",
        )
        if not path:
            return ""
        if not path.lower().endswith(f".{extension}"):
            path += f".{extension}"
        return path

    def _export_error(self, message: str) -> None:
        self.status_label.setText("Falha ao exportar.")
        self.status_label.setToolTip(message)

    def _export_csv(self) -> None:
        if self.scan_result is None:
            return
        path = self._ask_export("CSV", "top100", "csv")
        if not path:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            write_csv(self.scan_result, self._dirs, self._files, path)
        except Exception as exc:
            self._export_error(str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.status_label.setText(f"Exportado: {Path(path).name}")
        self.status_label.setToolTip(path)

    def _export_xlsx(self) -> None:
        if self.scan_result is None:
            return
        path = self._ask_export("XLSX", "top100", "xlsx")
        if not path:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            write_xlsx(self.scan_result, self._dirs, self._files, path)
        except ImportError:
            self._export_error(
                "XLSX requer openpyxl. Instale com: py -m pip install openpyxl"
            )
            return
        except Exception as exc:
            self._export_error(str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.status_label.setText(f"Exportado: {Path(path).name}")
        self.status_label.setToolTip(path)

    def _export_xlsb(self) -> None:
        if self.scan_result is None:
            return
        path = self._ask_export("XLSB", "top100", "xlsb")
        if not path:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            write_xlsb(self.scan_result, self._dirs, self._files, path)
        except ImportError:
            self._export_error(
                "XLSB requer openpyxl e pywin32. "
                "Instale com: py -m pip install openpyxl pywin32"
            )
            return
        except Exception as exc:
            self._export_error(
                f"{exc} — XLSB requer Microsoft Excel instalado."
            )
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.status_label.setText(f"Exportado: {Path(path).name}")
        self.status_label.setToolTip(path)

    def _show_kind(self, key: str) -> None:
        self._kind = "files" if key == "files" else "dirs"
        self._selected_path = ""
        self._populate()
        self._update_actions()

    def _show_size(self, key: str) -> None:
        self._size_filter = key if key in {"large100", "large1g"} else "all"
        self._selected_path = ""
        self._populate()
        self._update_actions()

    def _filtered_nodes(self) -> list:
        nodes = self._files if self._kind == "files" else self._dirs
        if self._size_filter == "large100":
            threshold = 100 * 1024 * 1024
        elif self._size_filter == "large1g":
            threshold = 1024 * 1024 * 1024
        else:
            return nodes
        return [node for node in nodes if node.size >= threshold]

    def _populate(self) -> None:
        nodes = self._filtered_nodes()
        self.tree.clear()
        self.tree.setUpdatesEnabled(False)
        try:
            for rank, node in enumerate(nodes, 1):
                percent = node.size / self._total * 100.0
                item = QTreeWidgetItem(
                    [
                        f"{rank}",
                        format_bytes(node.size),
                        f"{percent:.1f}%",
                        node.path,
                    ]
                )
                item.setTextAlignment(0, Qt.AlignRight | Qt.AlignVCenter)
                item.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
                item.setTextAlignment(2, Qt.AlignRight | Qt.AlignVCenter)
                item.setToolTip(3, node.path)
                self.tree.addTopLevelItem(item)
            if not nodes:
                empty = QTreeWidgetItem(["", "—", "", "Nenhum item para exibir."])
                empty.setDisabled(True)
                self.tree.addTopLevelItem(empty)
        finally:
            self.tree.setUpdatesEnabled(True)
        noun = "arquivos" if self._kind == "files" else "diretórios"
        self.summary.setText(
            f"{format_bytes(self._total)} analisados · {len(nodes)} {noun}"
        )
        self.status_label.setText("")
        self.path_label.setText("")
        self.path_label.setVisible(False)
        self._fit_path_width()

    def _fit_path_width(self) -> None:
        metrics = self.tree.fontMetrics()
        width = 0
        for index in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(index)
            text = item.text(3)
            if text:
                width = max(width, metrics.horizontalAdvance(text) + 32)
        available = self.tree.viewport().width() - 42 - 92 - 62 - 8
        self.tree.setColumnWidth(3, max(480, available, width))

    def _track_selection(self) -> None:
        item = self.tree.currentItem()
        if item is None or item.isDisabled():
            self._selected_path = ""
        else:
            self._selected_path = item.text(3)
        self.path_label.setText(self._selected_path)
        self.path_label.setVisible(bool(self._selected_path))
        self.status_label.setText("")
        self._update_actions()

    def _update_actions(self) -> None:
        enabled = bool(self._selected_path)
        self.copy_btn.setEnabled(enabled)
        self.open_btn.setEnabled(enabled)

    def _copy_selected(self) -> None:
        if not self._selected_path:
            return
        QApplication.clipboard().setText(self._selected_path)
        self.status_label.setText("Caminho copiado.")

    def _open_selected(self) -> None:
        if self._selected_path:
            self._open_path(self._selected_path)

    def _open_path(self, path: str) -> None:
        if path:
            open_in_explorer(path)


class ExportDialog(SheetDialog):
    """Janela de exportação da análise em CSV, XLSX ou XLSB."""

    def __init__(self, parent: QWidget | None, result: ScanResult) -> None:
        super().__init__(
            parent,
            "Exportar dados",
            "Escolha o formato e confirme o local do arquivo.",
            560,
            340,
        )
        self.scan_result = result
        self._dirs, self._files = top_items(result, 100)
        self.exported_path = ""

        format_row = QHBoxLayout()
        format_row.setSpacing(10)
        caption = QLabel("Formato")
        caption.setObjectName("Muted")
        format_row.addWidget(caption)
        self.format_btn = SelectButton("file-export", "CSV", self)
        self.format_btn.setMinimumWidth(190)
        self.format_btn.set_options(
            [
                ("csv", "CSV — Excel/LibreOffice", "file-delimited"),
                ("xlsx", "XLSX — pasta do Excel", "file-excel"),
                ("xlsb", "XLSB — binário do Excel", "microsoft-excel"),
            ],
            "csv",
        )
        format_row.addWidget(self.format_btn)
        format_row.addStretch(1)
        self.body.addLayout(format_row)

        summary = QLabel(
            "O arquivo inclui o resumo da análise, os 100 maiores diretórios, "
            "os 100 maiores arquivos e as sugestões."
        )
        summary.setObjectName("Muted")
        summary.setWordWrap(True)
        self.body.addWidget(summary)
        note = QLabel(
            "CSV: tabela do Top 100. XLSX: abas Resumo, Top 100 e Sugestões. "
            "XLSB: requer Microsoft Excel e pywin32 instalados."
        )
        note.setObjectName("Faint")
        note.setWordWrap(True)
        self.body.addWidget(note)
        self.error = QLabel("")
        self.error.setObjectName("BadgeDanger")
        self.error.setWordWrap(True)
        self.error.setVisible(False)
        self.body.addWidget(self.error)
        self.body.addStretch(1)

        cancel = ActionButton("Cancelar", "", "ghost", self)
        cancel.clicked.connect(self.reject)
        self.footer.addStretch(1)
        self.footer.addWidget(cancel)
        export = ActionButton("Exportar", "export-variant", "primary", self)
        export.clicked.connect(self._export)
        self.footer.addWidget(export)

    def _export(self) -> None:
        fmt = self.format_btn.current()
        titles = {"csv": "CSV", "xlsx": "XLSX", "xlsb": "XLSB"}
        title = titles.get(fmt, "CSV")
        path, _ = QFileDialog.getSaveFileName(
            self,
            f"Exportar {title}",
            default_export_path("analise", fmt),
            f"{title} (*.{fmt})",
        )
        if not path:
            return
        if not path.lower().endswith(f".{fmt}"):
            path += f".{fmt}"
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if fmt == "csv":
                write_csv(self.scan_result, self._dirs, self._files, path)
            elif fmt == "xlsx":
                write_xlsx(self.scan_result, self._dirs, self._files, path)
            else:
                write_xlsb(self.scan_result, self._dirs, self._files, path)
        except ImportError:
            self.error.setText(
                "Dependência ausente. Instale com: "
                "py -m pip install openpyxl pywin32"
            )
            self.error.setVisible(True)
            return
        except Exception as exc:
            self.error.setText(str(exc))
            self.error.setVisible(True)
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.exported_path = path
        self.accept()


class ConfirmDialog(SheetDialog):
    """Confirmação estilizada (evita QMessageBox fora da identidade visual)."""

    def __init__(
        self,
        parent: QWidget | None,
        title: str,
        message: str,
        confirm_text: str = "Confirmar",
        danger: bool = True,
    ) -> None:
        super().__init__(parent, title, "Esta ação não pode ser desfeita.", 470, 260)
        from .common import IconLabel

        content = QHBoxLayout()
        content.setSpacing(14)
        icon = IconLabel("alert-outline" if danger else "information-outline", 32, "danger" if danger else "info", self)
        content.addWidget(icon, 0, Qt.AlignTop)
        text = QLabel(message)
        text.setWordWrap(True)
        text.setObjectName("Muted")
        content.addWidget(text, 1)
        self.body.addLayout(content)
        self.body.addStretch(1)
        cancel = ActionButton("Cancelar", "", "ghost", self)
        cancel.clicked.connect(self.reject)
        self.footer.addStretch(1)
        self.footer.addWidget(cancel)
        confirm = ActionButton(
            confirm_text,
            "check" if not danger else "delete-outline",
            "danger" if danger else "primary",
            self,
        )
        confirm.clicked.connect(self.accept)
        self.footer.addWidget(confirm)


class ProfileDialog(SheetDialog):
    """Edição de nome e foto do usuário."""

    def __init__(self, parent: QWidget | None, config: AppConfig) -> None:
        super().__init__(
            parent,
            "Perfil do usuário",
            "O nome e a foto aparecem no rodapé do menu lateral.",
            540,
            370,
        )
        self.config = config
        self._picked_avatar: str | None = None
        self._remove_avatar = False

        preview_row = QHBoxLayout()
        preview_row.setSpacing(18)
        self.avatar = QLabel(self)
        self.avatar.setFixedSize(88, 88)
        self.avatar.setAlignment(Qt.AlignCenter)
        self.avatar.setScaledContents(True)
        preview_row.addWidget(self.avatar, 0)
        info = QVBoxLayout()
        info.setSpacing(6)
        name_cap = QLabel("NOME")
        name_cap.setObjectName("Eyebrow")
        info.addWidget(name_cap)
        self.name_edit = QLineEdit(config.user_name, self)
        self.name_edit.setPlaceholderText("Seu nome")
        info.addWidget(self.name_edit)
        hint = QLabel("Será exibido como o usuário atual da aplicação.")
        hint.setObjectName("Faint")
        hint.setWordWrap(True)
        info.addWidget(hint)
        preview_row.addLayout(info, 1)
        self.body.addLayout(preview_row)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        choose = ActionButton("Escolher foto", "image-outline", "soft", self, 17)
        choose.clicked.connect(self._choose_avatar)
        actions.addWidget(choose)
        remove = ActionButton("Remover", "delete-outline", "danger", self, 16)
        remove.clicked.connect(self._clear_avatar)
        actions.addWidget(remove)
        actions.addStretch(1)
        self.body.addLayout(actions)

        self.error = QLabel("")
        self.error.setObjectName("BadgeDanger")
        self.error.setVisible(False)
        self.body.addWidget(self.error)
        self.body.addStretch(1)

        note = QLabel(
            "A foto e o nome são salvos localmente nas configurações do aplicativo. "
            "A imagem é copiada para a pasta de ativos, então mover o original não quebra o perfil."
        )
        note.setObjectName("Faint")
        note.setWordWrap(True)
        self.body.addWidget(note)

        cancel = ActionButton("Cancelar", "", "ghost", self)
        cancel.clicked.connect(self.reject)
        self.footer.addStretch(1)
        self.footer.addWidget(cancel)
        save = ActionButton("Salvar perfil", "check", "primary", self)
        save.clicked.connect(self._save)
        self.footer.addWidget(save)

        self.name_edit.textChanged.connect(self._refresh_avatar)
        get_theme().changed.connect(self._refresh_avatar)
        self._refresh_avatar()

    def _avatar_source(self) -> str:
        if self._picked_avatar:
            return self._picked_avatar
        if not self._remove_avatar:
            return self.config.avatar_path
        return ""

    def _refresh_avatar(self, *_args: Any) -> None:
        source = self._avatar_source()
        theme = get_theme()
        if source:
            pm = circular_pixmap(source, 82)
            if pm.isNull():
                pm = avatar_pixmap(
                    self.name_edit.text() or self.config.user_name,
                    82,
                    theme.color("primary"),
                    theme.color("info"),
                    theme.color("on_primary"),
                )
        else:
            pm = avatar_pixmap(
                self.name_edit.text() or self.config.user_name,
                82,
                theme.color("primary"),
                theme.color("info"),
                theme.color("on_primary"),
            )
        self.avatar.setPixmap(pm)

    def _choose_avatar(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Escolher foto do perfil",
            str(Path.home()),
            "Imagens (*.png *.jpg *.jpeg *.webp *.bmp *.svg);;Todos os arquivos (*)",
        )
        if path:
            self._picked_avatar = path
            self._remove_avatar = False
            self._refresh_avatar()

    def _clear_avatar(self) -> None:
        self._picked_avatar = None
        self._remove_avatar = True
        self._refresh_avatar()

    def _save(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            self.error.setText("Informe um nome para o perfil.")
            self.error.setVisible(True)
            self.name_edit.setFocus()
            return
        self.error.setVisible(False)
        self.config.set("user.name", name, save=False)
        if self._picked_avatar:
            try:
                stored = self.config.import_asset(self._picked_avatar, "avatar")
                self.config.set("user.avatar", stored, save=False)
            except Exception as exc:
                self.error.setText(f"Não foi possível salvar a foto: {exc}")
                self.error.setVisible(True)
                return
        elif self._remove_avatar:
            self.config.set("user.avatar", "", save=False)
        self.config.save()
        self.accept()
