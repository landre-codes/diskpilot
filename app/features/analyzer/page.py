"""Página de análise: pastas, filtros, árvore e progresso."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from ...services.model import ScanProgress, ScanResult
from ...utils import format_bytes, format_number
from ...widgets.buttons import ActionButton, IconButton, SearchField, SelectButton
from ...widgets.common import Chip, ElidedLabel, EmptyState, PageHeader
from ...widgets.dialogs import ExportDialog, FolderPickerDialog, TopItemsDialog
from ..base import BasePage
from .tree import FileTree


class AnalyzerPage(BasePage):
    page_id = "analyzer"
    page_title = "Análise de diretórios"
    page_subtitle = "Descubra onde o espaço está sendo usado"
    page_icon = "folder-search-outline"

    def __init__(self, state, parent: QWidget | None = None) -> None:
        super().__init__(state, parent)
        self._last_matches: int | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        self.header = PageHeader(
            "Análise de diretórios",
            "Selecione uma ou mais pastas para mapear onde o espaço está sendo usado.",
            "Armazenamento",
        )
        self.top_btn = ActionButton("Top 100", "podium", "ghost")
        self.top_btn.setToolTip("Ver os 100 maiores diretórios e arquivos da última análise")
        self.top_btn.clicked.connect(self._open_top_items)
        self.header.add_action(self.top_btn)
        self.export_btn = ActionButton("Exportar", "export-variant", "ghost")
        self.export_btn.setToolTip("Exportar análise em CSV, XLSX ou XLSB")
        self.export_btn.clicked.connect(self._open_export)
        self.header.add_action(self.export_btn)
        self.rescan_btn = ActionButton("Reanalisar", "refresh", "ghost")
        self.rescan_btn.clicked.connect(self._rescan)
        self.header.add_action(self.rescan_btn)
        self.add_btn = ActionButton("Adicionar pastas", "folder-plus-outline", "primary")
        self.add_btn.clicked.connect(self.add_folders)
        self.header.add_action(self.add_btn)
        root.addWidget(self.header)

        # chips de raízes -------------------------------------------------
        self.chips_area = QScrollArea(self)
        self.chips_area.setWidgetResizable(True)
        self.chips_area.setFixedHeight(42)
        self.chips_area.setFrameShape(QFrame.NoFrame)
        self.chips_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.chips_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.chips_host = QWidget()
        self.chips_layout = QHBoxLayout(self.chips_host)
        self.chips_layout.setContentsMargins(0, 1, 0, 1)
        self.chips_layout.setSpacing(7)
        self.chips_area.setWidget(self.chips_host)
        root.addWidget(self.chips_area)

        # toolbar ----------------------------------------------------------
        toolbar = QFrame(self)
        toolbar.setObjectName("Card")
        tb = QVBoxLayout(toolbar)
        tb.setContentsMargins(10, 8, 10, 8)
        tb.setSpacing(7)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self.search = SearchField("Pesquisar por nome de arquivo ou pasta…", 260, self)
        self.search.setMinimumWidth(175)
        self.search.setMaximumWidth(520)
        self.search.setToolTip("Pesquisar por nome de arquivo ou pasta")
        self.search.searchChanged.connect(self._on_search)
        search_row.addWidget(self.search, 4)
        self.count_label = ElidedLabel("")
        self.count_label.setObjectName("Muted")
        self.count_label.setMinimumWidth(220)
        self.count_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        search_row.addWidget(self.count_label, 1)
        tb.addLayout(search_row)

        controls_row = QHBoxLayout()
        controls_row.setSpacing(8)
        self.unit_label = QLabel("Unidade")
        self.unit_label.setObjectName("Muted")
        controls_row.addWidget(self.unit_label, 0, Qt.AlignVCenter)
        self.unit_btn = SelectButton("numeric", "Auto", self)
        self.unit_btn.setMinimumWidth(100)
        self.unit_btn.setMaximumWidth(112)
        self.unit_btn.setToolTip("Unidade de exibição dos tamanhos")
        self.unit_btn.set_options(
            [
                ("auto", "Auto", "numeric"),
                ("KB", "KB", "alpha-k-box-outline"),
                ("MB", "MB", "alpha-m-box-outline"),
                ("GB", "GB", "alpha-g-box-outline"),
                ("TB", "TB", "alpha-t-box-outline"),
            ],
            self.state.config.get("ui.size_unit", "auto"),
        )
        self.unit_btn.changed.connect(self._on_unit)
        controls_row.addWidget(self.unit_btn)
        self.filter_btn = SelectButton("filter-variant", "Tudo", self)
        self.filter_btn.setMinimumWidth(116)
        self.filter_btn.set_options(
            [
                ("all", "Tudo", "filter-variant"),
                ("folders", "Pastas", "folder-outline"),
                ("files", "Arquivos", "file-outline"),
                ("large100", "> 100 MB", "file-alert-outline"),
                ("large1g", "> 1 GB", "database-alert-outline"),
            ],
            self.state.config.get("ui.tree_filter", "all"),
        )
        self.filter_btn.changed.connect(self._on_filter)
        controls_row.addWidget(self.filter_btn)
        self.sort_btn = SelectButton("sort", "Tamanho", self)
        self.sort_btn.setMinimumWidth(126)
        self.sort_btn.setToolTip("Ordenar os itens exibidos")
        self.sort_btn.set_chevron(False)
        self.sort_btn.set_options(
            [
                ("size_desc", "Tamanho ↓", "sort-descending"),
                ("size_asc", "Tamanho ↑", "sort-ascending"),
                ("name_asc", "Nome A–Z", "sort-alphabetical-ascending"),
                ("name_desc", "Nome Z–A", "sort-alphabetical-descending"),
                ("recent", "Recentes", "clock-outline"),
            ],
            self.state.config.get("ui.tree_sort", "size_desc"),
        )
        self.sort_btn.changed.connect(self._on_sort)
        controls_row.addWidget(self.sort_btn)
        self.path_check = QCheckBox("Caminho completo")
        self.path_check.setToolTip("Mostrar a coluna com o caminho completo")
        self.path_check.setChecked(bool(self.state.config.get("ui.tree_path", False)))
        self.path_check.toggled.connect(self._on_path_toggle)
        controls_row.addWidget(self.path_check)
        self.readonly_hint = QLabel("Somente leitura · nada é apagado")
        self.readonly_hint.setObjectName("Faint")
        self.readonly_hint.setToolTip(
            "O DiskPilot não apaga arquivos nem pastas. Os tamanhos são lógicos "
            "e podem diferir do espaço físico em arquivos esparsos/comprimidos. "
            "O uso dos dados é de responsabilidade do usuário."
        )
        controls_row.addWidget(self.readonly_hint, 0, Qt.AlignVCenter)
        controls_row.addStretch(1)
        self.expand_btn = IconButton("expand-all-outline", "Expandir tudo", self, 17)
        self.expand_btn.clicked.connect(self._expand_bounded)
        controls_row.addWidget(self.expand_btn)
        self.collapse_btn = IconButton("collapse-all-outline", "Recolher tudo", self, 17)
        self.collapse_btn.clicked.connect(lambda: self.tree.collapseAll())
        controls_row.addWidget(self.collapse_btn)
        tb.addLayout(controls_row)
        root.addWidget(toolbar)

        # banner de progresso ---------------------------------------------
        self.banner = QFrame(self)
        self.banner.setObjectName("ScanBanner")
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(13, 10, 10, 10)
        bl.setSpacing(12)
        self.banner_icon = QLabel(self)
        from ...widgets.common import IconLabel

        self.banner_icon = IconLabel("radar", 20, "primary", self)
        bl.addWidget(self.banner_icon)
        banner_text = QVBoxLayout()
        banner_text.setContentsMargins(0, 0, 0, 0)
        banner_text.setSpacing(1)
        self.banner_title = ElidedLabel("Analisando pastas…")
        self.banner_title.setObjectName("ScanText")
        self.banner_path = QLabel("")
        self.banner_path.setObjectName("PathText")
        self.banner_path.setWordWrap(True)
        self.banner_path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        banner_text.addWidget(self.banner_title)
        banner_text.addWidget(self.banner_path)
        bl.addLayout(banner_text, 1)
        self.scan_bar = QProgressBar(self)
        self.scan_bar.setObjectName("ScanBar")
        self.scan_bar.setTextVisible(False)
        self.scan_bar.setRange(0, 0)
        self.scan_bar.setFixedWidth(150)
        bl.addWidget(self.scan_bar)
        self.cancel_btn = ActionButton("Cancelar", "close", "ghost", self, 15)
        self.cancel_btn.clicked.connect(self._cancel_scan)
        bl.addWidget(self.cancel_btn)
        self.banner.hide()
        root.addWidget(self.banner)

        # árvore / estado vazio -------------------------------------------
        self.stack_host = QWidget(self)
        self.stack = QStackedLayout(self.stack_host)
        self.stack.setContentsMargins(0, 0, 0, 0)
        self.tree = FileTree(self.stack_host)
        self.tree.set_unit(self.unit_btn.current())
        self.tree.set_path_visible(self.path_check.isChecked())
        self.tree.countChanged.connect(self._on_count)
        self.tree.statusMessage.connect(lambda msg: self.toast(msg, "info"))
        self.stack.addWidget(self.tree)
        self.empty = EmptyState(
            "Nenhuma pasta analisada",
            "Adicione uma ou mais pastas para comparar tamanhos, navegar pelos arquivos e receber sugestões de limpeza segura.",
            "folder-search-outline",
        )
        self.empty_add = ActionButton("Adicionar pastas", "folder-plus-outline", "primary", self.empty)
        self.empty_add.clicked.connect(self.add_folders)
        self.empty.add_action(self.empty_add)
        self.empty_scan = ActionButton("Analisar agora", "play", "ghost", self.empty)
        self.empty_scan.clicked.connect(lambda: self.state.start_scan())
        self.empty.add_action(self.empty_scan)
        self.empty_clear = ActionButton("Limpar filtros", "filter-remove-outline", "ghost", self.empty)
        self.empty_clear.clicked.connect(self.clear_filters)
        self.empty.add_action(self.empty_clear)
        self.stack.addWidget(self.empty)
        root.addWidget(self.stack_host, 1)
        self.path_detail = QLabel("")
        self.path_detail.setObjectName("PathText")
        self.path_detail.setWordWrap(True)
        self.path_detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.path_detail.setVisible(False)
        root.addWidget(self.path_detail)
        self.tree.currentItemChanged.connect(self._update_path_detail)

        # conexões ---------------------------------------------------------
        self.state.rootsChanged.connect(self._refresh_roots)
        self.state.scanStarted.connect(self._on_scan_started)
        self.state.scanProgress.connect(self._on_progress)
        self.state.scanFinished.connect(self._on_scan_finished)
        self.state.scanCancelled.connect(self._on_scan_cancelled)
        self.state.scanFailed.connect(self._on_scan_failed)
        self.state.resultsCleared.connect(self._on_results_cleared)

        self._refresh_roots()
        if self.state.last_result is not None:
            self.tree.set_result(self.state.last_result)
        self._update_empty()

    # --------------------------------------------------------------- raízes
    def _clear_chips(self) -> None:
        while self.chips_layout.count():
            item = self.chips_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _refresh_roots(self) -> None:
        self._clear_chips()
        for path in self.state.roots:
            chip = Chip(path, self.chips_host)
            chip.removeRequested.connect(self._remove_root)
            self.chips_layout.addWidget(chip)
        self.chips_layout.addStretch(1)
        self.chips_area.setVisible(bool(self.state.roots))
        self._update_header()
        self._update_empty()

    def _remove_root(self, path: str) -> None:
        self.state.remove_root(path)
        self.toast("Pasta removida da análise.", "info")

    def _update_header(self) -> None:
        result = self.state.last_result
        count = len(self.state.roots)
        self.top_btn.setEnabled(result is not None)
        self.export_btn.setEnabled(result is not None)
        if result is not None:
            errors = f" · {result.errors} avisos" if result.errors else ""
            self.header.subtitle.setText(
                f"{count} pasta{'s' if count != 1 else ''} · "
                f"{format_bytes(result.total_size)} · "
                f"{format_number(result.total_files)} arquivos{errors}"
            )
        elif count:
            self.header.subtitle.setText(
                f"{count} pasta{'s' if count != 1 else ''} selecionada{'s' if count != 1 else ''}. "
                "Execute a análise para ver os tamanhos."
            )
        else:
            self.header.subtitle.setText(
                "Selecione uma ou mais pastas para mapear onde o espaço está sendo usado."
            )

    # ------------------------------------------------------------- adicionar
    def add_folders(self) -> None:
        start = self.state.roots[-1] if self.state.roots else ""
        dialog = FolderPickerDialog(self.window(), start)
        result = dialog.exec()
        paths = dialog.selected_paths() if result == QDialog.Accepted else []
        # O seletor usa QFileSystemModel e watchers nativos. Deixamos ele ser
        # destruído antes de iniciar a varredura; iniciar a varredura
        # imediatamente após o exec podia derrubar a aplicação no Windows.
        dialog.deleteLater()
        if result != QDialog.Accepted:
            return
        if not paths:
            return
        added = self.state.add_roots(paths, autoscan=False)
        if not added:
            self.toast("Essas pastas já estão na análise.", "info")
            return
        noun = "pasta adicionada" if len(added) == 1 else "pastas adicionadas"
        self.toast(f"{len(added)} {noun}. Iniciando análise…", "info")
        QTimer.singleShot(100, self.state.start_scan)

    def _rescan(self) -> None:
        if not self.state.roots:
            self.add_folders()
            return
        self.state.start_scan(force=True)
        self.toast("Reanalisando as pastas selecionadas…", "info")

    def _open_top_items(self) -> None:
        result = self.state.last_result
        if result is None:
            self.toast("Execute uma análise para gerar o ranking.", "info")
            return
        dialog = TopItemsDialog(self.window(), result)
        dialog.exec()
        dialog.deleteLater()

    def _open_export(self) -> None:
        result = self.state.last_result
        if result is None:
            self.toast("Execute uma análise para exportar os dados.", "info")
            return
        dialog = ExportDialog(self.window(), result)
        if dialog.exec() == QDialog.Accepted and dialog.exported_path:
            self.toast(f"Dados exportados: {Path(dialog.exported_path).name}", "success")
        dialog.deleteLater()

    # --------------------------------------------------------------- filtros
    def _on_search(self, text: str) -> None:
        self.tree.set_query(text)
        self._update_empty()

    def _on_filter(self, key: str) -> None:
        self.state.config.set("ui.tree_filter", key)
        self.tree.set_filter(key)
        self._update_empty()

    def _on_sort(self, key: str) -> None:
        self.state.config.set("ui.tree_sort", key)
        self.tree.set_sort(key)

    def _on_unit(self, unit: str) -> None:
        self.state.config.set("ui.size_unit", unit)
        self.tree.set_unit(unit)

    def _on_path_toggle(self, checked: bool) -> None:
        self.state.config.set("ui.tree_path", bool(checked))
        self.tree.set_path_visible(bool(checked))

    def _update_path_detail(self, *_args) -> None:
        path = self.tree.current_path()
        self.path_detail.setText(path)
        self.path_detail.setVisible(bool(path))

    def clear_filters(self) -> None:
        self.search.set_text("")
        self.filter_btn.set_current("all", emit=False)
        self.state.config.set("ui.tree_filter", "all")
        self.tree.set_query("")
        self.tree.set_filter("all")
        self._update_empty()

    def focus_search(self) -> None:
        self.search.focus()

    def _expand_bounded(self) -> None:
        truncated = self.tree.expand_all_bounded()
        if truncated:
            self.toast(
                "A expansão foi limitada para manter o app responsivo. Use a busca para chegar a itens específicos.",
                "info",
            )

    # ------------------------------------------------------------- progresso
    def _on_scan_started(self) -> None:
        self.banner.show()
        self.banner_title.setText("Analisando pastas…")
        self.banner_path.setText("Preparando varredura…")
        self.scan_bar.setRange(0, 0)
        self.cancel_btn.setEnabled(True)
        self.rescan_btn.setEnabled(False)
        self.top_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
        self.header.subtitle.setText("Analisando as pastas selecionadas…")
        self._update_empty()

    def _on_progress(self, progress: ScanProgress) -> None:
        self.banner.show()
        roots = progress.roots_total or 1
        current = min(progress.roots_done + 1, roots)
        self.banner_title.setText(
            f"Analisando {current} de {roots} pasta{'s' if roots != 1 else ''} · "
            f"{format_number(progress.files)} arquivos · {format_bytes(progress.bytes_seen)}"
        )
        path = progress.current or ""
        self.banner_path.setText(
            f"Lendo pasta: {path}" if path else "Mapeando estrutura…"
        )

    def _cancel_scan(self) -> None:
        self.cancel_btn.setEnabled(False)
        self.banner_title.setText("Cancelando…")
        self.state.cancel_scan()

    def _on_scan_finished(self, result: ScanResult) -> None:
        self.banner.hide()
        self.rescan_btn.setEnabled(True)
        self.tree.set_result(result)
        self._update_header()
        self._update_empty()
        self._update_path_detail()
        suffix = ""
        if result.errors:
            suffix = f" com {result.errors} aviso{'s' if result.errors != 1 else ''} de acesso"
        message = (
            f"Análise concluída: {format_bytes(result.total_size)} em "
            f"{result.elapsed:.1f}s{suffix}."
        )
        if result.truncated:
            self.toast(
                "Análise limitada pelo volume de itens. Os tamanhos podem estar incompletos.",
                "warn",
            )
        else:
            self.toast(message, "success" if not result.errors else "info")

    def _on_scan_cancelled(self) -> None:
        self.banner.hide()
        self.rescan_btn.setEnabled(True)
        self.toast("Análise cancelada.", "info")
        self._update_header()
        self._update_empty()

    def _on_scan_failed(self, message: str) -> None:
        self.banner.hide()
        self.rescan_btn.setEnabled(True)
        self.toast(f"Falha na análise: {message}", "danger")
        self._update_header()
        self._update_empty()

    def _on_results_cleared(self) -> None:
        self.tree.set_result(None)
        self._update_header()
        self._update_empty()
        self._update_path_detail()

    def _on_count(self, matches: int, shown: int) -> None:
        self._last_matches = matches
        if matches >= 0:
            text = f"{format_number(matches)} resultado{'s' if matches != 1 else ''}"
            if shown != matches:
                text += f" · {format_number(shown)} exibidos"
        else:
            text = f"{format_number(shown)} itens visíveis"
        self.count_label.setToolTip(text)
        self.count_label.setText(text)
        self._update_empty()

    # ----------------------------------------------------------- estado vazio
    def _show_empty(self, title: str, description: str, icon_name: str) -> None:
        self.empty.title.setText(title)
        self.empty.description.setText(description)
        self.empty.icon.set_icon_name(icon_name)
        self.empty.relayout()
        self.stack.setCurrentWidget(self.empty)

    def _update_empty(self) -> None:
        if not self.state.roots:
            self.empty_add.setVisible(True)
            self.empty_scan.setVisible(False)
            self.empty_clear.setVisible(False)
            self._show_empty(
                "Nenhuma pasta analisada",
                "Adicione uma ou mais pastas para comparar tamanhos, navegar pelos arquivos "
                "e receber sugestões de limpeza segura. Você também pode arrastar pastas para a janela.",
                "folder-search-outline",
            )
            return
        if self.state.last_result is None:
            if self.state.is_scanning:
                self.empty_add.setVisible(False)
                self.empty_scan.setVisible(False)
                self.empty_clear.setVisible(False)
                self._show_empty(
                    "Analisando pastas…",
                    "A estrutura está sendo percorrida em segundo plano. Os resultados aparecerão aqui.",
                    "radar",
                )
            else:
                self.empty_add.setVisible(True)
                self.empty_scan.setVisible(True)
                self.empty_clear.setVisible(False)
                self._show_empty(
                    "Tudo pronto para analisar",
                    f"{len(self.state.roots)} pasta{'s' if len(self.state.roots) != 1 else ''} "
                    "selecionada(s). Clique em analisar para calcular tamanhos e receber recomendações.",
                    "folder-search-outline",
                )
            return
        query_active = bool(self.search.text().strip())
        filter_active = self.filter_btn.current() != "all"
        if self._last_matches == 0 and (query_active or filter_active):
            self.empty_add.setVisible(False)
            self.empty_scan.setVisible(False)
            self.empty_clear.setVisible(True)
            self._show_empty(
                "Nenhum resultado",
                "Nenhum arquivo ou pasta corresponde à busca e aos filtros atuais. "
                "Tente outro termo ou remova os filtros.",
                "filter-off-outline",
            )
            return
        self.stack.setCurrentWidget(self.tree)
