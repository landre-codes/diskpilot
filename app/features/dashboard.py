"""Mini-dashboard da página inicial."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..services.model import Suggestion
from ..theme import get_theme
from ..utils import format_bytes, format_datetime, format_number
from ..widgets.buttons import ActionButton
from ..widgets.charts import BarList, DonutChart
from ..widgets.common import (
    Card,
    DisclaimerBanner,
    ElidedLabel,
    IconLabel,
    PageHeader,
    StatCard,
)
from ..widgets.dialogs import FolderPickerDialog
from .base import BasePage


class DashboardPage(BasePage):
    page_id = "dashboard"
    page_title = "Visão geral"
    page_subtitle = "Parâmetros tratados na última análise"
    page_icon = "view-dashboard-outline"

    def __init__(self, state, parent: QWidget | None = None) -> None:
        super().__init__(state, parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        self.header = PageHeader(
            "Painel de armazenamento",
            "Um resumo dos diretórios analisados, distribuição do espaço e recomendações.",
            "Visão geral",
        )
        open_btn = ActionButton("Abrir análise", "file-tree-outline", "ghost")
        open_btn.clicked.connect(lambda: self.navigateRequested.emit("analyzer"))
        self.header.add_action(open_btn)
        add_btn = ActionButton("Adicionar pastas", "folder-plus-outline", "primary")
        add_btn.clicked.connect(self._add_folders)
        self.header.add_action(add_btn)
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
                "Somente leitura: o DiskPilot não apaga arquivos nem pastas. "
                "Tamanhos e sugestões são estimativas — confira os caminhos e o "
                "impacto antes de qualquer limpeza. O uso dos dados é de "
                "responsabilidade do usuário."
            )
        )

        # KPIs ------------------------------------------------------------
        stats = QHBoxLayout()
        stats.setSpacing(12)
        self.card_size = StatCard(
            "Espaço analisado", "—", "Nenhuma análise carregada", "harddisk", "primary"
        )
        self.card_files = StatCard(
            "Arquivos", "—", "Inclui arquivos ocultos", "file-multiple-outline", "info"
        )
        self.card_dirs = StatCard(
            "Pastas", "—", "Inclui todas as subpastas", "folder-multiple-outline", "primary"
        )
        self.card_safe = StatCard(
            "Espaço liberável",
            "—",
            "Caches e itens regeneráveis",
            "shield-check-outline",
            "success",
        )
        for card in (self.card_size, self.card_files, self.card_dirs, self.card_safe):
            stats.addWidget(card, 1)
        body.addLayout(stats)

        # gráficos --------------------------------------------------------
        charts = QHBoxLayout()
        charts.setSpacing(14)
        dist_card = Card(
            "Distribuição por pasta",
            "Participação de cada raiz no total analisado.",
        )
        self.donut = DonutChart()
        dist_card.body.addWidget(self.donut)
        charts.addWidget(dist_card, 3)

        top_card = Card(
            "Maiores diretórios",
            "Filhos diretos das raízes, por tamanho.",
        )
        self.bars = BarList()
        top_card.body.addWidget(self.bars)
        charts.addWidget(top_card, 2)
        body.addLayout(charts)

        # recomendações + última análise ---------------------------------
        bottom = QHBoxLayout()
        bottom.setSpacing(14)
        self.rec_card = Card(
            "Sugestões para liberar espaço",
            "Geradas a partir da última varredura.",
        )
        self.rec_all = ActionButton("Ver todas", "arrow-right", "link")
        self.rec_all.clicked.connect(lambda: self.navigateRequested.emit("recommendations"))
        self.rec_card.add_header_action(self.rec_all)
        self.rec_box = QVBoxLayout()
        self.rec_box.setSpacing(8)
        self.rec_box.setContentsMargins(0, 0, 0, 0)
        self.rec_card.body.addLayout(self.rec_box)
        self.rec_card.body.addStretch(1)
        bottom.addWidget(self.rec_card, 2)

        self.last_card = Card(
            "Última análise",
            "Resumo operacional da varredura mais recente.",
        )
        self.last_status = QLabel("Sem dados")
        self.last_status.setObjectName("Badge")
        self.last_card.add_header_action(self.last_status)
        info = QVBoxLayout()
        info.setSpacing(7)
        self.info_values: dict[str, QLabel] = {}
        for key, label in (
            ("data", "Data"),
            ("duracao", "Duração"),
            ("pastas", "Pastas"),
            ("arquivos", "Arquivos"),
            ("avisos", "Avisos de acesso"),
            ("sugestoes", "Sugestões"),
        ):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            left = QLabel(label)
            left.setObjectName("InfoLabel")
            value = QLabel("—")
            value.setObjectName("InfoValue")
            value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row.addWidget(left)
            row.addStretch(1)
            row.addWidget(value)
            info.addLayout(row)
            self.info_values[key] = value
        self.last_card.body.addLayout(info)
        self.last_card.body.addStretch(1)
        self.last_scan_btn = ActionButton("Executar nova análise", "play", "soft")
        self.last_scan_btn.clicked.connect(self._scan_now)
        self.last_card.body.addWidget(self.last_scan_btn)
        bottom.addWidget(self.last_card, 1)
        body.addLayout(bottom)
        body.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        self.state.scanFinished.connect(self._refresh)
        self.state.scanStarted.connect(self._on_scan_started)
        self.state.rootsChanged.connect(self._refresh)
        self.state.resultsCleared.connect(self._refresh)
        self.state.scanCancelled.connect(self._refresh)
        self.state.scanFailed.connect(self._refresh)
        get_theme().changed.connect(lambda _key: self._refresh())
        self._refresh()

    # ------------------------------------------------------------------ ações
    def _add_folders(self) -> None:
        start = self.state.roots[-1] if self.state.roots else ""
        dialog = FolderPickerDialog(self.window(), start)
        result = dialog.exec()
        paths = dialog.selected_paths() if result == QDialog.Accepted else []
        # Mesma proteção da página de análise: o diálogo e o file-system
        # watcher precisam sair de cena antes da próxima varredura.
        dialog.deleteLater()
        if result != QDialog.Accepted:
            return
        if not paths:
            return
        added = self.state.add_roots(paths, autoscan=False)
        if not added:
            self.toast("Essas pastas já estão na análise.", "info")
            return
        self.toast(f"{len(added)} pasta(s) adicionada(s). Iniciando análise…", "info")
        QTimer.singleShot(100, self.state.start_scan)
        self.navigateRequested.emit("analyzer")

    def _scan_now(self) -> None:
        if not self.state.roots:
            self._add_folders()
            return
        self.state.start_scan(force=True)
        self.navigateRequested.emit("analyzer")

    def on_show(self) -> None:
        self._refresh()

    # --------------------------------------------------------------- refresh
    def _on_scan_started(self) -> None:
        self.last_status.setText("Em andamento")
        self.last_status.setObjectName("BadgeInfo")
        self._repolish(self.last_status)
        self.last_scan_btn.setEnabled(False)
        self.header.subtitle.setText("Análise em andamento — os números serão atualizados automaticamente.")

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _clear_rec_box(self) -> None:
        while self.rec_box.count():
            item = self.rec_box.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
            elif item.layout() is not None:
                self._clear_layout(item.layout())

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
            elif item.layout() is not None:
                self._clear_layout(item.layout())

    def _refresh(self, *_args: Any) -> None:
        summary = self.state.summary
        has = bool(summary)
        roots = summary.get("roots", []) if has else []
        total_size = int(summary.get("total_size", 0)) if has else 0
        total_files = int(summary.get("total_files", 0)) if has else 0
        total_dirs = int(summary.get("total_dirs", 0)) if has else 0
        safe = int(summary.get("safe_savings", 0)) if has else 0
        review = int(summary.get("review_savings", 0)) if has else 0
        errors = int(summary.get("errors", 0)) if has else 0
        suggestions = self.state.suggestions
        pending = not has and bool(self.state.roots)

        self.card_size.set_value(
            format_bytes(total_size) if has else "—",
            (
                f"{format_number(len(roots))} "
                + ("pasta monitorada" if len(roots) == 1 else "pastas monitoradas")
            )
            if has
            else (
                "Execute uma análise para calcular"
                if pending
                else "Adicione pastas para começar"
            ),
        )
        self.card_files.set_value(
            format_number(total_files) if has else "—",
            (
                f"Média: {format_bytes(total_size / total_files)} por arquivo"
                if total_files
                else "Nenhum arquivo lido ainda"
            )
            if has
            else (
                "Execute uma análise para calcular"
                if pending
                else "Nenhum arquivo lido ainda"
            ),
        )
        self.card_dirs.set_value(
            format_number(total_dirs) if has else "—",
            "Pastas e subpastas" if has else (
                "Execute uma análise para calcular" if pending else "Nenhuma pasta lida ainda"
            ),
        )
        self.card_safe.set_value(
            format_bytes(safe) if has else "—",
            (
                (
                    f"{len(suggestions) if suggestions else int(summary.get('suggestion_count', 0))} sugestões"
                    + (f" · {format_bytes(review)} p/ revisar" if review else "")
                )
                if has
                else "Analise para calcular"
            ),
        )

        # donut
        colors = get_theme().chart_colors()
        entries = sorted(
            [
                (str(r.get("name", "Pasta")), int(r.get("size", 0)))
                for r in roots
                if int(r.get("size", 0)) > 0
            ],
            key=lambda item: item[1],
            reverse=True,
        )
        chart_data: list[tuple[str, int, str]] = []
        if len(entries) > 5:
            head = entries[:5]
            other = sum(v for _, v in entries[5:])
            chart_data = [
                (label, value, colors[i % len(colors)])
                for i, (label, value) in enumerate(head)
            ]
            if other > 0:
                chart_data.append(("Outras pastas", other, colors[5 % len(colors)]))
        else:
            chart_data = [
                (label, value, colors[i % len(colors)])
                for i, (label, value) in enumerate(entries)
            ]
        self.donut.set_data(chart_data)

        # barras
        top = summary.get("top_dirs", []) if has else []
        self.bars.set_data(
            [(str(t.get("name", "Pasta")), int(t.get("size", 0))) for t in top[:7]],
            total_size,
        )

        # recomendações
        self._clear_rec_box()
        if suggestions:
            for suggestion in suggestions[:2]:
                self.rec_box.addWidget(self._suggestion_row(suggestion))
        else:
            empty = QLabel(
                "Nenhuma recomendação calculada nesta sessão. Execute uma nova análise "
                "para identificar caches, duplicatas e arquivos antigos."
                if has
                else "Adicione pastas e execute uma análise para receber recomendações de limpeza segura."
            )
            empty.setObjectName("Muted")
            empty.setWordWrap(True)
            self.rec_box.addWidget(empty)

        # última análise
        started = summary.get("started_at", 0) if has else 0
        self.info_values["data"].setText(format_datetime(started) if started else "—")
        self.info_values["duracao"].setText(
            f"{float(summary.get('elapsed', 0)):.1f}s" if has else "—"
        )
        self.info_values["pastas"].setText(
            format_number(len(roots)) if has else str(len(self.state.roots))
        )
        self.info_values["arquivos"].setText(format_number(total_files) if has else "—")
        self.info_values["avisos"].setText(format_number(errors) if has else "—")
        self.info_values["sugestoes"].setText(
            format_number(len(suggestions) if suggestions else summary.get("suggestion_count", 0))
            if has
            else "—"
        )
        if has:
            if self.state.is_scanning:
                self.last_status.setText("Em andamento")
                self.last_status.setObjectName("BadgeInfo")
            elif errors:
                self.last_status.setText("Com avisos")
                self.last_status.setObjectName("BadgeWarn")
            else:
                self.last_status.setText("Concluída")
                self.last_status.setObjectName("BadgeSuccess")
            self.last_scan_btn.setEnabled(not self.state.is_scanning)
        else:
            self.last_status.setText("Sem dados")
            self.last_status.setObjectName("Badge")
            self.last_scan_btn.setEnabled(True)
        self._repolish(self.last_status)
        self.last_scan_btn.set_icon_name("refresh" if self.state.is_scanning else "play")
        self._update_subtitle(has, started)

    def _update_subtitle(self, has: bool, started: float) -> None:
        if self.state.is_scanning:
            self.header.subtitle.setText("Análise em andamento — os números serão atualizados automaticamente.")
        elif has and started:
            self.header.subtitle.setText(
                f"Última leitura em {format_datetime(started)} · "
                "distribuição, maiores diretórios e recomendações."
            )
        elif self.state.roots:
            count = len(self.state.roots)
            self.header.subtitle.setText(
                f"{count} pasta{'s' if count != 1 else ''} pronta{'s' if count != 1 else ''} para analisar. "
                "Execute a análise para preencher o painel."
            )
        else:
            self.header.subtitle.setText(
                "Um resumo dos diretórios analisados, distribuição do espaço e recomendações."
            )

    def _suggestion_row(self, suggestion: Suggestion) -> QWidget:
        safe = suggestion.confidence == "safe"
        row = QFrame(self)
        row.setObjectName("InlineInfo")
        row.setFixedHeight(66)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(10, 8, 12, 8)
        lay.setSpacing(10)
        tile = QFrame(row)
        tile.setObjectName("IconTileSuccess" if safe else "IconTileWarn")
        tile.setFixedSize(36, 36)
        tl = QHBoxLayout(tile)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(
            IconLabel(
                suggestion.icon,
                18,
                "success" if safe else "warn",
                tile,
            ),
            0,
            Qt.AlignCenter,
        )
        lay.addWidget(tile)
        text = QVBoxLayout()
        text.setSpacing(1)
        title = ElidedLabel(suggestion.title)
        title.setObjectName("RowTitle")
        subtitle = ElidedLabel(
            f"{suggestion.count} {'item' if suggestion.count == 1 else 'itens'} · "
            + ("pode ser recriado automaticamente" if safe else "revisar antes de remover")
        )
        subtitle.setObjectName("RowSub")
        text.addWidget(title)
        text.addWidget(subtitle)
        lay.addLayout(text, 1)
        value = QLabel(format_bytes(suggestion.savings))
        value.setObjectName("RowValue")
        lay.addWidget(value)
        badge = QLabel("Seguro" if safe else "Revisar")
        badge.setObjectName("BadgeSuccess" if safe else "BadgeWarn")
        lay.addWidget(badge)
        return row
