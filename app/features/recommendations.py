"""Página de recomendações com detalhes e caminhos para inspeção."""

from __future__ import annotations

import os
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..services.model import Suggestion
from ..theme import get_theme
from ..utils import (
    copy_to_clipboard,
    format_bytes,
    format_datetime,
    open_in_explorer,
    short_path,
)
from ..widgets.buttons import ActionButton, SelectButton
from ..widgets.common import DisclaimerBanner, EmptyState, IconLabel, PageHeader
from .base import BasePage


class SuggestionCard(QFrame):
    toastRequested = Signal(str, str)

    def __init__(self, suggestion: Suggestion, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.suggestion = suggestion
        self.setObjectName("SuggestionCard")
        self.setAttribute(Qt.WA_Hover, True)
        safe = suggestion.confidence == "safe"
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(12)
        tile = QFrame(self)
        tile.setObjectName("IconTileSuccess" if safe else "IconTileWarn")
        tile.setFixedSize(46, 46)
        tl = QHBoxLayout(tile)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(
            IconLabel(suggestion.icon, 23, "success" if safe else "warn", tile),
            0,
            Qt.AlignCenter,
        )
        top.addWidget(tile)
        title_box = QVBoxLayout()
        title_box.setSpacing(3)
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title = QLabel(suggestion.title)
        title.setObjectName("SectionTitle")
        title_row.addWidget(title)
        badge = QLabel("Seguro" if safe else "Revisar")
        badge.setObjectName("BadgeSuccess" if safe else "BadgeWarn")
        title_row.addWidget(badge)
        title_row.addStretch(1)
        title_box.addLayout(title_row)
        meta = QLabel(
            f"{suggestion.count} {'item' if suggestion.count == 1 else 'itens'} · "
            + (
                "regeneráveis automaticamente"
                if safe
                else "confirme a necessidade antes de remover"
            )
        )
        meta.setObjectName("Muted")
        title_box.addWidget(meta)
        top.addLayout(title_box, 1)
        savings_box = QVBoxLayout()
        savings_box.setSpacing(0)
        savings = QLabel(format_bytes(suggestion.savings))
        savings.setObjectName("ValueSmall")
        savings.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        savings_box.addWidget(savings)
        savings_cap = QLabel("estimativa")
        savings_cap.setObjectName("Faint")
        savings_cap.setAlignment(Qt.AlignRight)
        savings_box.addWidget(savings_cap)
        top.addLayout(savings_box)
        lay.addLayout(top)

        desc = QLabel(suggestion.description)
        desc.setObjectName("Muted")
        desc.setWordWrap(True)
        lay.addWidget(desc)

        if suggestion.note:
            note = QFrame(self)
            note.setObjectName("TintSuccess" if safe else "TintWarn")
            nl = QHBoxLayout(note)
            nl.setContentsMargins(11, 8, 11, 8)
            nl.setSpacing(8)
            nl.addWidget(
                IconLabel("shield-check-outline" if safe else "alert-outline", 16, "success" if safe else "warn", note),
                0,
                Qt.AlignTop,
            )
            note_text = QLabel(suggestion.note)
            note_text.setWordWrap(True)
            note_text.setObjectName("Muted")
            nl.addWidget(note_text, 1)
            lay.addWidget(note)

        if suggestion.paths:
            paths_label = QLabel(f"CAMINHOS ({len(suggestion.paths)} exibidos)")
            paths_label.setObjectName("Eyebrow")
            lay.addWidget(paths_label)
            tree = QTreeWidget(self)
            tree.setHeaderHidden(True)
            tree.setRootIsDecorated(False)
            tree.setIndentation(0)
            tree.setUniformRowHeights(True)
            tree.setAlternatingRowColors(True)
            tree.setSelectionMode(QTreeWidget.SingleSelection)
            tree.setMinimumHeight(94)
            tree.setMaximumHeight(min(214, max(94, len(suggestion.paths) * 34 + 16)))
            theme = get_theme()
            for path in suggestion.paths:
                is_dir = os.path.isdir(path)
                item = QTreeWidgetItem([short_path(path, 110)])
                item.setData(0, Qt.UserRole, path)
                item.setToolTip(0, path)
                from ..icons import file_icon

                item.setIcon(
                    0,
                    file_icon(
                        path,
                        is_dir,
                        theme.color("muted"),
                        theme.color("primary"),
                    ),
                )
                tree.addTopLevelItem(item)
            tree.itemDoubleClicked.connect(self._open_item)
            lay.addWidget(tree)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.open_btn = ActionButton("Abrir local", "open-in-new", "ghost", self, 16)
        self.open_btn.clicked.connect(self._open_first)
        footer.addWidget(self.open_btn)
        copy_btn = ActionButton("Copiar caminhos", "content-copy", "link", self, 15)
        copy_btn.clicked.connect(self._copy_paths)
        footer.addWidget(copy_btn)
        footer.addStretch(1)
        lay.addLayout(footer)

    def _open_item(self, item: QTreeWidgetItem, column: int) -> None:
        path = item.data(0, Qt.UserRole)
        if path:
            open_in_explorer(str(path), select=os.path.isfile(str(path)))

    def _open_first(self) -> None:
        if self.suggestion.paths:
            path = self.suggestion.paths[0]
            open_in_explorer(path, select=os.path.isfile(path))

    def _copy_paths(self) -> None:
        if self.suggestion.paths:
            copy_to_clipboard("\n".join(self.suggestion.paths))
            self.toastRequested.emit("Caminhos copiados para a área de transferência.", "info")


class RecommendationsPage(BasePage):
    page_id = "recommendations"
    page_title = "Recomendações"
    page_subtitle = "Como liberar espaço com segurança"
    page_icon = "lightbulb-on-outline"

    def __init__(self, state, parent: QWidget | None = None) -> None:
        super().__init__(state, parent)
        self._cards: list[SuggestionCard] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        self.header = PageHeader(
            "Recomendações inteligentes",
            "Sugestões calculadas a partir dos diretórios analisados. Nada é removido automaticamente.",
            "Limpeza segura",
        )
        view_btn = ActionButton("Ver análise", "file-tree-outline", "ghost")
        view_btn.clicked.connect(lambda: self.navigateRequested.emit("analyzer"))
        self.header.add_action(view_btn)
        self.rescan_btn = ActionButton("Reanalisar", "refresh", "primary")
        self.rescan_btn.clicked.connect(self._rescan)
        self.header.add_action(self.rescan_btn)
        root.addWidget(self.header)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("Page")
        body = QVBoxLayout(content)
        body.setContentsMargins(0, 0, 8, 4)
        body.setSpacing(14)

        body.addWidget(
            DisclaimerBanner(
                "O DiskPilot apenas recomenda: nenhum arquivo é removido. "
                "Duplicatas são comparadas por nome e tamanho, não por conteúdo. "
                "Valide cada caminho e o impacto na equipe antes de qualquer limpeza."
            )
        )

        # hero ------------------------------------------------------------
        self.hero = QFrame()
        self.hero.setObjectName("HeroCard")
        hl = QHBoxLayout(self.hero)
        hl.setContentsMargins(24, 20, 24, 20)
        hl.setSpacing(24)
        left = QVBoxLayout()
        left.setSpacing(3)
        eyebrow = QLabel("POTENCIAL DE LIMPEZA")
        eyebrow.setObjectName("HeroLabel")
        left.addWidget(eyebrow)
        value_row = QHBoxLayout()
        value_row.setSpacing(8)
        self.hero_value = QLabel("—")
        self.hero_value.setObjectName("HeroValue")
        value_row.addWidget(self.hero_value)
        unit = QLabel("com segurança")
        unit.setObjectName("Muted")
        unit.setAlignment(Qt.AlignBottom)
        value_row.addWidget(unit)
        value_row.addStretch(1)
        left.addLayout(value_row)
        self.hero_caption = QLabel(
            "Caches e artefatos que podem ser recriados automaticamente."
        )
        self.hero_caption.setObjectName("Muted")
        self.hero_caption.setWordWrap(True)
        left.addWidget(self.hero_caption)
        self.hero_date = QLabel("")
        self.hero_date.setObjectName("Faint")
        left.addWidget(self.hero_date)
        hl.addLayout(left, 1)

        metrics = QHBoxLayout()
        metrics.setSpacing(16)
        self.metric_review = self._metric(metrics, "EM REVISÃO", "—")
        self.metric_count = self._metric(metrics, "SUGESTÕES", "—")
        self.metric_safe = self._metric(metrics, "ITENS SEGUROS", "—")
        hl.addLayout(metrics)
        body.addWidget(self.hero)

        # filtro -----------------------------------------------------------
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        filter_label = QLabel("Filtrar")
        filter_label.setObjectName("Muted")
        filter_row.addWidget(filter_label)
        self.filter_btn = SelectButton("shield-check-outline", "Todas", self)
        self.filter_btn.set_options(
            [
                ("all", "Todas", "format-list-bulleted"),
                ("safe", "Seguras", "shield-check-outline"),
                ("review", "Revisar", "alert-outline"),
            ],
            "all",
        )
        self.filter_btn.changed.connect(lambda _key: self._rebuild_cards())
        filter_row.addWidget(self.filter_btn)
        self.count_label = QLabel("")
        self.count_label.setObjectName("Muted")
        filter_row.addWidget(self.count_label)
        filter_row.addStretch(1)
        disclaimer = QLabel("Nenhum arquivo é removido automaticamente.")
        disclaimer.setObjectName("Faint")
        filter_row.addWidget(disclaimer)
        body.addLayout(filter_row)

        self.cards_host = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_host)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(10)
        body.addWidget(self.cards_host)
        body.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        self.state.scanFinished.connect(self._rebuild)
        self.state.scanStarted.connect(self._on_scan_started)
        self.state.scanCancelled.connect(self._rebuild)
        self.state.scanFailed.connect(self._rebuild)
        self.state.resultsCleared.connect(self._rebuild)
        get_theme().changed.connect(lambda _key: self._rebuild())
        self._rebuild()

    @staticmethod
    def _metric(layout: QHBoxLayout, label: str, value: str) -> QLabel:
        box = QVBoxLayout()
        box.setSpacing(1)
        cap = QLabel(label)
        cap.setObjectName("HeroLabel")
        val = QLabel(value)
        val.setObjectName("HeroSmall")
        box.addWidget(cap)
        box.addWidget(val)
        layout.addLayout(box)
        return val

    def _rescan(self) -> None:
        if not self.state.roots:
            self.navigateRequested.emit("analyzer")
            return
        self.state.start_scan(force=True)

    def _on_scan_started(self) -> None:
        self.rescan_btn.setEnabled(False)
        self.header.subtitle.setText("Recalculando recomendações…")

    def on_show(self) -> None:
        self._rebuild()

    def _clear_cards(self) -> None:
        self._cards.clear()
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()

    def _rebuild(self, *_args: Any) -> None:
        self.rescan_btn.setEnabled(not self.state.is_scanning)
        summary = self.state.summary
        has = bool(summary)
        suggestions = self.state.suggestions
        safe_total = (
            sum(s.savings for s in suggestions if s.confidence == "safe")
            if suggestions
            else int(summary.get("safe_savings", 0)) if has else 0
        )
        review_total = (
            sum(s.savings for s in suggestions if s.confidence != "safe")
            if suggestions
            else int(summary.get("review_savings", 0)) if has else 0
        )
        self.hero_value.setText(format_bytes(safe_total) if has else "—")
        self.metric_review.setText(format_bytes(review_total) if has else "—")
        self.metric_count.setText(
            str(len(suggestions) if suggestions else int(summary.get("suggestion_count", 0)))
            if has
            else "—"
        )
        safe_items = sum(s.count for s in suggestions if s.confidence == "safe")
        self.metric_safe.setText(str(safe_items) if suggestions else "—")
        started = summary.get("started_at", 0) if has else 0
        self.hero_date.setText(
            f"Baseado na análise de {format_datetime(started)}" if started else ""
        )
        if has:
            n_suggestions = (
                len(suggestions)
                if suggestions
                else int(summary.get("suggestion_count", 0))
            )
            self.header.subtitle.setText(
                f"{n_suggestions} "
                + ("recomendação" if n_suggestions == 1 else "recomendações")
                + " · nada é removido automaticamente."
            )
        else:
            self.header.subtitle.setText(
                "Sugestões calculadas a partir dos diretórios analisados. Nada é removido automaticamente."
            )
        self._rebuild_cards()

    def _rebuild_cards(self) -> None:
        self._clear_cards()
        suggestions = self.state.suggestions
        filter_key = self.filter_btn.current() if hasattr(self, "filter_btn") else "all"
        if filter_key == "safe":
            visible = [s for s in suggestions if s.confidence == "safe"]
        elif filter_key == "review":
            visible = [s for s in suggestions if s.confidence != "safe"]
        else:
            visible = list(suggestions)
        self.count_label.setText(
            (
                f"{len(visible)} de {len(suggestions)} "
                + ("recomendação" if len(suggestions) == 1 else "recomendações")
            )
            if suggestions
            else ""
        )

        if not suggestions:
            summary = self.state.summary
            if summary:
                self._add_empty(
                    "Detalhes disponíveis após nova análise",
                    "Os totais da última análise foram preservados, mas os caminhos e detalhes por item "
                    "são recalculados a cada varredura. Execute uma nova análise para vê-los.",
                    "radar",
                )
            else:
                self._add_empty(
                    "Sem recomendações ainda",
                    "Adicione pastas e execute uma análise. O DiskPilot identificará caches, "
                    "artefatos de build, arquivos antigos e possíveis duplicatas.",
                    "lightbulb-on-outline",
                )
            return
        if not visible:
            self._add_empty(
                "Nenhuma recomendação neste filtro",
                "Mude o filtro de segurança para visualizar todas as sugestões.",
                "filter-off-outline",
            )
            return
        for suggestion in visible:
            card = SuggestionCard(suggestion, self.cards_host)
            card.toastRequested.connect(self.toast)
            self.cards_layout.addWidget(card)
            self._cards.append(card)

    def _add_empty(self, title: str, description: str, icon_name: str) -> None:
        empty = EmptyState(title, description, icon_name, self.cards_host)
        btn = ActionButton("Abrir análise", "file-tree-outline", "primary", empty)
        btn.clicked.connect(lambda: self.navigateRequested.emit("analyzer"))
        empty.add_action(btn)
        if self.state.roots:
            rescan = ActionButton("Reanalisar", "refresh", "ghost", empty)
            rescan.clicked.connect(lambda: self.state.start_scan(force=True))
            empty.add_action(rescan)
        self.cards_layout.addWidget(empty)
