"""Seção por tipo de recomendação: contexto + tabela ordenável."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from appshell.utils import format_bytes
from appshell.widgets.buttons import ActionButton, IconButton
from appshell.widgets.common import ElidedLabel, IconLabel

from ..services.model import Suggestion
from .recommendation_table import (
    RecommendationFilterProxy,
    RecommendationRow,
    RecommendationTable,
    RecommendationTableModel,
)

TABLE_MIN_HEIGHT = 150
TABLE_MAX_HEIGHT = 300
COLLAPSE_DURATION_MS = 190


def _common_base(paths: list[str]) -> str:
    """Prefixo comum para evitar repetir o mesmo caminho em todas as linhas."""
    if len(paths) < 2:
        return ""
    normalized = [os.path.normpath(path) for path in paths]
    try:
        base = os.path.commonpath(normalized)
    except (ValueError, OSError):
        return ""
    if not base or Path(base).parent == Path(base):
        return ""
    if base in normalized:
        base = os.path.dirname(base)
    return base


class RecommendationSection(QFrame):
    """Um tipo de recomendação com descrição, resumo e tabela de caminhos."""

    statusMessage = Signal(str)
    expandedChanged = Signal(str, bool)

    def __init__(
        self,
        suggestion: Suggestion,
        rows: list[RecommendationRow],
        expanded: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.suggestion = suggestion
        self._rows = list(rows)
        self._expanded = expanded
        self._animation: QPropertyAnimation | None = None
        self._expanded_height = TABLE_MIN_HEIGHT
        self.setObjectName("Card")
        self._base_path = _common_base([row.path for row in self._rows])
        if self._base_path:
            for row in self._rows:
                try:
                    relative = os.path.relpath(row.path, self._base_path)
                except (ValueError, OSError):
                    continue
                if relative and not relative.startswith(".."):
                    row.display_path = relative
        safe = suggestion.confidence == "safe"

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(12)
        header.addWidget(
            IconLabel(
                suggestion.icon,
                24,
                "success" if safe else "warn",
                self,
            ),
            0,
            Qt.AlignTop,
        )

        text_box = QVBoxLayout()
        text_box.setSpacing(3)
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title = ElidedLabel(suggestion.title, self)
        title.setObjectName("SectionTitle")
        title.setToolTip(suggestion.title)
        title.setWordWrap(False)
        title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        title.setMinimumWidth(180)
        title_row.addWidget(title, 1)
        badge = QLabel("Segura" if safe else "Revisar", self)
        badge.setObjectName("BadgeSuccess" if safe else "BadgeWarn")
        badge.setAlignment(Qt.AlignCenter)
        title_row.addWidget(badge, 0, Qt.AlignTop)
        text_box.addLayout(title_row)
        description = QLabel(suggestion.description, self)
        description.setObjectName("Muted")
        description.setWordWrap(True)
        text_box.addWidget(description)
        if suggestion.note:
            note = QLabel(suggestion.note, self)
            note.setObjectName("Faint")
            note.setWordWrap(True)
            text_box.addWidget(note)
        if self._base_path:
            base = ElidedLabel(f"Base: {self._base_path}", self)
            base.setObjectName("Faint")
            base.setToolTip(self._base_path)
            text_box.addWidget(base)
        header.addLayout(text_box, 1)

        actions = QVBoxLayout()
        actions.setSpacing(4)
        summary = QLabel(
            f"{format_bytes(suggestion.savings)} • "
            f"{len(self._rows)} caminho(s)",
            self,
        )
        summary.setObjectName("ValueSmall")
        summary.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        actions.addWidget(summary)
        self.count_label = QLabel("", self)
        self.count_label.setObjectName("Faint")
        self.count_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        actions.addWidget(self.count_label)
        buttons = QHBoxLayout()
        buttons.setSpacing(4)
        self.copy_btn = ActionButton(
            "Copiar seção", "content-copy", "link", self, 14
        )
        self.copy_btn.setToolTip("Copiar os caminhos desta seção, um por linha")
        self.copy_btn.clicked.connect(self._copy_paths)
        buttons.addWidget(self.copy_btn)
        self.toggle_btn = IconButton(
            "chevron-up" if self._expanded else "chevron-down",
            "Recolher seção" if self._expanded else "Expandir seção",
            self,
            16,
        )
        self.toggle_btn.clicked.connect(self._toggle)
        buttons.addWidget(self.toggle_btn)
        actions.addLayout(buttons)
        header.addLayout(actions, 0)
        root.addLayout(header)

        self.table = RecommendationTable(self)
        self.model = RecommendationTableModel(self)
        self.model.set_rows(self._rows)
        self.proxy = RecommendationFilterProxy(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setSortRole(Qt.UserRole)
        self.table.setModel(self.proxy)
        # A seção já fornece sugestão e confiança no cabeçalho. O tipo
        # (pasta/arquivo) fica no ícone da coluna Nome e no tooltip.
        self.table.setColumnHidden(0, True)
        self.table.setColumnHidden(7, True)
        self.table.sortByColumn(3, Qt.DescendingOrder)
        self.table.setMinimumHeight(TABLE_MIN_HEIGHT)
        self.table.setMaximumHeight(TABLE_MAX_HEIGHT)
        self.table.statusMessage.connect(self.statusMessage)
        root.addWidget(self.table)
        self._expanded_height = min(
            TABLE_MAX_HEIGHT,
            max(TABLE_MIN_HEIGHT, self.table.sizeHint().height()),
        )
        self.table.setVisible(self._expanded)
        if not self._expanded:
            self.table.setMinimumHeight(0)
            self.table.setMaximumHeight(0)

    @property
    def key(self) -> str:
        return self.suggestion.key

    @property
    def expanded(self) -> bool:
        return self._expanded

    def _toggle(self) -> None:
        self.set_expanded(not self._expanded)
        self.expandedChanged.emit(self.key, self._expanded)

    def set_expanded(self, expanded: bool) -> None:
        expanded = bool(expanded)
        self._expanded = expanded
        self.toggle_btn.set_icon_name(
            "chevron-up" if self._expanded else "chevron-down"
        )
        self.toggle_btn.setToolTip(
            "Recolher seção" if self._expanded else "Expandir seção"
        )
        if self._expanded:
            self._animate_expand()
        else:
            self._animate_collapse()

    def _stop_animation(self) -> None:
        if self._animation is not None:
            self._animation.stop()
            self._animation.deleteLater()
            self._animation = None

    def _start_animation(
        self, start: int, end: int, expanded: bool
    ) -> None:
        self._stop_animation()
        anim = QPropertyAnimation(self.table, b"maximumHeight", self)
        anim.setDuration(COLLAPSE_DURATION_MS)
        anim.setStartValue(max(0, int(start)))
        anim.setEndValue(max(0, int(end)))
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.finished.connect(
            lambda: self._animation_finished(anim, expanded)
        )
        self._animation = anim
        anim.start()

    def _animation_finished(
        self, anim: QPropertyAnimation, expanded: bool
    ) -> None:
        if self._animation is not anim:
            anim.deleteLater()
            return
        self._animation = None
        anim.deleteLater()
        if expanded:
            self.table.setMinimumHeight(TABLE_MIN_HEIGHT)
            self.table.setMaximumHeight(TABLE_MAX_HEIGHT)
            self.table.setVisible(True)
            self._expanded_height = min(
                TABLE_MAX_HEIGHT,
                max(TABLE_MIN_HEIGHT, self.table.height()),
            )
        else:
            self.table.setVisible(False)
            self.table.setMinimumHeight(0)
            self.table.setMaximumHeight(0)

    def _animate_expand(self) -> None:
        table = self.table
        start = max(0, table.height()) if table.isVisible() else 0
        target = min(
            TABLE_MAX_HEIGHT,
            max(TABLE_MIN_HEIGHT, self._expanded_height, start),
        )
        table.setMinimumHeight(0)
        table.setMaximumHeight(start)
        table.setVisible(True)
        self._start_animation(start, target, True)

    def _animate_collapse(self) -> None:
        table = self.table
        if not table.isVisible():
            table.setMinimumHeight(0)
            table.setMaximumHeight(0)
            return
        start = max(0, table.height())
        if start <= 0:
            start = self._expanded_height
        self._expanded_height = min(
            TABLE_MAX_HEIGHT, max(TABLE_MIN_HEIGHT, start)
        )
        if start <= 0:
            table.setVisible(False)
            return
        table.setMinimumHeight(0)
        table.setMaximumHeight(start)
        self._start_animation(start, 0, False)

    def _copy_paths(self) -> None:
        self.table.copy_all()

    def apply_filter(self, query: str, confidence: str) -> int:
        self.proxy.set_query(query)
        self.proxy.set_confidence(confidence)
        visible = self.proxy.rowCount()
        total = self.model.rowCount()
        self.count_label.setText(
            f"{visible} de {total}" if visible != total else ""
        )
        self.setVisible(visible > 0)
        if visible <= 0:
            self._stop_animation()
            self.table.setVisible(False)
            return visible
        if not self._expanded:
            self._stop_animation()
            self.table.setVisible(False)
            return visible
        if self._animation is None:
            self.table.setMinimumHeight(TABLE_MIN_HEIGHT)
            self.table.setMaximumHeight(TABLE_MAX_HEIGHT)
            self.table.setVisible(True)
        return visible
