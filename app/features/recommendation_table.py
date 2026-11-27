"""Tabela ordenável e pesquisável das recomendações."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QMenu,
    QTableView,
)

from appshell.icons import icon
from appshell.theme import get_theme
from appshell.utils import (
    copy_to_clipboard,
    format_bytes,
    format_datetime,
    format_number,
    open_in_explorer,
)

from ..services.model import Suggestion


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text))
    return "".join(
        char for char in normalized if not unicodedata.combining(char)
    ).casefold()


@dataclass(slots=True)
class RecommendationRow:
    suggestion: Suggestion
    path: str
    display_path: str
    name: str
    size: int | None
    percent: float
    items: int | None
    mtime: float
    kind: str
    confidence: str


class RecommendationTableModel(QAbstractTableModel):
    COLUMNS = (
        "Sugestão",
        "Nome",
        "Caminho",
        "Tamanho",
        "%",
        "Itens",
        "Modificado em",
        "Confiança",
    )
    HEADER_TIPS = {
        2: "Caminho abreviado; o caminho completo aparece no tooltip e na cópia.",
        3: "Tamanho lógico do item; a ordenação é numérica.",
        4: "% do total — participação no total da análise.",
        5: "Arquivos e pastas contidos no item.",
        6: "Data da última modificação.",
        7: "Confiança da recomendação: segura ou para revisão.",
    }

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: list[RecommendationRow] = []

    def set_rows(self, rows: list[RecommendationRow]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def row_at(self, index: int) -> RecommendationRow | None:
        if 0 <= index < len(self._rows):
            return self._rows[index]
        return None

    def rows(self) -> list[RecommendationRow]:
        return list(self._rows)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.COLUMNS)

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole
    ) -> Any:
        if orientation == Qt.Horizontal:
            if role == Qt.DisplayRole and 0 <= section < len(self.COLUMNS):
                return self.COLUMNS[section]
            if role == Qt.ToolTipRole:
                return self.HEADER_TIPS.get(section)
        return None

    def data(  # noqa: N802
        self, index: QModelIndex, role: int = Qt.DisplayRole
    ) -> Any:
        if not index.isValid():
            return None
        row = self.row_at(index.row())
        if row is None:
            return None
        column = index.column()
        safe = row.confidence == "safe"
        if role == Qt.DisplayRole:
            if column == 0:
                return row.suggestion.title
            if column == 1:
                return row.name
            if column == 2:
                return row.display_path
            if column == 3:
                return format_bytes(row.size) if row.size is not None else "—"
            if column == 4:
                return f"{row.percent:.1f}%" if row.size is not None else "—"
            if column == 5:
                return format_number(row.items) if row.items is not None else "—"
            if column == 6:
                return format_datetime(row.mtime) if row.mtime else "—"
            if column == 7:
                return "Segura" if safe else "Revisar"
        if role == Qt.UserRole:
            if column == 3:
                return row.size if row.size is not None else -1
            if column == 4:
                return row.percent
            if column == 5:
                return row.items if row.items is not None else -1
            if column == 6:
                return row.mtime
            if column == 7:
                return row.confidence
            return self.data(index, Qt.DisplayRole)
        if role == Qt.ToolTipRole:
            details = [
                row.path,
                row.suggestion.title,
                row.suggestion.description,
            ]
            if row.kind:
                details.append(f"Tipo: {row.kind}")
            if row.suggestion.note:
                details.append(row.suggestion.note)
            return "\n".join(details)
        if role == Qt.TextAlignmentRole and column in (3, 4, 5):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.TextAlignmentRole and column == 7:
            return int(Qt.AlignCenter)
        if role == Qt.ForegroundRole and column == 7:
            theme = get_theme()
            return QColor(theme.color("success" if safe else "warn"))
        if role == Qt.DecorationRole and column == 0:
            theme = get_theme()
            return icon(
                row.suggestion.icon,
                theme.color("success" if safe else "warn"),
                16,
            )
        if role == Qt.DecorationRole and column == 1 and row.kind:
            theme = get_theme()
            return icon(
                "folder" if row.kind == "Pasta" else "file",
                theme.color("muted"),
                15,
            )
        return None


class RecommendationFilterProxy(QSortFilterProxyModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._query = ""
        self._confidence = "all"

    def _invalidate(self) -> None:
        self.invalidate()

    def set_query(self, query: str) -> None:
        self._query = _fold(query.strip())
        self._invalidate()

    def set_confidence(self, confidence: str) -> None:
        self._confidence = confidence if confidence in {"safe", "review"} else "all"
        self._invalidate()

    def filterAcceptsRow(  # noqa: N802
        self, source_row: int, source_parent: QModelIndex
    ) -> bool:
        model = self.sourceModel()
        if not isinstance(model, RecommendationTableModel):
            return True
        row = model.row_at(source_row)
        if row is None:
            return False
        if self._confidence != "all" and row.confidence != self._confidence:
            return False
        if not self._query:
            return True
        haystack = _fold(
            " ".join(
                (
                    row.suggestion.title,
                    row.suggestion.description,
                    row.suggestion.note,
                    row.name,
                    row.path,
                    row.confidence,
                )
            )
        )
        return self._query in haystack


class RecommendationTable(QTableView):
    statusMessage = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("RecommendationTable")
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.ElideMiddle)
        self.setSortingEnabled(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.verticalHeader().setVisible(False)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self.doubleClicked.connect(self._open_index)
        self.activated.connect(self._open_index)
        shortcut = QShortcut(QKeySequence.Copy, self)
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(self.copy_selected)
        self.setAccessibleName("Recomendações: caminhos para revisão")
        self._configure_header()

    def setModel(self, model) -> None:  # noqa: N802
        super().setModel(model)
        # QTableView recria as seções ao receber um modelo; reaplicamos os
        # tamanhos depois disso para não exibir todas as colunas com 100 px.
        self._configure_header()

    def _configure_header(self) -> None:
        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        header.setSectionResizeMode(6, QHeaderView.Fixed)
        header.setSectionResizeMode(7, QHeaderView.Fixed)
        self.setColumnWidth(0, 220)
        self.setColumnWidth(1, 180)
        self.setColumnWidth(3, 110)
        self.setColumnWidth(4, 60)
        self.setColumnWidth(5, 70)
        self.setColumnWidth(6, 140)
        self.setColumnWidth(7, 100)

    def _source_row(self, index: QModelIndex) -> RecommendationRow | None:
        if not index.isValid():
            return None
        proxy = self.model()
        if proxy is None:
            return None
        source = proxy.mapToSource(index) if hasattr(proxy, "mapToSource") else index
        source_model = getattr(proxy, "sourceModel", lambda: None)()
        if isinstance(source_model, RecommendationTableModel):
            return source_model.row_at(source.row())
        return None

    def _open_index(self, index: QModelIndex) -> None:
        row = self._source_row(index)
        if row is None:
            return
        if open_in_explorer(row.path, select=True):
            self.statusMessage.emit("Local aberto no Explorer.")
        else:
            self.statusMessage.emit("Não foi possível abrir o local no Explorer.")

    def _selected_rows(self) -> list[RecommendationRow]:
        rows: list[RecommendationRow] = []
        for index in self.selectionModel().selectedRows():
            row = self._source_row(index)
            if row is not None:
                rows.append(row)
        if not rows:
            row = self._source_row(self.currentIndex())
            if row is not None:
                rows.append(row)
        return rows

    def copy_selected(self) -> None:
        rows = self._selected_rows()
        if not rows:
            self.statusMessage.emit("Nenhum caminho selecionado.")
            return
        copy_to_clipboard("\n".join(row.path for row in rows))
        self.statusMessage.emit(
            f"{len(rows)} caminho(s) copiado(s)."
        )

    def copy_current(self) -> None:
        row = self._source_row(self.currentIndex())
        if row is None:
            self.statusMessage.emit("Nenhum caminho selecionado.")
            return
        copy_to_clipboard(row.path)
        self.statusMessage.emit("Caminho copiado.")

    def copy_all(self) -> None:
        proxy = self.model()
        source = proxy.sourceModel() if hasattr(proxy, "sourceModel") else proxy
        if not isinstance(source, RecommendationTableModel):
            return
        rows = source.rows()
        if not rows:
            self.statusMessage.emit("Nenhum caminho para copiar.")
            return
        copy_to_clipboard("\n".join(row.path for row in rows))
        self.statusMessage.emit(f"{len(rows)} caminho(s) copiado(s).")

    def _context_menu(self, pos) -> None:
        index = self.indexAt(pos)
        menu = QMenu(self)
        open_action = menu.addAction("Abrir local no Explorer")
        copy_action = menu.addAction("Copiar caminho")
        selected_action = menu.addAction("Copiar selecionados")
        menu.addSeparator()
        all_action = menu.addAction("Copiar todos os caminhos")
        chosen = menu.exec(self.viewport().mapToGlobal(pos))
        if chosen == open_action:
            self._open_index(index)
        elif chosen == copy_action:
            row = self._source_row(index)
            if row is not None:
                copy_to_clipboard(row.path)
                self.statusMessage.emit("Caminho copiado.")
        elif chosen == selected_action:
            self.copy_selected()
        elif chosen == all_action:
            self.copy_all()
        menu.deleteLater()
