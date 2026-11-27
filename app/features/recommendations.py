"""Página de recomendações com tabela ordenável, busca e cópia segura."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from appshell.utils import (
    copy_to_clipboard,
    format_bytes,
    format_datetime,
    normalize_path,
)
from appshell.widgets.buttons import ActionButton, SearchField, SelectButton
from appshell.widgets.common import DisclaimerBanner, EmptyState, PageHeader

from ..services.model import ScanResult, walk_nodes
from .base import BasePage
from .recommendation_section import RecommendationSection
from .recommendation_table import RecommendationRow

logger = logging.getLogger(__name__)


def _short_path(path: str, roots: list[str]) -> str:
    """Caminho abreviado; o caminho completo fica no tooltip e na cópia."""
    try:
        candidate = Path(path)
        for root in roots:
            try:
                relative = candidate.relative_to(Path(root))
            except ValueError:
                continue
            parts = relative.parts
            if not parts:
                return path
            suffix = "\\".join(parts[-4:])
            return f"…\\{suffix}" if len(parts) > 4 else "\\".join(parts)
        parts = candidate.parts
        if len(parts) > 4:
            return "…\\" + "\\".join(parts[-4:])
    except (OSError, ValueError):
        pass
    return path


class RecommendationsPage(BasePage):
    page_id = "recommendations"
    page_title = "Recomendações"
    page_subtitle = "Como liberar espaço com segurança"
    page_icon = "lightbulb-on-outline"

    def __init__(self, state, parent: QWidget | None = None) -> None:
        super().__init__(state, parent)
        self._rows: list[RecommendationRow] = []
        self._sections: list[RecommendationSection] = []
        self._collapsed_sections: set[str] = set()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        self.header = PageHeader(
            "Recomendações inteligentes",
            "Sugestões calculadas a partir dos diretórios analisados. "
            "Nada é removido automaticamente.",
            "Limpeza segura",
        )
        view_btn = ActionButton("Ver análise", "file-tree-outline", "ghost")
        view_btn.clicked.connect(lambda: self.navigateRequested.emit("analyzer"))
        self.header.add_action(view_btn)
        self.rescan_btn = ActionButton("Reanalisar", "refresh", "primary")
        self.rescan_btn.clicked.connect(self._rescan)
        self.header.add_action(self.rescan_btn)
        root.addWidget(self.header)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("Page")
        self.body = QVBoxLayout(content)
        self.body.setContentsMargins(0, 0, 8, 4)
        self.body.setSpacing(14)
        self.body.addWidget(
            DisclaimerBanner(
                "O DiskPilot apenas recomenda: nenhum arquivo é removido. "
                "Duplicatas são comparadas por nome e tamanho, não por conteúdo. "
                "Valide cada caminho e o impacto na equipe antes de qualquer limpeza."
            )
        )

        # hero -------------------------------------------------------------
        self.hero = QFrame()
        self.hero.setObjectName("HeroCard")
        hero_layout = QHBoxLayout(self.hero)
        hero_layout.setContentsMargins(24, 20, 24, 20)
        hero_layout.setSpacing(24)
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
        hero_layout.addLayout(left, 1)

        metrics = QHBoxLayout()
        metrics.setSpacing(16)
        self.metric_review = self._metric(metrics, "EM REVISÃO", "—")
        self.metric_count = self._metric(metrics, "SUGESTÕES", "—")
        self.metric_safe = self._metric(metrics, "ITENS SEGUROS", "—")
        hero_layout.addLayout(metrics)
        self.body.addWidget(self.hero)

        # busca e filtros --------------------------------------------------
        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self.search = SearchField(
            "Pesquisar sugestão, nome ou caminho.", 240, self
        )
        self.search.setMinimumWidth(260)
        self.search.setMaximumWidth(620)
        self.search.edit.setAccessibleName("Pesquisar recomendações")
        self.search.searchChanged.connect(self._apply_filters)
        search_row.addWidget(self.search, 1)
        self.copy_all_btn = ActionButton(
            "Copiar todos", "content-copy", "link", self, 15
        )
        self.copy_all_btn.setToolTip("Copiar todos os caminhos, um por linha")
        self.copy_all_btn.clicked.connect(self._copy_all)
        search_row.addWidget(self.copy_all_btn)
        self.body.addLayout(search_row)

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
        self.filter_btn.setToolTip(
            "Todas mostra qualquer sugestão; Seguras e Revisar limitam "
            "pela confiança da recomendação."
        )
        self.filter_btn.setAccessibleName("Filtro por confiança")
        self.filter_btn.changed.connect(
            lambda _key: self._apply_filters()
        )
        filter_row.addWidget(self.filter_btn)
        self.count_label = QLabel("")
        self.count_label.setObjectName("Muted")
        filter_row.addWidget(self.count_label)
        filter_row.addStretch(1)
        filter_hint = QLabel(
            "Pesquise por sugestão, nome ou caminho. "
            "Dê dois cliques para abrir o local no Explorer."
        )
        filter_hint.setObjectName("Faint")
        filter_hint.setWordWrap(True)
        filter_row.addWidget(filter_hint, 1)
        self.body.addLayout(filter_row)

        # seções por tipo --------------------------------------------------
        self.sections_host = QWidget(self)
        self.sections_layout = QVBoxLayout(self.sections_host)
        self.sections_layout.setContentsMargins(0, 0, 0, 0)
        self.sections_layout.setSpacing(10)
        self.body.addWidget(self.sections_host, 1)

        self.empty_host = QWidget(self)
        self.empty_layout = QVBoxLayout(self.empty_host)
        self.empty_layout.setContentsMargins(0, 0, 0, 0)
        self.empty_host.hide()
        self.body.addWidget(self.empty_host)

        self.scroll.setWidget(content)
        root.addWidget(self.scroll, 1)

        self.state.scanFinished.connect(self._rebuild)
        self.state.scanStarted.connect(self._on_scan_started)
        self.state.scanCancelled.connect(self._rebuild)
        self.state.scanFailed.connect(self._rebuild)
        self.state.resultsCleared.connect(self._rebuild)
        self.state.rootRemovalFinished.connect(self._rebuild)
        from appshell.theme import get_theme

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

    def _build_rows(self) -> list[RecommendationRow]:
        suggestions = self.state.suggestions
        result: ScanResult | None = self.state.last_result
        index = self.state.search_index
        paths = [path for suggestion in suggestions for path in suggestion.paths]
        nodes: dict[str, Any] = {}

        if index is not None and paths:
            try:
                for node in index.nodes_by_paths(paths):
                    nodes[normalize_path(node.path)] = node
            except Exception:
                logger.exception("falha ao resolver caminhos das recomendações")
        elif result is not None and paths:
            total_nodes = result.total_files + result.total_dirs
            # Evita congelar a interface em resultados muito grandes sem índice.
            if total_nodes <= 250_000:
                wanted = {normalize_path(path) for path in paths}
                for root in result.roots:
                    for node in walk_nodes(root):
                        key = normalize_path(node.path)
                        if key in wanted:
                            nodes[key] = node

        roots = [root.path for root in result.roots] if result else []
        total_size = max(1, result.total_size if result else 0)
        rows: list[RecommendationRow] = []
        for suggestion in suggestions:
            for path in suggestion.paths:
                node = nodes.get(normalize_path(path))
                size = int(node.size) if node is not None else None
                items = (
                    int(node.files) + int(node.dirs)
                    if node is not None
                    else None
                )
                rows.append(
                    RecommendationRow(
                        suggestion=suggestion,
                        path=path,
                        display_path=_short_path(path, roots),
                        name=node.name if node is not None else Path(path).name,
                        size=size,
                        percent=(size / total_size * 100.0) if size else 0.0,
                        items=items,
                        mtime=float(node.mtime) if node is not None else 0.0,
                        kind=(
                            "Pasta"
                            if node is not None and node.is_dir
                            else "Arquivo"
                            if node is not None
                            else ""
                        ),
                        confidence=suggestion.confidence,
                    )
                )
        return rows

    def _rebuild(self, *_args: Any) -> None:
        self.rescan_btn.setEnabled(not self.state.is_scanning)
        summary = self.state.summary
        has = bool(summary)
        truncated = bool(summary.get("truncated")) if has else False
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
            str(
                len(suggestions)
                if suggestions
                else int(summary.get("suggestion_count", 0))
            )
            if has
            else "—"
        )
        safe_items = sum(
            s.count for s in suggestions if s.confidence == "safe"
        )
        self.metric_safe.setText(
            str(safe_items) if suggestions else "—"
        )
        started = summary.get("started_at", 0) if has else 0
        self.hero_date.setText(
            f"Baseado na análise de {format_datetime(started)}"
            if started
            else ""
        )
        if has:
            n_suggestions = (
                len(suggestions)
                if suggestions
                else int(summary.get("suggestion_count", 0))
            )
            self.header.subtitle.setText(
                f"{n_suggestions} "
                + (
                    "recomendação"
                    if n_suggestions == 1
                    else "recomendações"
                )
                + (
                    " — resultado parcial; os totais podem estar incompletos."
                    if truncated
                    else " — nada é removido automaticamente."
                )
            )
        else:
            self.header.subtitle.setText(
                "Sugestões calculadas a partir dos diretórios analisados. "
                "Nada é removido automaticamente."
            )

        self._rows = self._build_rows()
        self._build_sections(suggestions)
        self._apply_filters()

    def _clear_sections(self) -> None:
        while self.sections_layout.count():
            item = self.sections_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        self._sections.clear()

    def _build_sections(self, suggestions) -> None:
        self._clear_sections()
        by_key: dict[str, list[RecommendationRow]] = {}
        for row in self._rows:
            by_key.setdefault(row.suggestion.key, []).append(row)
        for suggestion in suggestions:
            rows = by_key.get(suggestion.key, [])
            if not rows:
                continue
            section = RecommendationSection(
                suggestion,
                rows,
                expanded=suggestion.key not in self._collapsed_sections,
                parent=self.sections_host,
            )
            section.statusMessage.connect(
                lambda message: self.toast(message, "info")
            )
            section.expandedChanged.connect(self._on_section_expanded)
            self.sections_layout.addWidget(section)
            self._sections.append(section)
        self.sections_host.setVisible(bool(self._sections))

    def _on_section_expanded(self, key: str, expanded: bool) -> None:
        if expanded:
            self._collapsed_sections.discard(key)
        else:
            self._collapsed_sections.add(key)

    def _copy_all(self) -> None:
        if not self._rows:
            self.toast("Nenhum caminho para copiar.", "info")
            return
        copy_to_clipboard("\n".join(row.path for row in self._rows))
        self.toast(f"{len(self._rows)} caminho(s) copiado(s).", "info")

    def _apply_filters(self, *_args: Any) -> None:
        query = self.search.text()
        confidence = self.filter_btn.current()
        visible = sum(
            section.apply_filter(query, confidence)
            for section in self._sections
        )
        total = len(self._rows)
        self.count_label.setText(
            f"{visible} de {total} caminho(s)" if total else ""
        )
        self.empty_host.hide()
        self.sections_host.show()
        suggestions = self.state.suggestions
        if not suggestions or not self._rows:
            self._show_empty_for_no_suggestions()
            return
        if visible == 0:
            self._show_filter_empty()
            return
        self.sections_host.show()

    def _clear_empty(self) -> None:
        while self.empty_layout.count():
            item = self.empty_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()

    def _show_empty(
        self, title: str, description: str, icon_name: str
    ) -> None:
        self.sections_host.hide()
        self.empty_host.show()
        self._clear_empty()
        empty = EmptyState(title, description, icon_name, self.empty_host)
        self.empty_layout.addWidget(empty)
        if not self.state.roots:
            action = ActionButton(
                "Abrir análise", "file-tree-outline", "primary", empty
            )
            action.clicked.connect(
                lambda: self.navigateRequested.emit("analyzer")
            )
            empty.add_action(action)
        else:
            rescan = ActionButton("Reanalisar", "refresh", "ghost", empty)
            rescan.clicked.connect(
                lambda: self.state.start_scan(force=True)
            )
            empty.add_action(rescan)

    def _show_empty_for_no_suggestions(self) -> None:
        summary = self.state.summary
        if summary:
            self._show_empty(
                "Nenhuma recomendação persistida",
                "A última análise não gerou recomendações de limpeza. "
                "Execute uma nova análise para recalcular os detalhes.",
                "radar",
            )
        else:
            self._show_empty(
                "Sem recomendações ainda",
                "Adicione pastas e execute uma análise. O DiskPilot identificará "
                "caches, artefatos de build, arquivos antigos e possíveis duplicatas.",
                "lightbulb-on-outline",
            )

    def _show_filter_empty(self) -> None:
        self.sections_host.hide()
        self.empty_host.show()
        self._clear_empty()
        empty = EmptyState(
            "Nenhum caminho neste filtro",
            "Mude a busca ou o filtro de confiança para visualizar outros caminhos.",
            "filter-off-outline",
            self.empty_host,
        )
        clear = ActionButton(
            "Limpar filtros", "filter-remove-outline", "primary", empty
        )
        clear.clicked.connect(self._clear_filters)
        empty.add_action(clear)
        self.empty_layout.addWidget(empty)

    def _clear_filters(self) -> None:
        self.search.clear()
        self.filter_btn.set_current("all", emit=False)
        self._apply_filters()

    # Compatibilidade com testes/consumidores antigos.
    def _rebuild_cards(self) -> None:
        self._apply_filters()
