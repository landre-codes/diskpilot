"""Árvore de arquivos com tamanhos aninhados, busca, filtros e ordenação."""

from __future__ import annotations

import heapq
import logging
import os
import unicodedata
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QModelIndex,
    QObject,
    QRect,
    QRectF,
    QRunnable,
    QSize,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QKeySequence,
    QPainter,
    QPen,
    QShortcut,
)
from PySide6.QtWidgets import (
    QHeaderView,
    QMenu,
    QStyle,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QTreeWidget,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QWidget,
)

from shiboken6 import isValid

from appshell.icons import file_icon, icon
from ...services.index_store import SearchIndex
from ...services.model import Node, ScanResult
from appshell.tasks import Task, TaskCancelled, TaskRunner
from appshell.theme import get_theme
from appshell.utils import (
    cached_file_author,
    cached_file_owner,
    copy_to_clipboard,
    file_author,
    file_owner,
    format_datetime,
    format_number,
    format_size,
    normalize_path,
    open_in_explorer,
)


NODE_ROLE = Qt.UserRole + 10
PCT_ROLE = Qt.UserRole + 11
SIZE_ROLE = Qt.UserRole + 12
POPULATED_ROLE = Qt.UserRole + 13
PLACEHOLDER_ROLE = Qt.UserRole + 14

COL_NAME = 0
COL_SIZE = 1
COL_PCT = 2
COL_ITEMS = 3
COL_MTIME = 4
COL_AUTHOR = 5
COL_OWNER = 6
COL_KIND = 7
COL_PATH = 8

COLUMN_MINIMUMS = {
    COL_NAME: 250,
    COL_SIZE: 124,
    COL_PCT: 80,
    COL_ITEMS: 100,
    COL_MTIME: 140,
    COL_AUTHOR: 140,
    COL_OWNER: 200,
    COL_KIND: 100,
    COL_PATH: 600,
}
COLUMN_WIDTHS = {
    COL_SIZE: 124,
    COL_PCT: 80,
    COL_ITEMS: 100,
    COL_MTIME: 140,
    COL_AUTHOR: 140,
    COL_OWNER: 200,
    COL_KIND: 100,
    COL_PATH: 600,
}


class _MetadataSignals(QObject):
    resolved = Signal(str, str, str)


class _MetadataJob(QRunnable):
    """Consulta autor e proprietário fora da thread da interface."""

    def __init__(self, path: str, signals: _MetadataSignals) -> None:
        super().__init__()
        self.path = path
        self.signals = signals

    def run(self) -> None:
        author = ""
        owner = ""
        try:
            author = file_author(self.path)
        except Exception:
            pass
        try:
            owner = file_owner(self.path)
        except Exception:
            pass
        try:
            self.signals.resolved.emit(self.path, author, owner)
        except RuntimeError:
            # A árvore pode ter sido fechada enquanto a consulta terminava.
            pass

MAX_CHILDREN = 1200
MAX_RENDERED = 5000
MAX_RESULT_MATCHES = 5000
EXPAND_BATCH = 120
EXPAND_DEBOUNCE_MS = 60
MB = 1024 * 1024
GB = 1024 * MB

logger = logging.getLogger("diskpilot.tree")


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _node_matches(node: Node, query: str, filter_key: str) -> bool:
    if query:
        haystack = _fold(node.name)
        for token in query.split():
            if token not in haystack:
                return False
    if filter_key == "folders":
        return node.is_dir
    if filter_key == "files":
        return not node.is_dir
    if filter_key == "large100":
        return not node.is_dir and node.size >= 100 * MB
    if filter_key == "large1g":
        return not node.is_dir and node.size >= GB
    return True


def _sorted_children(
    node: Node, sort_key: str, limit: int | None = None
) -> list[Node]:
    children = node.ensure_children()
    if sort_key == "size_asc":
        func = lambda n: (n.size, _fold(n.name))
        if limit is not None:
            return heapq.nsmallest(limit, children, key=func)
        return sorted(children, key=func)
    if sort_key == "name_asc":
        func = lambda n: (not n.is_dir, _fold(n.name))
        if limit is not None:
            return heapq.nsmallest(limit, children, key=func)
        return sorted(children, key=func)
    if sort_key == "name_desc":
        func = lambda n: (n.is_dir, _fold(n.name))
        if limit is not None:
            return heapq.nlargest(limit, children, key=func)
        names = sorted(children, key=lambda n: _fold(n.name), reverse=True)
        return sorted(names, key=lambda n: not n.is_dir)
    if sort_key == "recent":
        func = lambda n: n.mtime
        if limit is not None:
            return heapq.nlargest(limit, children, key=func)
        return sorted(children, key=func, reverse=True)
    func = lambda n: (n.size, _fold(n.name))
    if limit is not None:
        return heapq.nlargest(limit, children, key=func)
    return sorted(children, key=func, reverse=True)


@dataclass(slots=True)
class _FilterResult:
    generation: int
    matches: int
    included: set[int]
    visited: int
    limited: bool
    roots: list[Node] | None = None


