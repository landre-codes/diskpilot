"""Diálogos do shell: seletor múltiplo de pastas e edição de perfil."""

from __future__ import annotations

import os
from collections import deque
from functools import lru_cache
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QAbstractListModel,
    QDir,
    QModelIndex,
    QObject,
    QPoint,
    QRectF,
    QRunnable,
    QSize,
    QStandardPaths,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QIcon,
    QImageReader,
    QPainter,
    QPainterPath,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QToolTip,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..config import AppConfig
from appshell.icons import avatar_pixmap, icon
from ..services.exporter import (
    default_export_dir,
    default_export_path,
    write_csv,
    write_xlsb,
    write_xlsx,
)
from ..services.model import ScanResult, top_items
from appshell.theme import get_theme
from appshell.utils import (
    avatar_photo,
    copy_to_clipboard,
    format_bytes,
    format_datetime,
    normalize_path,
    open_in_explorer,
    resolve_network_path,
)
from appshell.widgets.buttons import ActionButton, IconButton, SelectButton
from appshell.widgets.common import ElidedLabel
from appshell.widgets.dialogs import ConfirmDialog, SheetDialog


class _FolderModel(QAbstractListModel):
    """Modelo leve: o QListView desenha só as linhas visíveis."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._entries: list[tuple[str, str]] = []
        self._icon = QIcon()

    def set_entries(self, entries: list[tuple[str, str]]) -> None:
        self.beginResetModel()
        self._entries = list(entries)
        self.endResetModel()

    def set_icon(self, value: QIcon) -> None:
        self._icon = value
        if self._entries:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._entries) - 1, 0),
                [Qt.DecorationRole],
            )

    def path_at(self, row: int) -> str:
        if 0 <= row < len(self._entries):
            return self._entries[row][1]
        return ""

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._entries)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._entries):
            return None
        name, path = self._entries[index.row()]
        if role == Qt.DisplayRole:
            return name
        if role == Qt.DecorationRole:
            return self._icon
        if role in (Qt.ToolTipRole, Qt.UserRole):
            return path
        return None


class _FolderScanSignals(QObject):
    loaded = Signal(int, list, str)


class _FolderScanTask(QRunnable):
    """Lista as subpastas fora da thread da interface."""

    def __init__(
        self, path: str, generation: int, signals: _FolderScanSignals
    ) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self.path = path
        self.generation = generation
        self.signals = signals

    def run(self) -> None:
        entries: list[tuple[str, str]] = []
        error = ""
        try:
            with os.scandir(self.path) as iterator:
                for entry in iterator:
                    try:
                        if entry.is_dir():
                            entries.append((entry.name, entry.path))
                    except OSError:
                        continue
        except OSError as exc:
            error = str(exc)
        entries.sort(key=lambda item: item[0].casefold())
        self.signals.loaded.emit(self.generation, entries, error)


class FolderPickerDialog(SheetDialog):
    """Seleção de uma ou várias pastas, com lista carregada em segundo plano."""

    def __init__(
        self,
        parent: QWidget | None,
        start_path: str = "",
        *,
        title: str = "Adicionar pastas",
        subtitle: str = (
            "Escolha uma ou mais pastas na lista ou clique em “Adicionar esta "
            "pasta”. A análise é somente leitura."
        ),
        single: bool = False,
        accept_label: str = "Adicionar",
        current_label: str = "Adicionar esta pasta",
    ) -> None:
        super().__init__(
            parent,
            title,
            subtitle,
            920,
            610,
            min_width=840,
            min_height=520,
        )
        self._current_only = False
        self._single = single
        self._accept_label = accept_label
        self._current_label = current_label
        self._current = start_path or QStandardPaths.writableLocation(
            QStandardPaths.HomeLocation
        )
        if not self._current or not Path(self._current).exists():
            self._current = str(Path.home())
        self._loading = False
        self._current_valid = False
        self._folder_generation = 0
        self._folder_model = _FolderModel(self)
        # Sem parent: o QRunnable segura a referência e pode terminar depois
        # que o diálogo for fechado sem emitir em um QObject já destruído.
        self._folder_signals = _FolderScanSignals()
        self._folder_signals.loaded.connect(self._folder_loaded)
        self._folder_pool = QThreadPool(self)
        self._folder_pool.setMaxThreadCount(2)

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
        self.places.setAccessibleName("Locais")
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
        self.path_edit.setAccessibleName("Caminho da pasta")
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

        self.folder_list = QListView(self)
        self.folder_list.setObjectName("FolderList")
        self.folder_list.setAccessibleName("Subpastas")
        self.folder_list.setModel(self._folder_model)
        self.folder_list.setIconSize(QSize(18, 18))
        self.folder_list.setUniformItemSizes(True)
        self.folder_list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.folder_list.setSelectionMode(
            QAbstractItemView.SingleSelection
            if self._single
            else QAbstractItemView.ExtendedSelection
        )
        self.folder_list.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.folder_list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # ``activated`` cobre duplo clique e Enter sem disparar a navegação
        # duas vezes (doubleClicked + activated) no Windows.
        self.folder_list.activated.connect(self._enter_index)
        self.folder_list.selectionModel().selectionChanged.connect(
            self._update_selection_label
        )
        right.addWidget(self.folder_list, 1)
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
        hint = QLabel(
            "Dica: duplo clique abre uma pasta · use a pasta atual ou selecione uma subpasta"
            if single
            else "Dica: use Ctrl+clique para marcar várias pastas · duplo clique abre uma pasta"
        )
        hint.setObjectName("Faint")
        hint.setWordWrap(True)
        right.addWidget(hint)
        work.addLayout(right, 1)

        self.body.addStretch(0)
        self.add_current_btn = ActionButton(
            current_label, "folder-plus-outline", "soft", self, 16
        )
        self.add_current_btn.setMinimumWidth(170)
        self.add_current_btn.clicked.connect(self._accept_current)
        self.footer.addWidget(self.add_current_btn)
        self.selection_label = QLabel("Nenhuma pasta selecionada")
        self.selection_label.setObjectName("Muted")
        self.footer.addWidget(self.selection_label)
        self.footer.addStretch(1)
        cancel = ActionButton("Cancelar", "", "ghost", self)
        cancel.clicked.connect(self.reject)
        self.footer.addWidget(cancel)
        self.add_btn = ActionButton(accept_label, "folder-plus-outline", "primary", self)
        self.add_btn.clicked.connect(self.accept)
        self.footer.addWidget(self.add_btn)

        self.places.itemClicked.connect(self._place_clicked)
        get_theme().changed.connect(self._sync_icons)
        get_theme().changed.connect(self._refresh_folder_icon)
        self._sync_icons()
        self._refresh_folder_icon()
        self.path_edit.setText(self._current)
        self.path_edit.setToolTip(self._current)
        self.up_btn.setEnabled(False)
        self.selection_label.setText("Carregando pastas…")
        # A janela aparece primeiro; a enumeração de unidades e a primeira
        # navegação podem tocar a rede e não devem atrasar o diálogo.
        QTimer.singleShot(0, self._initial_load)

    # ------------------------------------------------------------ localidades
    def _initial_load(self) -> None:
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self._populate_places()
            self._navigate(self._current)
        finally:
            QApplication.restoreOverrideCursor()
        self._sync_icons()

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
            resolved = resolve_network_path(path, verify=False)
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
    def _navigate(self, path: str) -> None:
        path = resolve_network_path(normalize_path(path))
        if not path:
            return
        self._current = path
        self._current_only = False
        self.path_edit.setText(path)
        self.path_edit.setToolTip(path)
        if hasattr(self, "add_current_btn"):
            self.add_current_btn.setToolTip(f"Adicionar a pasta exibida: {path}")
        self.up_btn.setEnabled(Path(path).parent != Path(path))
        self._sync_icons()
        self._update_full_path()
        self._start_list_load(path)

    def _refresh_folder_icon(self, *_args: Any) -> None:
        self._folder_model.set_icon(
            icon("folder", get_theme().color("primary"), 18)
        )

    def _start_list_load(self, path: str) -> None:
        self._folder_generation += 1
        generation = self._folder_generation
        self._loading = True
        self._current_valid = False
        self._folder_model.set_entries([])
        self.selection_label.setText("Carregando pastas…")
        self.add_btn.setEnabled(False)
        self._folder_pool.start(
            _FolderScanTask(path, generation, self._folder_signals)
        )

    def _folder_loaded(
        self, generation: int, entries: list, error: str
    ) -> None:
        if generation != self._folder_generation:
            return
        self._loading = False
        if error:
            self._current_valid = False
            self.selection_label.setText("Sem acesso a esta pasta")
            self.selection_label.setToolTip(error)
            return
        self._current_valid = True
        self.selection_label.setToolTip("")
        self._folder_model.set_entries(list(entries))
        if not entries:
            self.selection_label.setText("Nenhuma subpasta")
            self.add_btn.setEnabled(False)
            self._update_full_path()
            return
        self._update_selection_label()

    def _go_up(self) -> None:
        parent = str(Path(self._current).parent)
        if os.path.normcase(parent) != os.path.normcase(self._current):
            self._navigate(parent)

    def _go_typed(self) -> None:
        self._navigate(self.path_edit.text().strip().strip('"'))

    def _enter_index(self, index: QModelIndex) -> None:
        path = self._folder_model.path_at(index.row())
        if path:
            self._navigate(path)

    # ------------------------------------------------------------- seleção
    def _selected_rows(self) -> list[str]:
        selection = self.folder_list.selectionModel()
        if selection is None:
            return []
        return [
            normalize_path(self._folder_model.path_at(index.row()))
            for index in selection.selectedRows()
            if self._folder_model.path_at(index.row())
        ]

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
        if not self._current_valid and not os.path.isdir(self._current):
            self.selection_label.setText("Pasta atual inválida ou inacessível")
            return
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
        if self._loading:
            self.selection_label.setText("Carregando pastas…")
            self.add_btn.setEnabled(False)
            return
        count = len(self._selected_rows())
        if self._single:
            self.selection_label.setText(
                "1 selecionada" if count else "Pasta atual"
            )
            self.add_btn.setText(self._accept_label)
            self.add_btn.setEnabled(count > 0)
            self._update_full_path()
            return
        if count:
            self.selection_label.setText(
                f"{count} pasta{'s' if count != 1 else ''} selecionada{'s' if count != 1 else ''}"
            )
        else:
            self.selection_label.setText("Nenhuma pasta selecionada")
        self.add_btn.setText(f"Adicionar {count}" if count else "Adicionar")
        self.add_btn.setEnabled(count > 0)
        self._update_full_path()


class _TopItemsSignals(QObject):
    loaded = Signal(list, list)
    failed = Signal(str)


class _TopItemsTask(QRunnable):
    def __init__(self, result: ScanResult, signals: _TopItemsSignals) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self.result = result
        self.signals = signals

    def run(self) -> None:
        try:
            dirs, files = top_items(self.result, 100)
        except Exception as exc:  # pragma: no cover - borda
            self.signals.failed.emit(str(exc))
        else:
            self.signals.loaded.emit(dirs, files)


class TopItemsDialog(SheetDialog):
    """Ranking dos maiores diretórios e arquivos da última análise."""

    def __init__(self, parent: QWidget | None, result: ScanResult | None) -> None:
        super().__init__(
            parent,
            "Maiores itens",
            "Os 100 diretórios e os 100 arquivos que mais ocupam espaço.",
            1080,
            680,
            min_width=760,
            min_height=480,
        )
        self.scan_result = result
        self._kind = "dirs"
        self._size_filter = "all"
        self._selected_path = ""
        self._dirs: list = []
        self._files: list = []
        self._loading = result is not None
        self._top_signals = _TopItemsSignals()
        self._top_signals.loaded.connect(self._ranking_loaded)
        self._top_signals.failed.connect(self._ranking_failed)
        self._top_pool = QThreadPool(self)
        self._top_pool.setMaxThreadCount(1)
        self._total = max(1, result.total_size if result is not None else 0)

        selector_row = QHBoxLayout()
        selector_row.setSpacing(8)
        selector_caption = QLabel("Mostrar")
        selector_caption.setObjectName("Muted")
        selector_row.addWidget(selector_caption)
        self.kind_btn = SelectButton("folder", "Diretórios (0)", self)
        self.kind_btn.setMinimumWidth(190)
        self.kind_btn.setMaximumWidth(240)
        self.kind_btn.set_options(
            [
                ("dirs", f"Diretórios ({len(self._dirs)})", "folder"),
                ("files", f"Arquivos ({len(self._files)})", "file-outline"),
            ],
            "dirs",
        )
        self.kind_btn.setEnabled(not self._loading)
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
        self.size_btn.setEnabled(not self._loading)
        self.size_btn.changed.connect(self._show_size)
        selector_row.addWidget(self.size_btn)
        selector_row.addStretch(1)
        self.summary = QLabel(
            "Carregando ranking…" if self._loading else ""
        )
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
        if result is not None:
            self._top_pool.start(_TopItemsTask(result, self._top_signals))

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        QTimer.singleShot(0, self._fit_path_width)

    def _export_menu(self) -> None:
        if self.scan_result is None:
            return
        dialog = ExportDialog(self, self.scan_result)
        try:
            if (
                dialog.exec() == QDialog.DialogCode.Accepted
                and dialog.exported_path
            ):
                self.status_label.setText(
                    f"Exportado: {Path(dialog.exported_path).name}"
                )
                self.status_label.setToolTip(dialog.exported_path)
        finally:
            dialog.deleteLater()

    def _ranking_loaded(self, dirs: list, files: list) -> None:
        self._dirs = list(dirs)
        self._files = list(files)
        self._loading = False
        self.kind_btn.setEnabled(True)
        self.size_btn.setEnabled(True)
        self.kind_btn.set_options(
            [
                ("dirs", f"Diretórios ({len(self._dirs)})", "folder"),
                ("files", f"Arquivos ({len(self._files)})", "file-outline"),
            ],
            self._kind,
        )
        self._populate()
        self._update_actions()

    def _ranking_failed(self, message: str) -> None:
        self._loading = False
        self.summary.setText("Falha ao carregar o ranking")
        self.status_label.setText(message)
        self.status_label.setToolTip(message)

    def _show_kind(self, key: str) -> None:
        if self._loading:
            return
        self._kind = "files" if key == "files" else "dirs"
        self._selected_path = ""
        self._populate()
        self._update_actions()

    def _show_size(self, key: str) -> None:
        if self._loading:
            return
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
        if self._loading:
            self.tree.clear()
            self.summary.setText("Carregando ranking…")
            return
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


class _ExportSignals(QObject):
    finished = Signal(str)
    failed = Signal(str)


class _ExportTask(QRunnable):
    """Grava a exportação fora da thread da interface."""

    def __init__(
        self,
        fmt: str,
        result: ScanResult,
        path: str,
        signals: _ExportSignals,
    ) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self.fmt = fmt
        self.result = result
        self.path = path
        self.signals = signals

    def run(self) -> None:
        try:
            dirs, files = top_items(self.result, 100)
            if self.fmt == "csv":
                write_csv(self.result, dirs, files, self.path)
            elif self.fmt == "xlsx":
                write_xlsx(self.result, dirs, files, self.path)
            else:
                write_xlsb(self.result, dirs, files, self.path)
        except ImportError as exc:
            self.signals.failed.emit(
                f"Dependência ausente: {exc}. "
                "Instale com: py -m pip install openpyxl pywin32"
            )
        except Exception as exc:  # pragma: no cover - borda de I/O/Excel
            message = str(exc) or exc.__class__.__name__
            if self.fmt == "xlsb":
                message += " — XLSB requer Microsoft Excel instalado."
            self.signals.failed.emit(message)
        else:
            self.signals.finished.emit(self.path)


class ExportDialog(SheetDialog):
    """Janela de exportação da análise em CSV, XLSX ou XLSB."""

    def __init__(self, parent: QWidget | None, result: ScanResult) -> None:
        super().__init__(
            parent,
            "Exportar dados",
            "Escolha o formato, a pasta de destino e o nome do arquivo.",
            620,
            520,
            min_width=600,
            min_height=420,
        )
        self.scan_result = result
        self.exported_path = ""
        self._fmt = "csv"
        self._exporting = False
        self._task: _ExportTask | None = None
        self._signals = _ExportSignals()
        self._signals.finished.connect(self._export_finished)
        self._signals.failed.connect(self._export_failed)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)

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
        self.format_btn.changed.connect(self._format_changed)
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

        folder_cap = QLabel("PASTA DE DESTINO")
        folder_cap.setObjectName("Eyebrow")
        self.body.addWidget(folder_cap)
        folder_row = QHBoxLayout()
        folder_row.setSpacing(8)
        self.folder_edit = QLineEdit(default_export_dir(), self)
        self.folder_edit.setPlaceholderText("Caminho da pasta de destino")
        self.folder_edit.setAccessibleName("Pasta de destino")
        self.folder_edit.textChanged.connect(self._update_target)
        folder_row.addWidget(self.folder_edit, 1)
        choose_folder = ActionButton(
            "Escolher pasta…", "folder-open-outline", "soft", self, 16
        )
        choose_folder.clicked.connect(self._choose_folder)
        folder_row.addWidget(choose_folder)
        self.body.addLayout(folder_row)

        name_cap = QLabel("NOME DO ARQUIVO")
        name_cap.setObjectName("Eyebrow")
        self.body.addWidget(name_cap)
        default_name = Path(default_export_path("analise", "csv")).name
        self.name_edit = QLineEdit(default_name, self)
        self.name_edit.setPlaceholderText("Nome do arquivo")
        self.name_edit.setAccessibleName("Nome do arquivo")
        self.name_edit.textChanged.connect(self._update_target)
        self.body.addWidget(self.name_edit)

        self.target_label = QLabel("")
        self.target_label.setObjectName("PathText")
        self.target_label.setWordWrap(True)
        self.target_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.body.addWidget(self.target_label)

        note = QLabel(
            "A gravação ocorre em segundo plano. CSV: Top 100; XLSX: abas "
            "Resumo, Top 100 e Sugestões; XLSB requer Microsoft Excel e pywin32."
        )
        note.setObjectName("Faint")
        note.setWordWrap(True)
        self.body.addWidget(note)
        self.error = QLabel("")
        self.error.setObjectName("BadgeDanger")
        self.error.setWordWrap(True)
        self.error.setVisible(False)
        self.body.addWidget(self.error)
        self.status = QLabel("")
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)
        self.body.addWidget(self.status)
        self.body.addStretch(1)

        self.cancel_btn = ActionButton("Cancelar", "", "ghost", self)
        self.cancel_btn.clicked.connect(self.reject)
        self.footer.addStretch(1)
        self.footer.addWidget(self.cancel_btn)
        self.export_btn = ActionButton("Exportar", "export-variant", "primary", self)
        self.export_btn.clicked.connect(self._export)
        self.footer.addWidget(self.export_btn)
        self._update_target()

    def _format_changed(self, fmt: str) -> None:
        self._fmt = fmt
        name = self.name_edit.text().strip()
        if not name:
            name = Path(default_export_path("analise", fmt)).name
        path = Path(name)
        if path.suffix.lower() in {".csv", ".xlsx", ".xlsb"}:
            name = path.with_suffix(f".{fmt}").name
        else:
            name = f"{name}.{fmt}"
        self.name_edit.setText(name)
        self._update_target()

    def _update_target(self, *_args: Any) -> None:
        folder = self.folder_edit.text().strip()
        name = self.name_edit.text().strip()
        if folder and name:
            try:
                expanded = os.path.expandvars(os.path.expanduser(folder))
                target = str(Path(expanded) / name)
            except Exception:
                target = f"{folder}\\{name}"
        else:
            target = ""
        self.target_label.setText(target)
        self.target_label.setToolTip(target)

    def _choose_folder(self) -> None:
        start = self.folder_edit.text().strip() or default_export_dir()
        dialog = FolderPickerDialog(
            self,
            start,
            title="Pasta de destino",
            subtitle="Escolha onde o arquivo exportado será salvo.",
            single=True,
            accept_label="Usar pasta",
            current_label="Usar esta pasta",
        )
        try:
            if dialog.exec() == QDialog.DialogCode.Accepted:
                paths = dialog.selected_paths()
                if paths:
                    self.folder_edit.setText(paths[0])
        finally:
            dialog.deleteLater()

    def _validated_path(self) -> Path | None:
        folder_text = self.folder_edit.text().strip().strip('"')
        name = self.name_edit.text().strip().strip('"')
        if not folder_text:
            self._show_error("Informe a pasta de destino.")
            return None
        if not name:
            self._show_error("Informe o nome do arquivo.")
            return None
        if name in {".", ".."}:
            self._show_error("Escolha um nome de arquivo válido.")
            return None
        if any(char in name for char in '<>:"/\\|?*'):
            self._show_error("O nome do arquivo contém caracteres inválidos.")
            return None
        if name.endswith((" ", ".")):
            self._show_error("O nome do arquivo não pode terminar com espaço ou ponto.")
            return None
        stem = Path(name).stem.upper()
        reserved = {"CON", "PRN", "AUX", "NUL"}
        reserved.update({f"COM{i}" for i in range(1, 10)})
        reserved.update({f"LPT{i}" for i in range(1, 10)})
        if stem in reserved:
            self._show_error("Este nome é reservado pelo Windows.")
            return None
        name_path = Path(name)
        if name_path.suffix.lower() in {".csv", ".xlsx", ".xlsb"}:
            if name_path.suffix.lower() != f".{self._fmt}":
                name = name_path.with_suffix(f".{self._fmt}").name
        elif not name.lower().endswith(f".{self._fmt}"):
            name += f".{self._fmt}"
        try:
            folder = Path(os.path.expandvars(os.path.expanduser(folder_text)))
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._show_error(f"Não foi possível usar a pasta: {exc}")
            return None
        if not folder.is_dir():
            self._show_error("O destino não é uma pasta válida.")
            return None
        return folder / name

    def _show_error(self, message: str) -> None:
        self.error.setText(message)
        self.error.setVisible(True)

    def _export(self) -> None:
        if self._exporting:
            return
        path = self._validated_path()
        if path is None:
            return
        self.error.setVisible(False)
        if path.exists():
            confirm = ConfirmDialog(
                self,
                "Substituir arquivo",
                f"O arquivo já existe:\n{path}\n\nDeseja substituí-lo?",
                "Substituir",
                danger=True,
            )
            try:
                if confirm.exec() != QDialog.DialogCode.Accepted:
                    return
            finally:
                confirm.deleteLater()
        self._exporting = True
        self.export_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.status.setText(f"Exportando em segundo plano: {path}")
        task = _ExportTask(
            self.format_btn.current(),
            self.scan_result,
            str(path),
            self._signals,
        )
        self._task = task
        self._pool.start(task)

    def _export_finished(self, path: str) -> None:
        self._exporting = False
        self._task = None
        self.exported_path = path
        self.accept()

    def _export_failed(self, message: str) -> None:
        self._exporting = False
        self._task = None
        self.status.setText("")
        self.export_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        self._show_error(message)

    def reject(self) -> None:
        if self._exporting:
            return
        super().reject()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._exporting:
            event.ignore()
            return
        super().closeEvent(event)


_AVATAR_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".jfif",
    ".webp",
    ".bmp",
    ".gif",
    ".svg",
    ".svgz",
    ".tif",
    ".tiff",
}
_MAX_IMAGE_ITEMS = 4000
_PLACE_KIND_ROLE = Qt.UserRole + 1


def _display_dimensions(path: str, mtime: float) -> QSize:
    """Dimensões exibidas, trocando eixos quando o EXIF gira a foto."""
    try:
        raw = QImageReader(path).size()
        if not raw.isValid():
            return QSize()
        thumb = _thumbnail_pixmap(path, mtime, 112)
        if thumb.isNull():
            return raw
        raw_landscape = raw.width() >= raw.height()
        thumb_landscape = thumb.width() >= thumb.height()
        if raw_landscape != thumb_landscape:
            return QSize(raw.height(), raw.width())
        return raw
    except Exception:
        return QSize()


@lru_cache(maxsize=384)
def _thumbnail_pixmap(path: str, mtime: float, box: int) -> QPixmap:
    """Miniatura com rotação EXIF e escala preservada, sem carregar tudo."""
    try:
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        size = reader.size()
        if not size.isValid() or size.width() <= 0 or size.height() <= 0:
            return QPixmap()
        scaled = size.scaled(QSize(box, box), Qt.KeepAspectRatio)
        if scaled.width() <= 0 or scaled.height() <= 0:
            return QPixmap()
        reader.setScaledSize(scaled)
        image = reader.read()
        if image.isNull():
            return QPixmap()
        return QPixmap.fromImage(image)
    except Exception:
        return QPixmap()


@lru_cache(maxsize=16)
def _preview_pixmap(path: str, mtime: float, size: int = 210) -> QPixmap:
    """Prévia arredondada em resolução 2×, sem decodificar a foto inteira."""
    source = _thumbnail_pixmap(path, mtime, size * 2)
    if source.isNull():
        return QPixmap()
    side = size * 2
    target = QPixmap(side, side)
    target.fill(Qt.transparent)
    scaled = source.scaled(side, side, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    painter = QPainter(target)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, side, side), 24, 24)
    painter.setClipPath(clip)
    painter.drawPixmap(
        (side - scaled.width()) // 2,
        (side - scaled.height()) // 2,
        scaled,
    )
    painter.end()
    target.setDevicePixelRatio(2)
    return target


class _ImageScanSignals(QObject):
    loaded = Signal(int, list, list, str)


class _ImageScanTask(QRunnable):
    """Lista pastas e imagens fora da thread da interface."""

    def __init__(
        self, path: str, generation: int, signals: _ImageScanSignals
    ) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self.path = path
        self.generation = generation
        self.signals = signals

    def run(self) -> None:
        dirs: list[tuple[str, str]] = []
        images: list[tuple[str, str, float]] = []
        error = ""
        try:
            with os.scandir(self.path) as iterator:
                for entry in iterator:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            dirs.append((entry.name, entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            suffix = os.path.splitext(entry.name)[1].lower()
                            if suffix in _AVATAR_EXTENSIONS:
                                stat = entry.stat(follow_symlinks=False)
                                images.append(
                                    (entry.name, entry.path, stat.st_mtime)
                                )
                    except OSError:
                        continue
        except OSError as exc:
            error = str(exc)
        dirs.sort(key=lambda entry: entry[0].casefold())
        images.sort(key=lambda entry: entry[0].casefold())
        self.signals.loaded.emit(self.generation, dirs, images, error)


class ImagePickerDialog(SheetDialog):
    """Seletor de imagens com miniaturas, locais e prévia."""

    def __init__(self, parent: QWidget | None, start_path: str = "") -> None:
        super().__init__(
            parent,
            "Escolher foto do perfil",
            "Navegue pelas pastas, confira a prévia e escolha a imagem. "
            "O enquadramento é ajustado na tela do perfil.",
            1040,
            650,
            min_width=760,
            min_height=520,
        )
        self.selected_path = ""
        self._current = ""
        self._initial_file = start_path if start_path and Path(start_path).is_file() else ""
        self._thumb_box = 112
        self._thumb_queue: deque[tuple[QListWidgetItem, str, float]] = deque()
        self._thumb_timer = QTimer(self)
        self._thumb_timer.setInterval(12)
        self._thumb_timer.timeout.connect(self._load_thumbnails)
        self._loading = False
        self._image_generation = 0
        self._grid_generation = 0
        self._image_count = 0
        self._initial_item: QListWidgetItem | None = None
        self._truncated = False
        self._pending_grid: list[tuple[str, str, bool, float]] = []
        self._pending_pos = 0
        self._grid_timer = QTimer(self)
        self._grid_timer.setInterval(0)
        self._grid_timer.timeout.connect(self._add_grid_batch)
        self._image_signals = _ImageScanSignals()
        self._image_signals.loaded.connect(self._images_loaded)
        self._image_pool = QThreadPool(self)
        self._image_pool.setMaxThreadCount(2)

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
        self.places.setFixedWidth(220)
        self.places.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left.addWidget(self.places, 1)
        work.addLayout(left)

        # Navegador e grade ----------------------------------------------
        right = QVBoxLayout()
        right.setSpacing(9)
        nav = QHBoxLayout()
        nav.setSpacing(6)
        self.up_btn = IconButton("arrow-up", "Subir um nível", self, 17, 32, "primary")
        self.up_btn.clicked.connect(self._go_up)
        nav.addWidget(self.up_btn)
        self.path_edit = QLineEdit(self)
        self.path_edit.setPlaceholderText("Caminho da pasta")
        self.path_edit.setAccessibleName("Caminho da pasta")
        self._path_action = self.path_edit.addAction(
            icon("folder-open-outline", get_theme().color("muted"), 16),
            QLineEdit.LeadingPosition,
        )
        self.path_edit.returnPressed.connect(self._go_typed)
        nav.addWidget(self.path_edit, 1)
        go = ActionButton("Ir", "arrow-right", "soft", self, 16)
        go.clicked.connect(self._go_typed)
        nav.addWidget(go)
        refresh = IconButton("refresh", "Atualizar pasta", self, 15, 28, "primary")
        refresh.clicked.connect(self._reload)
        nav.addWidget(refresh)
        right.addLayout(nav)

        main = QHBoxLayout()
        main.setSpacing(12)
        self.grid = QListWidget(self)
        self.grid.setObjectName("ImageGrid")
        self.grid.setViewMode(QListView.IconMode)
        self.grid.setResizeMode(QListView.Adjust)
        self.grid.setMovement(QListView.Static)
        self.grid.setFlow(QListView.LeftToRight)
        self.grid.setWrapping(True)
        self.grid.setSpacing(8)
        self.grid.setUniformItemSizes(True)
        self.grid.setIconSize(QSize(112, 112))
        self.grid.setGridSize(QSize(142, 148))
        self.grid.setWordWrap(False)
        self.grid.setTextElideMode(Qt.ElideMiddle)
        self.grid.setSelectionMode(QAbstractItemView.SingleSelection)
        self.grid.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.grid.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.grid.currentItemChanged.connect(self._update_preview)
        self.grid.itemActivated.connect(self._activate_item)
        main.addWidget(self.grid, 1)

        panel = QFrame(self)
        panel.setObjectName("ImagePreview")
        panel.setFixedWidth(268)
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(14, 14, 14, 14)
        pv.setSpacing(8)
        cap = QLabel("PRÉVIA")
        cap.setObjectName("Eyebrow")
        pv.addWidget(cap)
        self.preview = QLabel("Selecione uma foto\npara ver a prévia")
        self.preview.setObjectName("ImagePreviewCanvas")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setWordWrap(True)
        self.preview.setFixedSize(238, 210)
        pv.addWidget(self.preview, 0, Qt.AlignHCenter)
        self.preview_name = ElidedLabel("Nenhuma foto selecionada")
        self.preview_name.setObjectName("SectionTitle")
        self.preview_name.setAlignment(Qt.AlignCenter)
        self.preview_name.setMaximumWidth(238)
        pv.addWidget(self.preview_name)
        self.preview_details = QLabel("")
        self.preview_details.setObjectName("Muted")
        self.preview_details.setAlignment(Qt.AlignCenter)
        self.preview_details.setWordWrap(True)
        pv.addWidget(self.preview_details)
        pv.addStretch(1)
        hint = QLabel("Dica: duplo clique ou Enter escolhe a foto.")
        hint.setObjectName("Faint")
        hint.setWordWrap(True)
        pv.addWidget(hint)
        main.addWidget(panel, 0)
        right.addLayout(main, 1)

        self.empty_label = QLabel("Nenhuma imagem nesta pasta.")
        self.empty_label.setObjectName("Muted")
        self.empty_label.setVisible(False)
        right.addWidget(self.empty_label)

        self.error = QLabel("")
        self.error.setObjectName("BadgeDanger")
        self.error.setWordWrap(True)
        self.error.setVisible(False)
        right.addWidget(self.error)

        path_caption = QLabel("CAMINHO COMPLETO")
        path_caption.setObjectName("Eyebrow")
        right.addWidget(path_caption)
        path_row = QHBoxLayout()
        path_row.setSpacing(6)
        self.full_path_label = QLabel("")
        self.full_path_label.setObjectName("PathText")
        self.full_path_label.setWordWrap(True)
        self.full_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        path_row.addWidget(self.full_path_label, 1)
        self.copy_path_btn = IconButton(
            "content-copy", "Copiar caminho completo", self, 15, 28, "primary"
        )
        self.copy_path_btn.clicked.connect(self._copy_full_path)
        path_row.addWidget(self.copy_path_btn, 0, Qt.AlignTop)
        right.addLayout(path_row)
        work.addLayout(right, 1)

        self.selection_label = QLabel("Nenhuma foto selecionada")
        self.selection_label.setObjectName("Muted")
        self.footer.addWidget(self.selection_label)
        self.footer.addStretch(1)
        cancel = ActionButton("Cancelar", "", "ghost", self)
        cancel.clicked.connect(self.reject)
        self.footer.addWidget(cancel)
        self.choose_btn = ActionButton(
            "Escolher foto", "check-circle-outline", "primary", self
        )
        self.choose_btn.setEnabled(False)
        self.choose_btn.clicked.connect(self._accept_selected)
        self.footer.addWidget(self.choose_btn)

        self._populate_places()
        self.places.itemClicked.connect(self._place_clicked)
        get_theme().changed.connect(self._sync_icons)
        self._sync_icons()

        start = start_path
        if start and Path(start).is_file():
            start = str(Path(start).parent)
        if not start or not Path(start).is_dir():
            start = QStandardPaths.writableLocation(
                QStandardPaths.PicturesLocation
            )
        if not start or not Path(start).is_dir():
            start = str(Path.home())
        self._navigate(start)

    # ------------------------------------------------------------ localidades
    def _populate_places(self) -> None:
        self.places.clear()
        theme = get_theme()
        locations = [
            ("Imagens", QStandardPaths.PicturesLocation, "image"),
            ("Início", QStandardPaths.HomeLocation, "folder"),
            ("Área de trabalho", QStandardPaths.DesktopLocation, "folder"),
            ("Documentos", QStandardPaths.DocumentsLocation, "folder"),
            ("Downloads", QStandardPaths.DownloadLocation, "folder"),
        ]
        seen: set[str] = set()
        for label, location, kind in locations:
            path = QStandardPaths.writableLocation(location)
            if not path or not Path(path).exists():
                continue
            key = os.path.normcase(path)
            if key in seen:
                continue
            seen.add(key)
            item = QListWidgetItem(icon("folder", theme.color("muted"), 16), label)
            item.setToolTip(path)
            item.setData(Qt.UserRole, path)
            item.setData(_PLACE_KIND_ROLE, kind)
            self.places.addItem(item)
        for drive in QDir.drives():
            path = drive.absolutePath()
            resolved = resolve_network_path(path, verify=False)
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
            item.setData(_PLACE_KIND_ROLE, "network" if network else "drive")
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
            kind = str(item.data(_PLACE_KIND_ROLE) or "")
            if kind == "image":
                md = "image-multiple-outline"
            elif kind == "network":
                md = "server-network"
            elif kind == "drive":
                md = "harddisk"
            else:
                md = "folder"
            item.setIcon(icon(md, theme.color("muted"), 16))
            if os.path.normcase(path) == os.path.normcase(self._current):
                self.places.setCurrentItem(item)

    # ------------------------------------------------------------- navegação
    def _navigate(self, path: str) -> None:
        path = resolve_network_path(normalize_path(path))
        if not path:
            return
        self._current = path
        self.path_edit.setText(path)
        self.path_edit.setToolTip(path)
        self.up_btn.setEnabled(Path(path).parent != Path(path))
        self.places.setCurrentItem(None)
        for i in range(self.places.count()):
            item = self.places.item(i)
            if os.path.normcase(str(item.data(Qt.UserRole) or "")) == os.path.normcase(path):
                self.places.setCurrentItem(item)
                break
        self._start_image_load(path)

    def _go_up(self) -> None:
        parent = str(Path(self._current).parent)
        if os.path.normcase(parent) != os.path.normcase(self._current):
            self._navigate(parent)

    def _go_typed(self) -> None:
        self._navigate(self.path_edit.text().strip().strip('"'))

    def _reload(self) -> None:
        if self._current:
            self._start_image_load(self._current)

    def _start_image_load(self, path: str) -> None:
        self._image_generation += 1
        generation = self._image_generation
        self._grid_generation = generation
        self._loading = True
        self._thumb_timer.stop()
        self._thumb_queue.clear()
        self._grid_timer.stop()
        self._pending_grid = []
        self._pending_pos = 0
        self._image_count = 0
        self._initial_item = None
        self._truncated = False
        self.grid.clear()
        self.selected_path = ""
        self.error.setVisible(False)
        self.choose_btn.setEnabled(False)
        self.empty_label.setText("Carregando imagens…")
        self.empty_label.setVisible(True)
        self.full_path_label.setText(path)
        self.full_path_label.setToolTip(path)
        self._update_preview()
        self._image_pool.start(
            _ImageScanTask(path, generation, self._image_signals)
        )

    def _images_loaded(
        self, generation: int, dirs: list, images: list, error: str
    ) -> None:
        if generation != self._image_generation:
            return
        self._loading = False
        if error:
            self.empty_label.setText("Não foi possível abrir esta pasta.")
            self._show_error(f"Não foi possível abrir a pasta: {error}")
            return
        truncated = len(images) > _MAX_IMAGE_ITEMS
        if truncated:
            images = images[:_MAX_IMAGE_ITEMS]
        self._truncated = truncated
        self._image_count = len(images)
        self._pending_grid = [
            (name, path, True, 0.0) for name, path in dirs
        ] + [(name, path, False, mtime) for name, path, mtime in images]
        self._pending_pos = 0
        if not self._pending_grid:
            self.empty_label.setText("Nenhuma imagem nesta pasta.")
            self.empty_label.setVisible(True)
            self._update_preview()
            return
        self._add_grid_batch()

    def _add_grid_batch(self) -> None:
        if self._grid_generation != self._image_generation:
            self._grid_timer.stop()
            return
        end = min(self._pending_pos + 120, len(self._pending_grid))
        theme = get_theme()
        folder_icon = icon("folder", theme.color("primary"), 96)
        image_icon = icon("file-image-outline", theme.color("muted"), 96)
        for name, path, is_dir, mtime in self._pending_grid[
            self._pending_pos:end
        ]:
            item = QListWidgetItem(folder_icon if is_dir else image_icon, name)
            item.setData(Qt.UserRole, path)
            item.setData(Qt.UserRole + 2, is_dir)
            item.setToolTip(path)
            self.grid.addItem(item)
            if not is_dir:
                self._thumb_queue.append((item, path, mtime))
                if self._initial_file and os.path.normcase(path) == os.path.normcase(
                    self._initial_file
                ):
                    self._initial_item = item
        self._pending_pos = end
        if self._pending_pos < len(self._pending_grid):
            self._grid_timer.start(0)
            return
        self._grid_timer.stop()
        self._initial_file = ""
        if self._truncated:
            self.empty_label.setText(
                f"Mostrando as primeiras {_MAX_IMAGE_ITEMS} imagens desta pasta."
            )
            self.empty_label.setVisible(True)
        elif not self._image_count:
            self.empty_label.setText("Nenhuma imagem nesta pasta.")
            self.empty_label.setVisible(True)
        else:
            self.empty_label.setVisible(False)
        if self._initial_item is not None:
            self.grid.setCurrentItem(self._initial_item)
            self.grid.scrollToItem(self._initial_item)
        self._update_preview()
        if self._thumb_queue:
            self._thumb_timer.start(0)

    def _show_error(self, message: str) -> None:
        self.error.setText(message)
        self.error.setVisible(True)

    def _load_thumbnails(self) -> None:
        for _ in range(6):
            if not self._thumb_queue:
                break
            item, path, mtime = self._thumb_queue.popleft()
            pixmap = _thumbnail_pixmap(path, mtime, self._thumb_box)
            if not pixmap.isNull():
                item.setIcon(QIcon(pixmap))
        if self._thumb_queue:
            self._thumb_timer.start(12)
        else:
            self._thumb_timer.stop()

    # ------------------------------------------------------------- seleção
    def _update_preview(self, *_args: Any) -> None:
        item = self.grid.currentItem()
        path = str(item.data(Qt.UserRole) or "") if item is not None else ""
        is_dir = bool(item.data(Qt.UserRole + 2)) if item is not None else False
        if not item or not path:
            self.preview.clear()
            self.preview.setText("Selecione uma foto\npara ver a prévia")
            self.preview_name.setText("Nenhuma foto selecionada")
            self.preview_details.setText("")
            self.selection_label.setText("Nenhuma foto selecionada")
            self.selected_path = ""
            self.choose_btn.setEnabled(False)
            return
        self.full_path_label.setText(path)
        self.full_path_label.setToolTip(path)
        if is_dir:
            self.preview.clear()
            self.preview.setPixmap(
                icon("folder", get_theme().color("muted"), 72).pixmap(72, 72)
            )
            self.preview_name.setText(Path(path).name)
            self.preview_details.setText("Pasta · duplo clique para abrir")
            self.selection_label.setText("Selecione uma imagem")
            self.selected_path = ""
            self.choose_btn.setEnabled(False)
            return
        self.preview.clear()
        try:
            stat = Path(path).stat()
        except OSError:
            size = QImageReader(path).size()
            details = f"{size.width()} × {size.height()} px"
        else:
            self.preview.setPixmap(_preview_pixmap(path, stat.st_mtime))
            size = _display_dimensions(path, stat.st_mtime)
            details = (
                f"{size.width()} × {size.height()} px · "
                f"{format_bytes(stat.st_size)} · {format_datetime(stat.st_mtime)}"
            )
        self.preview_name.setText(Path(path).name)
        self.preview_details.setText(details)
        self.selection_label.setText("Foto selecionada")
        self.selected_path = path
        self.choose_btn.setEnabled(True)

    def _activate_item(self, item: QListWidgetItem) -> None:
        path = str(item.data(Qt.UserRole) or "")
        if not path:
            return
        if bool(item.data(Qt.UserRole + 2)):
            self._navigate(path)
            return
        self.grid.setCurrentItem(item)
        self._update_preview()
        self._accept_selected()

    def _accept_selected(self) -> None:
        if not self.selected_path:
            return
        self.accept()

    def _copy_full_path(self) -> None:
        text = self.full_path_label.text()
        if not text:
            return
        QApplication.clipboard().setText(text)
        QToolTip.showText(
            self.copy_path_btn.mapToGlobal(self.copy_path_btn.rect().bottomLeft()),
            "Caminho copiado.",
            self.copy_path_btn,
        )


class AvatarEditor(QLabel):
    """Prévia circular com arraste para reposicionar e roda para zoom."""

    def __init__(self, parent: QWidget | None = None, size: int = 120) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        self.setScaledContents(True)
        self.setMouseTracking(True)
        self.setCursor(Qt.ArrowCursor)
        self._path = ""
        self._initials = "?"
        self._focus_x = 0.5
        self._focus_y = 0.5
        self._zoom = 1.0
        self._drag_start: QPoint | None = None
        self._drag_focus = (0.5, 0.5)

    @property
    def framing(self) -> tuple[float, float, float]:
        return self._focus_x, self._focus_y, self._zoom

    def set_initials(self, name: str) -> None:
        self._path = ""
        self._initials = name or "?"
        self.setCursor(Qt.ArrowCursor)
        self._render()

    @property
    def photo_path(self) -> str:
        return self._path

    def set_photo(
        self,
        path: str,
        focus_x: float | None = None,
        focus_y: float | None = None,
        zoom: float | None = None,
        reset: bool = False,
    ) -> None:
        if reset or path != self._path or focus_x is not None:
            self._focus_x = 0.5 if focus_x is None else float(focus_x)
            self._focus_y = 0.5 if focus_y is None else float(focus_y)
            self._zoom = 1.0 if zoom is None else float(zoom)
            self._focus_x = max(0.0, min(1.0, self._focus_x))
            self._focus_y = max(0.0, min(1.0, self._focus_y))
            self._zoom = max(1.0, min(4.0, self._zoom))
        self._path = path
        self.setCursor(Qt.OpenHandCursor)
        self._render()

    def reset_framing(self) -> None:
        self._focus_x = 0.5
        self._focus_y = 0.5
        self._zoom = 1.0
        self._render()

    def _render(self) -> None:
        if self._path:
            self.setPixmap(
                avatar_photo(
                    self._path,
                    self.width(),
                    max(2.0, self.devicePixelRatioF()),
                    self._focus_x,
                    self._focus_y,
                    self._zoom,
                )
            )
            return
        theme = get_theme()
        self.setPixmap(
            avatar_pixmap(
                self._initials,
                self.width(),
                theme.color("primary"),
                theme.color("info"),
                theme.color("on_primary"),
            )
        )

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._path and event.button() == Qt.LeftButton:
            self._drag_start = event.position().toPoint()
            self._drag_focus = (self._focus_x, self._focus_y)
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_start is not None and event.buttons() & Qt.LeftButton:
            pos = event.position().toPoint()
            dx = pos.x() - self._drag_start.x()
            dy = pos.y() - self._drag_start.y()
            span_x = max(1.0, self.width() * self._zoom)
            span_y = max(1.0, self.height() * self._zoom)
            self._focus_x = max(
                0.0, min(1.0, self._drag_focus[0] - dx / span_x)
            )
            self._focus_y = max(
                0.0, min(1.0, self._drag_focus[1] - dy / span_y)
            )
            self._render()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self._drag_start is not None:
            self._drag_start = None
            if self._path:
                self.setCursor(Qt.OpenHandCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: N802
        if self._path:
            delta = event.angleDelta().y()
            if delta:
                step = 0.1 if delta > 0 else -0.1
                self._zoom = max(1.0, min(4.0, self._zoom + step))
                self._render()
                event.accept()
                return
        super().wheelEvent(event)


class ProfileDialog(SheetDialog):
    """Edição de nome e foto do usuário."""

    def __init__(self, parent: QWidget | None, config: AppConfig) -> None:
        super().__init__(
            parent,
            "Perfil do usuário",
            "Ajuste o nome e o enquadramento da foto exibida no menu lateral.",
            580,
            470,
            min_width=520,
            min_height=400,
        )
        self.config = config
        self._picked_avatar: str | None = None
        self._remove_avatar = False

        preview_row = QHBoxLayout()
        preview_row.setSpacing(18)
        self.avatar = AvatarEditor(self, 120)
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

        framing_row = QHBoxLayout()
        framing_row.setSpacing(8)
        self.framing_hint = QLabel(
            "Arraste a foto para enquadrar · use a roda do mouse para zoom"
        )
        self.framing_hint.setObjectName("Faint")
        self.framing_hint.setWordWrap(True)
        framing_row.addWidget(self.framing_hint, 1)
        self.reset_frame_btn = ActionButton(
            "Centralizar", "image-filter-center-focus", "ghost", self, 15
        )
        self.reset_frame_btn.clicked.connect(self._reset_framing)
        framing_row.addWidget(self.reset_frame_btn)
        self.body.addLayout(framing_row)

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
        name = self.name_edit.text() or self.config.user_name
        if source:
            if self.avatar.photo_path != source:
                focus_x, focus_y, zoom = self.config.avatar_framing
                self.avatar.set_photo(source, focus_x, focus_y, zoom)
            else:
                self.avatar.set_photo(source)
            self.framing_hint.setVisible(True)
            self.reset_frame_btn.setVisible(True)
        else:
            self.avatar.set_initials(name)
            self.framing_hint.setVisible(False)
            self.reset_frame_btn.setVisible(False)

    def _reset_framing(self) -> None:
        self.avatar.reset_framing()

    def _choose_avatar(self) -> None:
        picker = ImagePickerDialog(self, self._picked_avatar or "")
        if picker.exec() == QDialog.Accepted and picker.selected_path:
            path = picker.selected_path
            self._picked_avatar = path
            self._remove_avatar = False
            self.avatar.set_photo(path, 0.5, 0.3, 1.0, reset=True)
            self._refresh_avatar()
        picker.deleteLater()

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
        focus_x, focus_y, zoom = self.avatar.framing
        self.config.set("user.avatar_focus_x", focus_x, save=False)
        self.config.set("user.avatar_focus_y", focus_y, save=False)
        self.config.set("user.avatar_zoom", zoom, save=False)
        self.config.save()
        self.accept()


class WarningsDialog(SheetDialog):
    """Resumo categorizado dos avisos sem expor caminhos completos."""

    CATEGORY_LABELS = {
        "permission_denied": "Permissão negada",
        "not_found": "Item removido durante a análise",
        "path_too_long": "Caminho longo demais",
        "io_error": "Erro de I/O",
    }
    OPERATION_LABELS = {
        "stat_root": "Ler raiz",
        "list_root": "Listar raiz",
        "iterate_dir": "Percorrer pasta",
        "list_dir": "Listar subpasta",
        "read_entry": "Ler item",
    }

    def __init__(self, parent: QWidget | None, result: ScanResult) -> None:
        super().__init__(
            parent,
            "Avisos da análise",
            "Itens que não puderam ser lidos por completo.",
            720,
            460,
            min_width=540,
            min_height=340,
        )
        self.result = result
        if result.errors == 1:
            summary_text = "1 item não pôde ser lido por completo."
        else:
            summary_text = (
                f"{result.errors} itens não puderam ser lidos por completo."
            )
        summary_text += (
            " A varredura continuou; os totais podem estar incompletos."
        )
        summary = QLabel(summary_text)
        summary.setObjectName("Muted")
        summary.setWordWrap(True)
        self.body.addWidget(summary)

        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["Categoria", "Operação", "Quantidade"])
        self.tree.setRootIsDecorated(False)
        self.tree.setIndentation(0)
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QAbstractItemView.NoSelection)
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        for warning in result.warnings:
            category = self.CATEGORY_LABELS.get(
                warning.category, warning.category
            )
            operation = self.OPERATION_LABELS.get(
                warning.operation, warning.operation
            )
            item = QTreeWidgetItem([category, operation, str(warning.count)])
            item.setTextAlignment(2, Qt.AlignRight | Qt.AlignVCenter)
            self.tree.addTopLevelItem(item)
        categorized = sum(warning.count for warning in result.warnings)
        if not result.warnings:
            self.tree.addTopLevelItem(
                QTreeWidgetItem(["Não categorizado", "-", str(result.errors)])
            )
        elif categorized < result.errors:
            self.tree.addTopLevelItem(
                QTreeWidgetItem(
                    [
                        "Não categorizado",
                        "-",
                        str(result.errors - categorized),
                    ]
                )
            )
        self.body.addWidget(self.tree, 1)

        note = QLabel(
            "Por privacidade, este resumo não inclui caminhos completos. "
            "O log registra categorias e hashes, não nomes de arquivos."
        )
        note.setObjectName("Faint")
        note.setWordWrap(True)
        self.body.addWidget(note)

        self.copy_btn = ActionButton("Copiar resumo", "content-copy", "ghost", self)
        self.copy_btn.clicked.connect(self._copy_summary)
        close_btn = ActionButton("Fechar", "close", "soft", self)
        close_btn.clicked.connect(self.accept)
        self.footer.addStretch(1)
        self.footer.addWidget(self.copy_btn)
        self.footer.addWidget(close_btn)

    def summary_text(self) -> str:
        lines = [
            "DiskPilot — avisos da análise",
            f"Total: {self.result.errors}",
        ]
        for warning in self.result.warnings:
            category = self.CATEGORY_LABELS.get(
                warning.category, warning.category
            )
            operation = self.OPERATION_LABELS.get(
                warning.operation, warning.operation
            )
            lines.append(f"- {category} ({operation}): {warning.count}")
        categorized = sum(
            warning.count for warning in self.result.warnings
        )
        if not self.result.warnings:
            lines.append(f"- Não categorizado: {self.result.errors}")
        elif categorized < self.result.errors:
            lines.append(
                f"- Não categorizado: {self.result.errors - categorized}"
            )
        lines.append("")
        lines.append(
            "Caminhos completos não são armazenados por privacidade."
        )
        return "\n".join(lines)

    def _copy_summary(self) -> None:
        copy_to_clipboard(self.summary_text())
        self.copy_btn.setText("Resumo copiado")
