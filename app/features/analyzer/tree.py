"""Árvore de arquivos com tamanhos aninhados, busca, filtros e ordenação."""

from __future__ import annotations

import heapq
import os
import unicodedata
from collections import deque
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

from ...icons import file_icon, icon
from ...services.model import Node, ScanResult
from ...theme import get_theme
from ...utils import (
    cached_file_owner,
    copy_to_clipboard,
    file_owner,
    format_datetime,
    format_number,
    format_size,
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
COL_OWNER = 5
COL_KIND = 6
COL_PATH = 7


class _OwnerSignals(QObject):
    resolved = Signal(str, str)


class _OwnerJob(QRunnable):
    """Consulta o proprietário fora da thread da interface."""

    def __init__(self, path: str, signals: _OwnerSignals) -> None:
        super().__init__()
        self.path = path
        self.signals = signals

    def run(self) -> None:
        self.signals.resolved.emit(self.path, file_owner(self.path))

MAX_CHILDREN = 1200
MAX_RENDERED = 2800
MAX_FILTER_SCAN = 30000
EXPAND_BATCH = 120
EXPAND_DEBOUNCE_MS = 60
MB = 1024 * 1024
GB = 1024 * MB


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


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
        self.setColumnCount(8)
        self.setHeaderLabels(
            [
                "Nome",
                "Tamanho",
                "% do pai",
                "Itens",
                "Modificado",
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
        header.setSectionResizeMode(COL_NAME, QHeaderView.Stretch)
        for column, width in (
            (COL_SIZE, 116),
            (COL_PCT, 74),
            (COL_ITEMS, 88),
            (COL_MTIME, 132),
            (COL_KIND, 86),
        ):
            header.setSectionResizeMode(column, QHeaderView.Fixed)
            self.setColumnWidth(column, width)
        header.setSectionResizeMode(COL_OWNER, QHeaderView.Interactive)
        self.setColumnWidth(COL_OWNER, 220)
        header.setSectionResizeMode(COL_PATH, QHeaderView.Interactive)
        self.setColumnWidth(COL_PATH, 600)
        header.setMinimumSectionSize(64)
        header.setHighlightSections(False)
        for column in (COL_SIZE, COL_PCT, COL_ITEMS, COL_MTIME):
            self.headerItem().setTextAlignment(column, Qt.AlignRight | Qt.AlignVCenter)
        for column in (COL_OWNER, COL_KIND, COL_PATH):
            self.headerItem().setTextAlignment(column, Qt.AlignLeft | Qt.AlignVCenter)
        self.setTextElideMode(Qt.ElideMiddle)
        self.setColumnHidden(COL_PATH, True)
        self._path_visible = False
        self._path_content_width = 600
        self._size_delegate = SizeBarDelegate(self)
        self.setItemDelegateForColumn(1, self._size_delegate)
        self._result: ScanResult | None = None
        self._query = ""
        self._filter = "all"
        self._sort = "size_desc"
        self._unit = "auto"
        self._building = False
        self._matches = -1
        self._shown = 0
        self._overflow = False
        self._expand_queue: deque[tuple[QTreeWidgetItem, Node]] = deque()
        self._expand_active: list[Any] | None = None
        self._expand_all_budget = 0
        self._restore_paths: set[str] = set()
        self._expand_timer = QTimer(self)
        self._expand_timer.setSingleShot(True)
        self._expand_timer.setInterval(EXPAND_DEBOUNCE_MS)
        self._expand_timer.timeout.connect(self._expand_step)
        self._owner_pool = QThreadPool(self)
        self._owner_pool.setMaxThreadCount(4)
        self._owner_signals = _OwnerSignals(self)
        self._owner_signals.resolved.connect(self._owner_resolved)
        self._owner_pending: dict[str, list[QTreeWidgetItem]] = {}
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
            "Modificado, Proprietário, Tipo, Caminho."
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
        self.rebuild()

    def set_path_visible(self, visible: bool) -> None:
        self._path_visible = bool(visible)
        self.setColumnHidden(COL_PATH, not self._path_visible)
        if self._path_visible:
            self._update_path_content_width()
            self._fit_path_columns()
        else:
            self.header().setSectionResizeMode(COL_NAME, QHeaderView.Stretch)

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
        self._path_content_width = max(600, width)

    def _fit_path_columns(self) -> None:
        """Divide o espaço entre Nome e Caminho sem estrangular o Nome."""
        if not self._path_visible:
            return
        header = self.header()
        header.setSectionResizeMode(COL_NAME, QHeaderView.Interactive)
        header.setSectionResizeMode(COL_PATH, QHeaderView.Interactive)
        viewport = max(1, self.viewport().width())
        fixed = sum(
            self.columnWidth(column) for column in range(COL_SIZE, COL_PATH)
        )
        path_width = max(600, self._path_content_width)
        name_width = max(280, viewport - fixed - path_width)
        self.setColumnWidth(COL_NAME, name_width)
        self.setColumnWidth(COL_PATH, path_width)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._fit_path_columns()

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
            self._restore_paths.discard(os.path.normcase(node.path))
        for i in range(item.childCount()):
            child = item.child(i)
            child_node = self._node_at(child)
            if child_node is None:
                continue
            key = os.path.normcase(child_node.path)
            if key in self._restore_paths:
                self._restore_paths.discard(key)
                child.setExpanded(True)

    def _expand_all_children(self, item: QTreeWidgetItem) -> None:
        if self._expand_all_budget <= 0:
            return
        for i in range(item.childCount()):
            child = item.child(i)
            node = self._node_at(child)
            if node is None or not node.is_dir:
                continue
            if child.isExpanded():
                if child.data(0, POPULATED_ROLE) is True:
                    self._expand_all_children(child)
                continue
            child.setExpanded(True)
            self._expand_all_budget -= 1
            if self._expand_all_budget <= 0:
                break

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
        self.setUpdatesEnabled(False)
        self._building = True
        self.clear()
        self._matches = -1
        self._shown = 0
        self._overflow = False
        if self._result is None:
            self._building = False
            self.setUpdatesEnabled(True)
            self.countChanged.emit(0, 0)
            return
        filtered = bool(self._query) or self._filter != "all"
        if filtered:
            self._build_filtered()
        else:
            total = self._result.total_size or 1
            for root in self._result.roots:
                item = self._create_item(None, root, total, is_root=True, lazy=True)
                self.addTopLevelItem(item)
            self._building = False
            for i in range(self.topLevelItemCount()):
                item = self.topLevelItem(i)
                item.setExpanded(True)
                self._restore_expanded(item, expanded)
            self._matches = -1
            self._shown = self._count_items()
            self.countChanged.emit(-1, self._shown)
        self._building = False
        self.setUpdatesEnabled(True)
        self.viewport().update()
        if self._path_visible:
            self._fit_path_columns()
        if filtered:
            self.expandAll()
            self.scrollToTop()

    def _expanded_paths(self) -> set[str]:
        paths: set[str] = set()
        iterator = QTreeWidgetItemIterator(self)
        while iterator.value():
            item = iterator.value()
            node = item.data(0, NODE_ROLE)
            if node is not None and item.isExpanded():
                paths.add(os.path.normcase(node.path))
            iterator += 1
        return paths

    def _restore_expanded(self, item: QTreeWidgetItem, paths: set[str]) -> None:
        node = item.data(0, NODE_ROLE)
        if node is None or os.path.normcase(node.path) not in paths:
            return
        item.setExpanded(True)
        for i in range(item.childCount()):
            child = item.child(i)
            if child.data(0, NODE_ROLE) is not None:
                self._restore_expanded(child, paths)

    def _count_items(self) -> int:
        count = 0
        iterator = QTreeWidgetItemIterator(self)
        while iterator.value():
            if iterator.value().data(0, NODE_ROLE) is not None:
                count += 1
            iterator += 1
        return count

    # ---------------------------------------------------------------- filtros
    def _node_matches(self, node: Node) -> bool:
        if self._query:
            haystack = _fold(node.name)
            for token in self._query.split():
                if token not in haystack:
                    return False
        if self._filter == "folders":
            return node.is_dir
        if self._filter == "files":
            return not node.is_dir
        if self._filter == "large100":
            return not node.is_dir and node.size >= 100 * MB
        if self._filter == "large1g":
            return not node.is_dir and node.size >= GB
        return True

    def _build_filtered(self) -> None:
        if self._result is None:
            return
        visited = 0
        matched = 0

        def collect(node: Node) -> tuple[Node, list[Any], bool] | None:
            nonlocal visited, matched
            visited += 1
            if visited > MAX_FILTER_SCAN:
                self._overflow = True
                return None
            children: list[Any] = []
            for child in self._sorted_children(node):
                result = collect(child)
                if result is not None:
                    children.append(result)
            self_match = self._node_matches(node)
            if self_match:
                matched += 1
            if self_match or children:
                return (node, children, self_match)
            return None

        roots: list[tuple[Node, list[Any], bool]] = []
        for root in self._result.roots:
            result = collect(root)
            if result is not None:
                roots.append(result)

        rendered = 0
        truncated_render = False

        def add(parent: QTreeWidgetItem | None, entry: tuple[Node, list[Any], bool], parent_size: int):
            nonlocal rendered, truncated_render
            if rendered >= MAX_RENDERED:
                truncated_render = True
                return
            node, children, _self_match = entry
            item = self._create_item(
                parent, node, parent_size, is_root=parent is None, lazy=False
            )
            if parent is None:
                self.addTopLevelItem(item)
            item.setData(0, POPULATED_ROLE, True)
            rendered += 1
            for child_entry in children:
                add(item, child_entry, node.size or 1)

        total = self._result.total_size or 1
        for entry in roots:
            add(None, entry, total)
        if truncated_render:
            info = QTreeWidgetItem(
                ["  Resultados limitados a 2.800 itens — refine a busca para ver mais."]
            )
            info.setFirstColumnSpanned(True)
            info.setFlags(Qt.NoItemFlags)
            info.setForeground(0, QColor(get_theme().color("muted")))
            self.addTopLevelItem(info)
        self._matches = matched
        self._shown = rendered
        self.countChanged.emit(matched, rendered)

    def _sorted_children(self, node: Node, limit: int | None = None) -> list[Node]:
        key = self._sort
        if key == "size_asc":
            func = lambda n: (n.size, _fold(n.name))
            if limit is not None:
                return heapq.nsmallest(limit, node.children, key=func)
            return sorted(node.children, key=func)
        if key == "name_asc":
            func = lambda n: (not n.is_dir, _fold(n.name))
            if limit is not None:
                return heapq.nsmallest(limit, node.children, key=func)
            return sorted(node.children, key=func)
        if key == "name_desc":
            func = lambda n: (n.is_dir, _fold(n.name))
            if limit is not None:
                return heapq.nlargest(limit, node.children, key=func)
            names = sorted(
                node.children, key=lambda n: _fold(n.name), reverse=True
            )
            return sorted(names, key=lambda n: not n.is_dir)
        if key == "recent":
            func = lambda n: n.mtime
            if limit is not None:
                return heapq.nlargest(limit, node.children, key=func)
            return sorted(node.children, key=func, reverse=True)
        func = lambda n: (n.size, _fold(n.name))
        if limit is not None:
            return heapq.nlargest(limit, node.children, key=func)
        return sorted(node.children, key=func, reverse=True)

    def _node_tooltip(self, node: Node) -> str:
        tip = [
            node.path,
            f"Tamanho: {format_size(node.size, self._unit)}",
            f"Arquivos: {format_number(node.files)} · Pastas: {format_number(node.dirs)}",
            f"Modificado: {format_datetime(node.mtime)}",
        ]
        owner = cached_file_owner(node.path)
        if owner:
            tip.append(f"Proprietário: {owner}")
        if node.error:
            tip.append(f"Aviso: {node.error}")
        return "\n".join(tip)

    # ---------------------------------------------------------- proprietário
    def _queue_owner(self, item: QTreeWidgetItem, node: Node) -> None:
        owner = cached_file_owner(node.path)
        if owner is not None:
            text = owner or "—"
            item.setText(COL_OWNER, text)
            item.setToolTip(COL_OWNER, text)
            return
        item.setText(COL_OWNER, "…")
        item.setToolTip(COL_OWNER, "Consultando proprietário…")
        key = os.path.normcase(node.path)
        items = self._owner_pending.get(key)
        if items is None:
            self._owner_pending[key] = [item]
            self._owner_pool.start(_OwnerJob(node.path, self._owner_signals))
        else:
            items.append(item)

    def _owner_resolved(self, path: str, owner: str) -> None:
        key = os.path.normcase(path)
        items = self._owner_pending.pop(key, [])
        text = owner or "—"
        for item in items:
            if not isValid(item):
                continue
            item.setText(COL_OWNER, text)
            item.setToolTip(COL_OWNER, text)
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
        for column in (COL_OWNER, COL_KIND, COL_PATH):
            item.setTextAlignment(column, Qt.AlignLeft | Qt.AlignVCenter)
        if node.error:
            item.setForeground(0, QColor(get_theme().color("danger")))
        self._queue_owner(item, node)
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
        if node.is_dir and node.children and lazy:
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
                children = self._sorted_children(node, limit=MAX_CHILDREN)
                self._expand_active = [item, node, children, 0, len(node.children)]
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
        if self._path_visible:
            self._fit_path_columns()
        self.countChanged.emit(self._matches, max(0, self._shown))
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
            open_in_explorer(node.path, select=not node.is_dir)
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
            self._fit_path_columns()
        self.viewport().update()