class _FilterTask(Task):
    """Percorre a árvore completa fora da GUI e guarda só os primeiros matches."""

    def __init__(
        self,
        result: ScanResult,
        query: str,
        filter_key: str,
        sort_key: str,
        generation: int,
    ) -> None:
        super().__init__()
        self.result = result
        self.query = query
        self.filter_key = filter_key
        self.sort_key = sort_key
        self.generation = generation

    def execute(self) -> _FilterResult:
        included: set[int] = set()
        matches = 0
        stored = 0
        visited = 0
        for root in self.result.roots:
            stack: list[tuple[Node, bool]] = [(root, False)]
            path: list[Node] = []
            while stack:
                if self.cancel.is_set():
                    raise TaskCancelled()
                node, exiting = stack.pop()
                if exiting:
                    path.pop()
                    continue
                path.append(node)
                visited += 1
                if _node_matches(node, self.query, self.filter_key):
                    matches += 1
                    if stored < MAX_RESULT_MATCHES:
                        for ancestor in path:
                            included.add(id(ancestor))
                        stored += 1
                stack.append((node, True))
                for child in reversed(
                    _sorted_children(node, self.sort_key)
                ):
                    stack.append((child, False))
        return _FilterResult(
            generation=self.generation,
            matches=matches,
            included=included,
            visited=visited,
            limited=matches > stored,
        )


class _IndexFilterTask(Task):
    """Usa o SQLite para achar os caminhos e a árvore só para montar ancestrais."""

    def __init__(
        self,
        result: ScanResult,
        index: SearchIndex,
        query: str,
        filter_key: str,
        sort_key: str,
        generation: int,
    ) -> None:
        super().__init__()
        self.result = result
        self.index = index
        self.query = query
        self.filter_key = filter_key
        self.sort_key = sort_key
        self.generation = generation

    def execute(self) -> _FilterResult:
        hits = self.index.search(
            self.query,
            self.filter_key,
            self.sort_key,
            limit=MAX_RESULT_MATCHES,
            cancel=self.cancel,
        )
        if self.result.lazy and getattr(self.result, "index", None) is not None:
            paths: set[str] = set()
            for hit in hits.paths:
                normalized = normalize_path(hit)
                paths.add(normalized)
                parent = Path(normalized).parent
                while True:
                    paths.add(str(parent))
                    if parent.parent == parent:
                        break
                    parent = parent.parent
            for root in self.result.roots:
                paths.add(normalize_path(root.path))
            nodes = self.index.nodes_by_paths(paths)
            by_path = {normalize_path(node.path): node for node in nodes}
            root_order = {
                normalize_path(root.path): index
                for index, root in enumerate(self.result.roots)
            }
            partial_roots: list[Node] = []
            for node in nodes:
                normalized = normalize_path(node.path)
                parent_node = by_path.get(str(Path(normalized).parent))
                if parent_node is not None and parent_node is not node:
                    parent_node.children.append(node)
                elif normalized in root_order:
                    partial_roots.append(node)
            partial_roots.sort(
                key=lambda node: root_order.get(
                    normalize_path(node.path), len(root_order)
                )
            )
            return _FilterResult(
                generation=self.generation,
                matches=hits.matches,
                included=set(),
                visited=len(nodes),
                limited=hits.matches > len(hits.paths),
                roots=partial_roots,
            )
        target = {normalize_path(path) for path in hits.paths}
        included: set[int] = set()
        visited = 0
        for root in self.result.roots:
            stack: list[tuple[Node, bool]] = [(root, False)]
            path: list[Node] = []
            while stack:
                if self.cancel.is_set():
                    raise TaskCancelled()
                node, exiting = stack.pop()
                if exiting:
                    path.pop()
                    continue
                path.append(node)
                visited += 1
                if normalize_path(node.path) in target:
                    for ancestor in path:
                        included.add(id(ancestor))
                stack.append((node, True))
                for child in reversed(node.children):
                    stack.append((child, False))
        return _FilterResult(
            generation=self.generation,
            matches=hits.matches,
            included=included,
            visited=visited,
            limited=hits.matches > len(hits.paths),
        )


class SizeBarDelegate(QStyledItemDelegate):
    """Coluna de tamanho com micro barra proporcional e alinhamento à direita."""

    def __init__(self, parent: QWidget | None = None, unit: str = "auto") -> None:
        super().__init__(parent)
        self.unit = unit

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        theme = get_theme()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        rect = option.rect
        if option.state & QStyle.State_Selected:
            bg = theme.qcolor("primary", 46)
        elif option.state & QStyle.State_MouseOver:
            bg = QColor(theme.color("surface_2"))
        elif option.features & QStyleOptionViewItem.Alternate:
            bg = QColor(theme.color("surface_2"))
            bg.setAlpha(110)
        else:
            bg = QColor(theme.color("surface"))
        painter.fillRect(rect, bg)

        size = index.data(SIZE_ROLE) or 0
        pct = float(index.data(PCT_ROLE) or 0.0)
        text = format_size(size, self.unit)

        track = QRectF(rect.left() + 9, rect.bottom() - 5, max(10, rect.width() - 20), 2.5)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(theme.color("border")))
        painter.drawRoundedRect(track, 1.25, 1.25)
        if pct > 0:
            fill = QRectF(track.left(), track.top(), max(2.0, track.width() * min(1.0, pct)), track.height())
            painter.setBrush(theme.qcolor("primary", 150))
            painter.drawRoundedRect(fill, 1.25, 1.25)

        color = QColor(theme.color("text" if size else "faint"))
        painter.setPen(color)
        f = QFont("Segoe UI")
        f.setPixelSize(theme.fs(12))
        f.setWeight(QFont.DemiBold if size else QFont.Normal)
        painter.setFont(f)
        painter.drawText(
            rect.adjusted(6, 0, -9, -4),
            Qt.AlignVCenter | Qt.AlignRight,
            text,
        )
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(130, 32)


class FileTree(QTreeWidget):
    countChanged = Signal(int, int)  # correspondências (-1 = sem filtro), exibidos
    statusMessage = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("FileTree")
        self.setColumnCount(9)
        self.setHeaderLabels(
            [
                "Nome",
                "Tamanho",
                "% do pai",
                "Itens",
                "Modificado",
                "Autor",
                "Proprietário",
                "Tipo",
                "Caminho completo",
            ]
        )
        self.setAlternatingRowColors(True)
        self.setUniformRowHeights(True)
        self.setRootIsDecorated(True)
        self.setIndentation(18)
        self.setAnimated(False)
        self.setExpandsOnDoubleClick(False)
        self.setSortingEnabled(False)
        self.setMouseTracking(True)
        self.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        copy_shortcut = QShortcut(QKeySequence.Copy, self)
        copy_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        copy_shortcut.activated.connect(self._copy_rows)
        self.itemExpanded.connect(self._on_expanded)
        self.itemDoubleClicked.connect(self._on_double_clicked)
        header = self.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(COL_NAME, QHeaderView.Interactive)
        for column, width in (
            (COL_SIZE, COLUMN_WIDTHS[COL_SIZE]),
            (COL_PCT, COLUMN_WIDTHS[COL_PCT]),
            (COL_ITEMS, COLUMN_WIDTHS[COL_ITEMS]),
            (COL_MTIME, COLUMN_WIDTHS[COL_MTIME]),
            (COL_KIND, COLUMN_WIDTHS[COL_KIND]),
        ):
            header.setSectionResizeMode(column, QHeaderView.Fixed)
            self.setColumnWidth(column, width)
        header.setSectionResizeMode(COL_AUTHOR, QHeaderView.Interactive)
        self.setColumnWidth(COL_AUTHOR, COLUMN_WIDTHS[COL_AUTHOR])
        header.setSectionResizeMode(COL_OWNER, QHeaderView.Interactive)
        self.setColumnWidth(COL_OWNER, COLUMN_WIDTHS[COL_OWNER])
        header.setSectionResizeMode(COL_PATH, QHeaderView.Interactive)
        self.setColumnWidth(COL_PATH, COLUMN_WIDTHS[COL_PATH])
        header.setMinimumSectionSize(90)
        header.setHighlightSections(False)
        for column in (COL_SIZE, COL_PCT, COL_ITEMS, COL_MTIME):
            self.headerItem().setTextAlignment(column, Qt.AlignRight | Qt.AlignVCenter)
        for column in (COL_AUTHOR, COL_OWNER, COL_KIND, COL_PATH):
            self.headerItem().setTextAlignment(column, Qt.AlignLeft | Qt.AlignVCenter)
        self.headerItem().setToolTip(
            COL_AUTHOR,
            "Autor do documento, obtido dos metadados. "
            "Contas de sistema são omitidas.",
        )
        self.headerItem().setToolTip(
            COL_OWNER,
            "Proprietário NTFS/ACL: usuário ou grupo dono do arquivo ou pasta. "
            "Contas de sistema e grupos internos são omitidos.",
        )
        self.setTextElideMode(Qt.ElideMiddle)
        self.setColumnHidden(COL_PATH, True)
        self._path_visible = False
        self._path_content_width = COLUMN_MINIMUMS[COL_PATH]
        self._fitting_columns = False
        header.sectionResized.connect(self._on_section_resized)
        self._size_delegate = SizeBarDelegate(self)
        self.setItemDelegateForColumn(1, self._size_delegate)
        self._result: ScanResult | None = None
        self._search_index: SearchIndex | None = None
        self._query = ""
        self._filter = "all"
        self._sort = "size_desc"
        self._unit = "auto"
        self._building = False
        self._matches = -1
        self._shown = 0
        self._expand_queue: deque[tuple[QTreeWidgetItem, Node]] = deque()
        self._expand_active: list[Any] | None = None
        self._expand_all_budget = 0
        self._restore_paths: set[str] = set()
        self._expand_timer = QTimer(self)
        self._expand_timer.setSingleShot(True)
        self._expand_timer.setInterval(EXPAND_DEBOUNCE_MS)
        self._expand_timer.timeout.connect(self._expand_step)
        self._count_timer = QTimer(self)
        self._count_timer.setSingleShot(True)
        self._count_timer.setInterval(30)
        self._count_timer.timeout.connect(self._refresh_visible_count)
        self.itemExpanded.connect(self._schedule_visible_count)
        self.itemCollapsed.connect(self._schedule_visible_count)
        self._metadata_pool = QThreadPool(self)
        self._metadata_pool.setMaxThreadCount(4)
        self._metadata_signals = _MetadataSignals()
        self._metadata_signals.resolved.connect(self._metadata_resolved)
        self._metadata_pending: dict[str, list[QTreeWidgetItem]] = {}
        self._filter_runner = TaskRunner(self, max_threads=1)
        self._filter_runner.finished.connect(self._filter_finished)
        self._filter_runner.failed.connect(self._filter_failed)
        self._filter_generation = 0
        get_theme().changed.connect(self._refresh_visuals)

    # ------------------------------------------------------------- galhos
    def _depth_of(self, index: QModelIndex) -> int:
        depth = 0
        parent = index.parent()
        while parent.isValid():
            depth += 1
            parent = parent.parent()
        return depth

    def _expander_x(self, index: QModelIndex) -> int:
        step = self.indentation()
        return self._depth_of(index) * step + step // 2

    def drawBranches(self, painter: QPainter, rect: QRect, index: QModelIndex) -> None:  # noqa: N802
        """Desenha as guias de hierarquia e as setas de expandir/recolher.

        O estilo nativo deixa de desenhar a seta quando o QSS estiliza
        ``::branch``; por isso o indicador é desenhado aqui, com a cor do tema.
        """
        if not index.isValid():
            return
        model = self.model()
        theme = get_theme()
        step = self.indentation()
        depth = self._depth_of(index)
        center_x = depth * step + step // 2
        center_y = rect.center().y() + 1
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        guide_pen = QPen(theme.qcolor("border_strong", 130))
        guide_pen.setWidth(1)
        painter.setPen(guide_pen)
        for level in range(depth):
            x = level * step + step // 2
            painter.drawLine(x, rect.top(), x, rect.bottom())

        if model is not None and model.hasChildren(index):
            expanded = self.isExpanded(index)
            pen = QPen(theme.qcolor("primary" if expanded else "muted"))
            pen.setWidthF(1.9)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            size = 4
            if expanded:
                painter.drawLine(center_x - size, center_y - 2, center_x, center_y + 2)
                painter.drawLine(center_x, center_y + 2, center_x + size, center_y - 2)
            else:
                painter.drawLine(center_x - 2, center_y - size, center_x + 2, center_y)
                painter.drawLine(center_x + 2, center_y, center_x - 2, center_y + size)
        painter.restore()

    def _on_expander(self, pos, index: QModelIndex) -> bool:
        if not index.isValid() or self.model() is None:
            return False
        if not self.model().hasChildren(index):
            return False
        return abs(pos.x() - self._expander_x(index)) <= 10

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            pos = event.position().toPoint()
            index = self.indexAt(pos)
            if self._on_expander(pos, index):
                self.setExpanded(index, not self.isExpanded(index))
                event.accept()
                return
        super().mousePressEvent(event)

    # ---------------------------------------------------------------- cópia
    def _size_text(self, item: QTreeWidgetItem) -> str:
        value = item.data(1, SIZE_ROLE)
        try:
            size = int(value or 0)
        except (TypeError, ValueError):
            size = 0
        return format_size(size, self._unit)

    def _row_text(self, item: QTreeWidgetItem) -> str:
        node = item.data(0, NODE_ROLE)
        columns = [
            item.text(COL_NAME),
            self._size_text(item),
            item.text(COL_PCT),
            item.text(COL_ITEMS),
            item.text(COL_MTIME),
            item.text(COL_AUTHOR),
            item.text(COL_OWNER),
            item.text(COL_KIND),
        ]
        if node is not None:
            columns.append(node.path)
        return "\t".join(columns)

    def _copy_rows(self) -> None:
        items = [
            item for item in self.selectedItems() if item.data(0, NODE_ROLE) is not None
        ]
        if not items:
            current = self.currentItem()
            if current is not None and current.data(0, NODE_ROLE) is not None:
                items = [current]
        if not items:
            return
        copy_to_clipboard("\n".join(self._row_text(item) for item in items))
        self.statusMessage.emit(
            f"{len(items)} linha(s) copiada(s): Nome, Tamanho, %, Itens, "
            "Modificado, Autor, Proprietário, Tipo, Caminho."
        )

    def _copy_size(self, item: QTreeWidgetItem) -> None:
        copy_to_clipboard(self._size_text(item))
        self.statusMessage.emit("Tamanho copiado para a área de transferência.")

    def _copy_path(self, item: QTreeWidgetItem) -> None:
        node = item.data(0, NODE_ROLE)
        if node is not None:
            copy_to_clipboard(node.path)
            self.statusMessage.emit("Caminho copiado para a área de transferência.")

    # -------------------------------------------------------------- configuração
    def set_result(self, result: ScanResult | None) -> None:
        self._result = result
        self._search_index = (
            result.index
            if result is not None and getattr(result, "lazy", False)
            else None
        )
        self.rebuild()

    def set_search_index(self, index: SearchIndex | None) -> None:
        """Troca o backend de busca; ``None`` volta ao filtro em memória."""
        if self._search_index is index:
            return
        self._search_index = index
        if self._result is not None and (self._query or self._filter != "all"):
            self.rebuild()

    def set_path_visible(self, visible: bool) -> None:
        self._path_visible = bool(visible)
        self.setColumnHidden(COL_PATH, not self._path_visible)
        if self._path_visible:
            self._update_path_content_width()
        self._fit_columns()

    def _update_path_content_width(self) -> None:
        if not self._path_visible:
            return
        metrics = self.fontMetrics()
        width = self._path_content_width
        iterator = QTreeWidgetItemIterator(self)
        while iterator.value():
            item = iterator.value()
            text = item.text(COL_PATH)
            if text:
                width = max(width, metrics.horizontalAdvance(text) + 28)
            iterator += 1
        self._path_content_width = max(COLUMN_MINIMUMS[COL_PATH], width)

    def _fit_columns(self) -> None:
        """Distribui a largura restante para Nome, respeitando os mínimos."""
        viewport = max(1, self.viewport().width())
        fixed = sum(
            self.columnWidth(column)
            for column in range(COL_SIZE, COL_PATH)
            if not self.isColumnHidden(column)
        )
        path_width = 0
        if self._path_visible:
            path_width = max(
                COLUMN_MINIMUMS[COL_PATH],
                self._path_content_width,
                self.columnWidth(COL_PATH),
            )
        available = viewport - fixed - path_width
        name_width = max(COLUMN_MINIMUMS[COL_NAME], available)
        self._fitting_columns = True
        try:
            self.setColumnWidth(COL_NAME, name_width)
            if self._path_visible:
                self.setColumnWidth(COL_PATH, path_width)
        finally:
            self._fitting_columns = False

    def _on_section_resized(self, logical: int, _old: int, new: int) -> None:
        if self._fitting_columns or self.isColumnHidden(logical):
            return
        minimum = COLUMN_MINIMUMS.get(logical, 0)
        if new >= minimum:
            return
        self._fitting_columns = True
        try:
            self.setColumnWidth(logical, minimum)
        finally:
            self._fitting_columns = False

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._fit_columns()

    def set_query(self, query: str) -> None:
        self._query = _fold(query.strip())
        self.rebuild()

    def set_filter(self, key: str) -> None:
        self._filter = key
        self.rebuild()

    def set_sort(self, key: str) -> None:
        self._sort = key
        self.rebuild()

    def set_unit(self, unit: str) -> None:
        unit = unit if unit in {"KB", "MB", "GB", "TB"} else "auto"
        self._unit = unit
        self._size_delegate.unit = unit
        self.headerItem().setText(
            1, "Tamanho" if unit == "auto" else f"Tamanho ({unit})"
        )
        iterator = QTreeWidgetItemIterator(self)
        while iterator.value():
            item = iterator.value()
            node = item.data(0, NODE_ROLE)
            if isinstance(node, Node):
                item.setText(1, format_size(node.size, unit))
                item.setToolTip(0, self._node_tooltip(node))
            iterator += 1
        self.viewport().update()

    @property
    def matches(self) -> int:
        return self._matches

    @property
    def shown(self) -> int:
        return self._shown

    def expand_all_bounded(self, max_items: int = 2200) -> bool:
        """Expande em largura, em lotes, sem materializar a árvore inteira."""
        if self._result is None:
            return False
        self._expand_all_budget = max_items
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if self._node_at(item) is None:
                continue
            if item.isExpanded() and item.data(0, POPULATED_ROLE) is True:
                self._expand_all_children(item)
            else:
                item.setExpanded(True)
        return False

    def _restore_pending_children(self, item: QTreeWidgetItem) -> None:
        if not self._restore_paths:
            return
        node = self._node_at(item)
        if node is not None:
            self._restore_paths.discard(normalize_path(node.path))
        for i in range(item.childCount()):
            child = item.child(i)
            child_node = self._node_at(child)
            if child_node is None:
                continue
            key = normalize_path(child_node.path)
            if key in self._restore_paths:
                self._restore_paths.discard(key)
                child.setExpanded(True)

    def _expand_all_children(self, item: QTreeWidgetItem) -> None:
        # Quadros (item, próximo filho) preservam a ordem da visita recursiva
        # sem consumir a pilha do Python.
        stack: list[tuple[QTreeWidgetItem, int]] = [(item, 0)]
        while stack and self._expand_all_budget > 0:
            current, index = stack[-1]
            if index >= current.childCount():
                stack.pop()
                continue
            stack[-1] = (current, index + 1)
            child = current.child(index)
            node = self._node_at(child)
            if node is None or not node.is_dir:
                continue
            if child.isExpanded():
                if child.data(0, POPULATED_ROLE) is True:
                    stack.append((child, 0))
                continue
            child.setExpanded(True)
            self._expand_all_budget -= 1
            if self._expand_all_budget <= 0:
                return

    def _cancel_pending_expands(self) -> None:
        self._expand_timer.stop()
        self._expand_queue.clear()
        self._expand_active = None
        self._expand_all_budget = 0
        self._restore_paths.clear()

    def rebuild(self) -> None:
        self._cancel_pending_expands()
        self._path_content_width = 600
        expanded = self._expanded_paths()
        self._restore_paths = set(expanded)
        self._filter_generation += 1
        self._filter_runner.cancel()
        self.setUpdatesEnabled(False)
        self._building = True
        self.clear()
        self._metadata_pending.clear()
        self._matches = -1
        self._shown = 0
        if self._result is None:
            self._building = False
            self.setUpdatesEnabled(True)
            self.countChanged.emit(0, 0)
            return
        filtered = bool(self._query) or self._filter != "all"
        if filtered:
            self._building = False
            self.setUpdatesEnabled(True)
            self._start_filter()
            return
        total = self._result.total_size or 1
        for root in self._result.roots:
            item = self._create_item(None, root, total, is_root=True, lazy=True)
            self.addTopLevelItem(item)
        self._building = False
        for i in range(self.topLevelItemCount()):
            self._restore_expanded(self.topLevelItem(i), expanded)
        self._matches = -1
        self._shown = self._count_items()
        self.countChanged.emit(-1, self._shown)
        self._building = False
        self.setUpdatesEnabled(True)
        self.viewport().update()
        self._fit_columns()
        self._schedule_visible_count()

    def _expanded_paths(self) -> set[str]:
        paths: set[str] = set()
        iterator = QTreeWidgetItemIterator(self)
        while iterator.value():
            item = iterator.value()
            node = item.data(0, NODE_ROLE)
            if node is not None and item.isExpanded():
                paths.add(normalize_path(node.path))
            iterator += 1
        return paths

    def _restore_expanded(self, item: QTreeWidgetItem, paths: set[str]) -> None:
        stack = [item]
        while stack:
            current = stack.pop()
            node = current.data(0, NODE_ROLE)
            if node is None or normalize_path(node.path) not in paths:
                continue
            current.setExpanded(True)
            for index in range(current.childCount() - 1, -1, -1):
                child = current.child(index)
                if child.data(0, NODE_ROLE) is not None:
                    stack.append(child)

    def _count_items(self) -> int:
        return self._count_visible_items()

    def _count_visible_items(self) -> int:
        """Conta apenas os nós que estão realmente visíveis na árvore."""
        count = 0
        stack = [
            self.topLevelItem(index)
            for index in range(self.topLevelItemCount())
        ]
        while stack:
            item = stack.pop()
            if item.data(0, NODE_ROLE) is None:
                continue
            count += 1
            if item.isExpanded():
                for index in range(item.childCount()):
                    stack.append(item.child(index))
        return count

    def _schedule_visible_count(self, *_args: Any) -> None:
        if getattr(self, "_building", False):
            return
        self._count_timer.start()

    def _refresh_visible_count(self) -> None:
        if getattr(self, "_building", False):
            return
        shown = self._count_visible_items()
        if shown == self._shown:
            return
        self._shown = shown
        self.countChanged.emit(self._matches, shown)

    # ---------------------------------------------------------------- filtros
    def _start_filter(self) -> None:
        if self._result is None:
            return
        self._filter_generation += 1
        generation = self._filter_generation
        self._filter_runner.cancel()
        self.clear()
        self._metadata_pending.clear()
        self._matches = -1
        self._shown = 0
        self._building = False
        info = QTreeWidgetItem(["  Buscando resultados..."])
        info.setFirstColumnSpanned(True)
        info.setFlags(Qt.NoItemFlags)
        info.setForeground(0, QColor(get_theme().color("muted")))
        self.addTopLevelItem(info)
        self.countChanged.emit(-1, 0)
        self._filter_runner.submit(
            (
                _IndexFilterTask(
                    self._result,
                    self._search_index,
                    self._query,
                    self._filter,
                    self._sort,
                    generation,
                )
                if self._search_index is not None
                else _FilterTask(
                    self._result,
                    self._query,
                    self._filter,
                    self._sort,
                    generation,
                )
            )
        )

    def _filter_finished(self, result: _FilterResult) -> None:
        if result.generation != self._filter_generation or self._result is None:
            return
        self._render_filtered(result)

    def _filter_failed(self, message: str) -> None:
        if self._result is None:
            return
        self.clear()
        self._metadata_pending.clear()
        info = QTreeWidgetItem([f"  Falha na busca: {message}"])
        info.setFirstColumnSpanned(True)
        info.setFlags(Qt.NoItemFlags)
        info.setForeground(0, QColor(get_theme().color("danger")))
        self.addTopLevelItem(info)
        self._matches = 0
        self._shown = 0
        self.countChanged.emit(0, 0)

    def _render_filtered(self, result: _FilterResult) -> None:
        self.setUpdatesEnabled(False)
        self._building = True
        self.clear()
        self._metadata_pending.clear()
        rendered = 0
        truncated = False
        total = self._result.total_size if self._result is not None else 0

        # Pilha explícita: a árvore pode ser mais profunda que o limite de
        # recursão do Python, mesmo tendo sido varrida iterativamente.
        stack: list[tuple[QTreeWidgetItem | None, Node, int]] = []
        source_roots = (
            result.roots
            if result.roots is not None
            else (self._result.roots if self._result is not None else [])
        )
        if self._result is not None:
            for root in reversed(source_roots):
                stack.append((None, root, total or 1))
        while stack:
            parent, node, parent_size = stack.pop()
            if result.roots is None and id(node) not in result.included:
                continue
            if rendered >= MAX_RENDERED:
                truncated = True
                break
            item = self._create_item(
                parent, node, parent_size, is_root=parent is None, lazy=False
            )
            if parent is None:
                self.addTopLevelItem(item)
            item.setData(0, POPULATED_ROLE, True)
            rendered += 1
            for child in reversed(_sorted_children(node, self._sort)):
                stack.append((item, child, node.size or 1))

        if truncated or result.limited:
            suffix = (
                f"{result.matches} correspondência"
                if result.matches == 1
                else f"{result.matches} correspondências"
            )
            info = QTreeWidgetItem(
                [f"  {suffix}; exibindo {rendered}. Refine a busca para ver mais."]
            )
            info.setFirstColumnSpanned(True)
            info.setFlags(Qt.NoItemFlags)
            info.setForeground(0, QColor(get_theme().color("muted")))
            self.addTopLevelItem(info)
        self._matches = result.matches
        self._shown = rendered
        self.countChanged.emit(result.matches, rendered)
        self._building = False
        self.setUpdatesEnabled(True)
        self.expandAll()
        self.scrollToTop()
        self.viewport().update()
        self._fit_columns()
        self._schedule_visible_count()

    def _sorted_children(self, node: Node, limit: int | None = None) -> list[Node]:
        if not node.children_loaded and node.children_loader is not None:
            return node.children_loader(node, self._sort, limit)
        return _sorted_children(node, self._sort, limit)

    def _node_tooltip(self, node: Node) -> str:
        tip = [
            node.path,
            f"Tamanho: {format_size(node.size, self._unit)}",
            f"Arquivos: {format_number(node.files)} · Pastas: {format_number(node.dirs)}",
            f"Modificado: {format_datetime(node.mtime)}",
        ]
        author = cached_file_author(node.path)
        if author:
            tip.append(f"Autor: {author}")
        owner = cached_file_owner(node.path)
        if owner:
            tip.append(f"Proprietário: {owner}")
        if node.error:
            tip.append(f"Aviso: {node.error}")
        return "\n".join(tip)

    # -------------------------------------------------------------- metadados
    def _queue_metadata(self, item: QTreeWidgetItem, node: Node) -> None:
        author = cached_file_author(node.path)
        owner = cached_file_owner(node.path)
        if author is not None:
            item.setText(COL_AUTHOR, author or "—")
            item.setToolTip(COL_AUTHOR, author or "Sem autor para exibir.")
        else:
            item.setText(COL_AUTHOR, "…")
            item.setToolTip(COL_AUTHOR, "Consultando autor…")
        if owner is not None:
            item.setText(COL_OWNER, owner or "—")
            item.setToolTip(COL_OWNER, owner or "Sem proprietário para exibir.")
        else:
            item.setText(COL_OWNER, "…")
            item.setToolTip(COL_OWNER, "Consultando proprietário…")
        if author is not None and owner is not None:
            return
        key = normalize_path(node.path)
        items = self._metadata_pending.get(key)
        if items is None:
            self._metadata_pending[key] = [item]
            self._metadata_pool.start(
                _MetadataJob(node.path, self._metadata_signals)
            )
        else:
            items.append(item)

    def _metadata_resolved(self, path: str, author: str, owner: str) -> None:
        key = normalize_path(path)
        items = self._metadata_pending.pop(key, [])
        author_text = author or "—"
        owner_text = owner or "—"
        for item in items:
            if not isValid(item):
                continue
            item.setText(COL_AUTHOR, author_text)
            item.setToolTip(
                COL_AUTHOR,
                author_text if author else "Sem autor para exibir.",
            )
            item.setText(COL_OWNER, owner_text)
            item.setToolTip(
                COL_OWNER,
                owner_text if owner else "Sem proprietário para exibir.",
            )
            node = item.data(COL_NAME, NODE_ROLE)
            if isinstance(node, Node):
                item.setToolTip(COL_NAME, self._node_tooltip(node))

    # --------------------------------------------------------------- itens
    def _create_item(
        self,
        parent: QTreeWidgetItem | None,
        node: Node,
        parent_size: int,
        is_root: bool = False,
        lazy: bool = False,
    ) -> QTreeWidgetItem:
        pct = 1.0 if is_root else (node.size / parent_size if parent_size else 0.0)
        item = QTreeWidgetItem(
            [
                node.name,
                format_size(node.size, self._unit),
                f"{pct * 100:.1f}%".replace(".", ","),
                self._item_count_text(node),
                format_datetime(node.mtime),
                "",
                "",
                "Raiz" if is_root else ("Pasta" if node.is_dir else self._type_text(node)),
                node.path,
            ]
        )
        item.setData(0, NODE_ROLE, node)
        item.setData(0, SIZE_ROLE, node.size)
        item.setData(0, PCT_ROLE, pct)
        item.setData(1, SIZE_ROLE, node.size)
        item.setData(1, PCT_ROLE, pct)
        item.setData(0, POPULATED_ROLE, False)
        for column in (COL_SIZE, COL_PCT, COL_ITEMS, COL_MTIME):
            item.setTextAlignment(column, Qt.AlignRight | Qt.AlignVCenter)
        for column in (COL_AUTHOR, COL_OWNER, COL_KIND, COL_PATH):
            item.setTextAlignment(column, Qt.AlignLeft | Qt.AlignVCenter)
        if node.error:
            item.setForeground(0, QColor(get_theme().color("danger")))
        self._queue_metadata(item, node)
        item.setToolTip(0, self._node_tooltip(node))
        item.setToolTip(COL_PATH, node.path)
        if self._path_visible:
            self._path_content_width = max(
                self._path_content_width,
                self.fontMetrics().horizontalAdvance(node.path) + 28,
            )
        if is_root:
            f = item.font(0)
            f.setWeight(QFont.DemiBold)
            item.setFont(0, f)
        self._apply_icon(item, node, is_root)
        if parent is not None:
            parent.addChild(item)
        if node.is_dir and lazy and (
            not node.children_loaded or node.children
        ):
            placeholder = QTreeWidgetItem([""])
            placeholder.setData(0, PLACEHOLDER_ROLE, True)
            placeholder.setFlags(Qt.NoItemFlags)
            item.addChild(placeholder)
        return item

    @staticmethod
    def _item_count_text(node: Node) -> str:
        if not node.is_dir:
            return "—"
        if node.files == 0:
            return "vazia" if node.dirs <= 1 else "sem arquivos"
        return f"{format_number(node.files)} arq."

    @staticmethod
    def _type_text(node: Node) -> str:
        if not node.extension:
            return "Arquivo"
        return node.extension.upper()[:7]

    def _apply_icon(self, item: QTreeWidgetItem, node: Node, is_root: bool = False) -> None:
        theme = get_theme()
        color = theme.color("primary" if node.is_dir else "muted")
        if node.error:
            color = theme.color("warn")
        item.setIcon(0, file_icon(node.name, node.is_dir, color, theme.color("primary")))
        if is_root:
            item.setIcon(0, icon("harddisk", theme.color("primary"), 17))

    def _on_expanded(self, item: QTreeWidgetItem) -> None:
        if self._building:
            return
        node = self._node_at(item)
        if node is None or not node.is_dir:
            return
        if item.data(0, POPULATED_ROLE):
            return
        item.setData(0, POPULATED_ROLE, "pending")
        while item.childCount():
            child = item.takeChild(0)
            del child
        loading = QTreeWidgetItem(["  Carregando…"])
        loading.setFirstColumnSpanned(True)
        loading.setFlags(Qt.NoItemFlags)
        loading.setForeground(0, QColor(get_theme().color("muted")))
        item.addChild(loading)
        self._expand_queue.append((item, node))
        if self._expand_active is None and not self._expand_timer.isActive():
            self._expand_timer.start()

    def _expand_step(self) -> None:
        active = self._expand_active
        if active is None:
            while self._expand_queue:
                item, node = self._expand_queue.popleft()
                try:
                    valid = (
                        item.treeWidget() is self
                        and item.data(0, NODE_ROLE) is node
                    )
                except RuntimeError:
                    valid = False
                if not valid:
                    continue
                if not item.isExpanded():
                    item.setData(0, POPULATED_ROLE, False)
                    while item.childCount():
                        child = item.takeChild(0)
                        del child
                    continue
                while item.childCount():
                    child = item.takeChild(0)
                    del child
                try:
                    children = self._sorted_children(node, limit=MAX_CHILDREN)
                except Exception as exc:
                    logger.exception("falha ao carregar filhos indexados")
                    error = QTreeWidgetItem(
                        [f"  Falha ao carregar: {exc}"]
                    )
                    error.setFirstColumnSpanned(True)
                    error.setFlags(Qt.NoItemFlags)
                    error.setForeground(
                        0, QColor(get_theme().color("danger"))
                    )
                    item.addChild(error)
                    item.setData(0, POPULATED_ROLE, True)
                    self._expand_active = None
                    if self._expand_queue:
                        self._expand_timer.start(0)
                    return
                total = node.children_total or len(children)
                self._expand_active = [item, node, children, 0, total]
                break
            active = self._expand_active
            if active is None:
                return
        item, node, children, index, total = active
        try:
            valid = item.treeWidget() is self and item.data(0, NODE_ROLE) is node
        except RuntimeError:
            valid = False
        if not valid or not item.isExpanded():
            if index and self._shown > 0:
                self._shown -= index
            if valid:
                item.setData(0, POPULATED_ROLE, False)
                while item.childCount():
                    child = item.takeChild(0)
                    del child
            self._expand_active = None
            if self._expand_queue:
                self._expand_timer.start(0)
            return
        end = min(index + EXPAND_BATCH, len(children))
        parent_size = node.size or 1
        for child in children[index:end]:
            self._create_item(item, child, parent_size, lazy=True)
        active[3] = end
        added = end - index
        if added and self._shown >= 0:
            self._shown += added
        if end < len(children):
            self._expand_timer.start(0)
            return
        hidden = total - len(children)
        if hidden > 0:
            info = QTreeWidgetItem(
                [f"  … {format_number(hidden)} itens não exibidos — refine a busca."]
            )
            info.setFirstColumnSpanned(True)
            info.setFlags(Qt.NoItemFlags)
            info.setForeground(0, QColor(get_theme().color("muted")))
            item.addChild(info)
        item.setData(0, POPULATED_ROLE, True)
        self._expand_active = None
        self._restore_pending_children(item)
        self._expand_all_children(item)
        self._fit_columns()
        self.countChanged.emit(self._matches, max(0, self._shown))
        self._schedule_visible_count()
        if self._expand_queue:
            self._expand_timer.start(0)

    # -------------------------------------------------------------- interação
    def _node_at(self, item: QTreeWidgetItem | None) -> Node | None:
        if item is None:
            return None
        node = item.data(0, NODE_ROLE)
        return node if isinstance(node, Node) else None

    def current_path(self) -> str:
        node = self._node_at(self.currentItem())
        return node.path if node is not None else ""

    def _on_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        node = self._node_at(item)
        if node is None:
            return
        if node.is_dir:
            item.setExpanded(not item.isExpanded())
        else:
            open_in_explorer(node.path, select=True)

    def _context_menu(self, pos) -> None:
        item = self.itemAt(pos)
        node = self._node_at(item)
        if node is None:
            return
        theme = get_theme()
        menu = QMenu(self)
        act_open = menu.addAction(icon("open-in-new", theme.color("muted"), 16), "Abrir no Explorer")
        menu.addSeparator()
        act_row = menu.addAction(
            icon("content-copy", theme.color("muted"), 16), "Copiar linha(s)\tCtrl+C"
        )
        act_size = menu.addAction(
            icon("numeric", theme.color("muted"), 16), "Copiar tamanho"
        )
        act_copy = menu.addAction(
            icon("link-variant", theme.color("muted"), 16), "Copiar caminho"
        )
        menu.addSeparator()
        act_parent = menu.addAction(
            icon("folder-open-outline", theme.color("muted"), 16),
            "Abrir pasta pai",
        )
        chosen = menu.exec(self.viewport().mapToGlobal(pos))
        if chosen == act_open:
            open_in_explorer(node.path, select=True)
        elif chosen == act_row:
            self._copy_rows()
        elif chosen == act_size:
            self._copy_size(item)
        elif chosen == act_copy:
            self._copy_path(item)
        elif chosen == act_parent:
            parent = node.path if node.is_dir else os.path.dirname(node.path)
            open_in_explorer(parent)
        menu.deleteLater()

    def _refresh_visuals(self, *_args: Any) -> None:
        iterator = QTreeWidgetItemIterator(self)
        while iterator.value():
            item = iterator.value()
            node = item.data(0, NODE_ROLE)
            if node is not None:
                is_root = item.parent() is None
                self._apply_icon(item, node, is_root)
            iterator += 1
        if self._path_visible:
            self._update_path_content_width()
        self._fit_columns()
        self.viewport().update()
