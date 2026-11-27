"""Configurações: tema, identidade, dados da análise e atalhos."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize, QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import APP_AUTHOR, APP_NAME, __version__
from ..services.limits import MAX_ENTRIES, MIN_ENTRIES
from appshell.icons import avatar_pixmap, icon
from appshell.theme import get_theme
from appshell.utils import (
    avatar_photo,
    format_bytes,
    format_datetime,
    format_number,
    open_in_explorer,
)
from appshell.widgets.buttons import ActionButton, SelectButton
from appshell.widgets.common import Card, ElidedLabel, IconLabel, PageHeader
from ..widgets.dialogs import ConfirmDialog, ProfileDialog
from .base import BasePage


class ThemeButton(QPushButton):
    def __init__(self, text: str, icon_name: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("ThemeOption")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self._icon_name = icon_name
        self.setIconSize(QSize(19, 19))
        self.toggled.connect(self._sync)
        get_theme().changed.connect(self._sync)
        self._sync()

    def _sync(self, *_args: Any) -> None:
        theme = get_theme()
        color = theme.color("primary" if self.isChecked() else "text")
        self.setIcon(icon(self._icon_name, color, 19))


class SettingsPage(BasePage):
    page_id = "settings"
    page_title = "Configurações"
    page_subtitle = "Aparência, identidade e dados"
    page_icon = "cog-outline"

    def __init__(self, state, parent: QWidget | None = None) -> None:
        super().__init__(state, parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)
        self.header = PageHeader(
            "Configurações",
            "Personalize a aparência, a identidade e o comportamento da análise.",
            "Preferências",
        )
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

        # Aparência -------------------------------------------------------
        theme_card = Card(
            "Aparência",
            "A paleta é aplicada em toda a interface, incluindo ícones desenhados e gráficos.",
        )
        theme_row = QHBoxLayout()
        theme_row.setSpacing(10)
        self.dark_btn = ThemeButton("  Escuro", "weather-night")
        self.light_btn = ThemeButton("  Claro", "white-balance-sunny")
        group = QButtonGroup(self)
        group.setExclusive(True)
        group.addButton(self.dark_btn)
        group.addButton(self.light_btn)
        self.dark_btn.clicked.connect(lambda: self._apply_theme("dark"))
        self.light_btn.clicked.connect(lambda: self._apply_theme("light"))
        theme_row.addWidget(self.dark_btn, 1)
        theme_row.addWidget(self.light_btn, 1)
        theme_card.body.addLayout(theme_row)
        self.theme_note = QLabel("")
        self.theme_note.setObjectName("Faint")
        theme_card.body.addWidget(self.theme_note)
        body.addWidget(theme_card)

        # Identidade ------------------------------------------------------
        identity = Card(
            "Perfil",
            "Nome e foto exibidos na barra lateral. A imagem é copiada para a pasta de configurações.",
        )
        user_box = QVBoxLayout()
        user_box.setSpacing(7)
        user_cap = QLabel("PERFIL DO USUÁRIO")
        user_cap.setObjectName("Eyebrow")
        user_box.addWidget(user_cap)
        user_row = QHBoxLayout()
        user_row.setSpacing(10)
        self.avatar_preview = QLabel()
        self.avatar_preview.setFixedSize(56, 56)
        self.avatar_preview.setAlignment(Qt.AlignCenter)
        self.avatar_preview.setScaledContents(True)
        user_row.addWidget(self.avatar_preview)
        user_text = QVBoxLayout()
        user_text.setSpacing(1)
        self.user_name = QLabel("")
        self.user_name.setObjectName("RowTitle")
        self.user_hint = QLabel("Conta local")
        self.user_hint.setObjectName("RowSub")
        user_text.addWidget(self.user_name)
        user_text.addWidget(self.user_hint)
        user_row.addLayout(user_text, 1)
        edit_profile = ActionButton("Editar perfil", "account-edit-outline", "soft", self, 16)
        edit_profile.setMaximumWidth(180)
        edit_profile.clicked.connect(self._edit_profile)
        user_row.addWidget(edit_profile, 0, Qt.AlignVCenter)
        user_box.addLayout(user_row)
        identity.body.addLayout(user_box)
        body.addWidget(identity)

        # Dados da análise ------------------------------------------------
        data_card = Card(
            "Dados da análise",
            "Controle o resumo armazenado localmente. As pastas selecionadas não são apagadas.",
        )
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(7)
        self.data_values: dict[str, QLabel] = {}
        for row, (key, label) in enumerate(
            (
                ("pastas", "Pastas selecionadas"),
                ("ultima", "Última análise"),
                ("tamanho", "Espaço analisado"),
                ("limite", "Limite de análise"),
                ("motor", "Motor de análise"),
                ("indice", "Índice de busca"),
                ("snapshots", "Snapshots do índice"),
                ("config", "Pasta de configurações"),
            )
        ):
            cap = QLabel(label)
            cap.setObjectName("InfoLabel")
            grid.addWidget(cap, row, 0, Qt.AlignTop)
            if key == "config":
                value = ElidedLabel(str(self.state.config.path.parent))
                value.setObjectName("InfoValue")
            else:
                value = QLabel("—")
                value.setObjectName("InfoValue")
                value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            grid.addWidget(value, row, 1)
            self.data_values[key] = value
        grid.setColumnStretch(1, 1)
        data_card.body.addLayout(grid)
        quota_row = QHBoxLayout()
        quota_row.setSpacing(8)
        quota_caption = QLabel("Quota do índice")
        quota_caption.setObjectName("InfoLabel")
        self.quota_btn = SelectButton("database", "24 GB", self)
        self.quota_btn.set_options(
            (
                ("4", "4 GB", "database"),
                ("8", "8 GB", "database"),
                ("16", "16 GB", "database"),
                ("24", "24 GB", "database"),
            ),
            current="24",
        )
        self.quota_btn.setToolTip(
            "Limite soft para a pasta index. O snapshot ativo nunca é "
            "removido automaticamente para caber na quota."
        )
        self.quota_btn.changed.connect(self._set_index_quota)
        quota_row.addWidget(quota_caption)
        quota_row.addStretch(1)
        quota_row.addWidget(self.quota_btn)
        data_card.body.addLayout(quota_row)
        data_actions = QHBoxLayout()
        data_actions.setSpacing(8)
        config_btn = ActionButton("Abrir configurações", "folder-open-outline", "soft", self, 16)
        config_btn.clicked.connect(
            lambda: open_in_explorer(str(self.state.config.path.parent))
        )
        data_actions.addWidget(config_btn)
        rescan = ActionButton("Reanalisar agora", "refresh", "ghost", self, 16)
        rescan.clicked.connect(self._rescan)
        data_actions.addWidget(rescan)
        self.clear_previous_btn = ActionButton(
            "Limpar índice anterior", "history", "ghost", self, 16
        )
        self.clear_previous_btn.setToolTip(
            "Remove apenas o snapshot de rollback; o índice ativo é mantido."
        )
        self.clear_previous_btn.clicked.connect(self._clear_previous_index)
        data_actions.addWidget(self.clear_previous_btn)
        data_actions.addStretch(1)
        clear = ActionButton("Limpar resultados", "delete-outline", "danger", self, 16)
        clear.clicked.connect(self._clear_results)
        data_actions.addWidget(clear)
        data_card.body.addLayout(data_actions)
        body.addWidget(data_card)

        # Segurança e responsabilidade ------------------------------------
        safety = Card(
            "Segurança e responsabilidade",
            "Leia antes de usar as recomendações em produção.",
        )
        safety_text = QLabel(
            "• O DiskPilot é somente leitura: nenhum arquivo ou pasta é apagado por ele.\n"
            "• Tamanhos são lógicos e podem diferir do espaço físico (arquivos esparsos, "
            "compactados, links e junctions).\n"
            "• A varredura pode ser limitada em volumes muito grandes; verifique o aviso de "
            "resultado parcial.\n"
            "• Duplicatas são comparadas por nome e tamanho, não por conteúdo.\n"
            "• Decisões de limpeza, exclusão e uso dos dados são de responsabilidade do "
            "usuário e da equipe.\n"
            "• Nenhum dado é enviado para a internet. Configurações e logs ficam locais e "
            "podem conter caminhos do computador."
        )
        safety_text.setObjectName("Muted")
        safety_text.setWordWrap(True)
        safety_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        safety.body.addWidget(safety_text)
        body.addWidget(safety)

        # Atalhos ---------------------------------------------------------
        shortcuts = Card("Atalhos de teclado", "Acesso rápido aos fluxos principais.")
        shortcut_grid = QGridLayout()
        shortcut_grid.setHorizontalSpacing(18)
        shortcut_grid.setVerticalSpacing(6)
        for row, (keys, desc) in enumerate(
            (
                ("Ctrl+O", "Adicionar pastas"),
                ("Ctrl+F", "Pesquisar na análise"),
                ("Ctrl+R", "Reanalisar diretórios"),
                ("Ctrl+B", "Recolher ou expandir o menu"),
                ("F11", "Alternar tela cheia"),
                ("Ctrl+1 … 4", "Ir direto para uma aba"),
            )
        ):
            k = QLabel(keys)
            k.setObjectName("BadgeInfo")
            d = QLabel(desc)
            d.setObjectName("Muted")
            shortcut_grid.addWidget(k, row, 0, Qt.AlignLeft)
            shortcut_grid.addWidget(d, row, 1)
        shortcut_grid.setColumnStretch(1, 1)
        shortcuts.body.addLayout(shortcut_grid)
        body.addWidget(shortcuts)

        # Sobre -----------------------------------------------------------
        about = Card("Sobre", "")
        about_row = QHBoxLayout()
        about_row.setSpacing(14)
        about_icon = IconLabel("harddisk", 30, "primary")
        about_row.addWidget(about_icon, 0, Qt.AlignTop)
        about_text = QVBoxLayout()
        about_text.setSpacing(3)
        title = QLabel(f"{APP_NAME} {__version__}")
        title.setObjectName("SectionTitle")
        about_text.addWidget(title)
        desc = QLabel(
            "Aplicação gerencial focada na gestão minuciosa e correta de "
            "diretórios e arquivos. "
            "Interface construída com Python, PySide6, qt-material e ícones Material Design. "
            "O tema, o perfil e o resumo da última análise são persistidos localmente."
        )
        desc.setWordWrap(True)
        desc.setObjectName("Muted")
        about_text.addWidget(desc)
        author = QLabel(f"Desenvolvido por {APP_AUTHOR}")
        author.setObjectName("Muted")
        author.setToolTip("Autor do DiskPilot")
        about_text.addWidget(author)
        stack = QLabel("PySide6 · qt-material · qtawesome (MDI) · QPainter")
        stack.setObjectName("Faint")
        about_text.addWidget(stack)
        about_row.addLayout(about_text, 1)
        about.body.addLayout(about_row)
        body.addWidget(about)
        body.addStretch(1)

        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        self.state.scanFinished.connect(self._refresh_data)
        self.state.scanStarted.connect(self._refresh_data)
        self.state.resultsCleared.connect(self._refresh_data)
        self.state.rootsChanged.connect(self._refresh_data)
        self.state.rootRemovalFinished.connect(self._refresh_data)
        self.state.indexUsageChanged.connect(self._refresh_data)
        self.state.searchIndexReady.connect(self._refresh_data)
        self.state.searchIndexCleared.connect(self._refresh_data)
        self.state.searchIndexFailed.connect(self._refresh_data)
        get_theme().changed.connect(self._on_theme_changed)
        self._refresh_identity()
        self._refresh_data()
        self._on_theme_changed(get_theme().key)

    # ------------------------------------------------------------------ tema
    def _apply_theme(self, key: str) -> None:
        if get_theme().key == key:
            return
        get_theme().apply(key)
        self.toast(
            f"Tema {'escuro' if key == 'dark' else 'claro'} aplicado e salvo.",
            "success",
        )

    def _on_theme_changed(self, key: str) -> None:
        for btn, btn_key in ((self.dark_btn, "dark"), (self.light_btn, "light")):
            blocker = QSignalBlocker(btn)
            btn.setChecked(key == btn_key)
            del blocker
            btn._sync()
        self.theme_note.setText(
            f"Tema atual: {'Escuro' if key == 'dark' else 'Claro'}."
        )

    # ------------------------------------------------------------- identidade
    def _refresh_identity(self) -> None:
        theme = get_theme()
        avatar_path = self.state.config.avatar_path
        if avatar_path:
            focus_x, focus_y, zoom = self.state.config.avatar_framing
            pm = avatar_photo(
                avatar_path, 54, 2.0, focus_x, focus_y, zoom
            )
        else:
            pm = avatar_pixmap(
                self.state.config.user_name,
                54,
                theme.color("primary"),
                theme.color("info"),
                theme.color("on_primary"),
            )
        self.avatar_preview.setPixmap(pm)
        self.user_name.setText(self.state.config.user_name)

    def _edit_profile(self) -> None:
        dialog = ProfileDialog(self.window(), self.state.config)
        result = dialog.exec()
        dialog.deleteLater()
        if result == QDialog.Accepted:
            self._refresh_identity()
            self.identityChanged.emit()
            self.toast("Perfil atualizado.", "success")

    # ------------------------------------------------------------------ dados
    def _refresh_data(self, *_args: Any) -> None:
        summary = self.state.summary
        self.data_values["pastas"].setText(str(len(self.state.roots)))
        started = summary.get("started_at", 0) if summary else 0
        self.data_values["ultima"].setText(format_datetime(started) if started else "Nenhuma")
        size = int(summary.get("total_size", 0)) if summary else 0
        self.data_values["tamanho"].setText(format_bytes(size) if summary else "—")
        limit = self.state.scan_limit
        self.data_values["limite"].setText(
            f"{format_number(limit)} entradas"
        )
        self.data_values["limite"].setToolTip(
            "Limite automático calculado pela memória RAM disponível no "
            "momento. Piso de "
            f"{format_number(MIN_ENTRIES)} e teto de "
            f"{format_number(MAX_ENTRIES)} entradas."
        )
        engine = self.state.scan_engine
        self.data_values["motor"].setText(
            "Indexado (lazy)" if engine != "memory" else "Memória"
        )
        self.data_values["motor"].setToolTip(
            "Indexado: grava no SQLite durante a varredura e carrega a árvore "
            "sob demanda. Memória: mantém a árvore completa em RAM."
        )
        usage = self.state.index_usage()
        total_bytes = int(usage["total_bytes"])
        quota_bytes = int(usage["quota_bytes"])
        self.data_values["indice"].setText(format_bytes(total_bytes))
        quota_text = f"Quota: {format_bytes(quota_bytes)}"
        self.data_values["indice"].setToolTip(
            f"{usage.get('active_path') or 'sem índice ativo'}\n{quota_text}"
        )
        snapshots = int(usage["snapshots"])
        parts = []
        if usage.get("active_exists"):
            parts.append("ativo")
        if usage.get("previous_exists"):
            parts.append("anterior")
        extras = max(0, snapshots - len(parts))
        if extras > 0:
            parts.append(f"{extras} órfão" + ("s" if extras != 1 else ""))
        self.data_values["snapshots"].setText(
            f"{snapshots} ({' + '.join(parts) if parts else 'nenhum'})"
        )
        self.data_values["snapshots"].setToolTip(
            "O snapshot ativo é mantido. O anterior serve de rollback e "
            "expira pela política de retenção/quota."
        )
        self.clear_previous_btn.setEnabled(bool(usage.get("previous_exists")))
        try:
            quota_current = str(
                int(float(self.state.config.get("scan.index_max_gb", 24) or 24))
            )
        except (TypeError, ValueError):
            quota_current = "24"
        if quota_current not in {"4", "8", "16", "24"}:
            quota_current = "24"
        self.quota_btn.set_current(quota_current, emit=False)

    def _rescan(self) -> None:
        if not self.state.roots:
            self.navigateRequested.emit("analyzer")
            return
        self.state.start_scan(force=True)
        self.toast("Reanalisando diretórios…", "info")

    def _set_index_quota(self, value: str) -> None:
        try:
            gigabytes = int(value)
        except (TypeError, ValueError):
            return
        if gigabytes <= 0:
            gigabytes = 24
        try:
            self.state.config.set("scan.index_max_gb", gigabytes, save=True)
        except Exception:
            self.toast("Não foi possível salvar a quota do índice.", "danger")
            return
        self.state._enforce_index_retention()
        self._refresh_data()
        self.toast(
            f"Quota do índice atualizada para {gigabytes} GB.",
            "info",
        )

    def _clear_previous_index(self) -> None:
        usage = self.state.index_usage()
        if not usage.get("previous_exists"):
            self.toast("Não há índice anterior para remover.", "info")
            self._refresh_data()
            return
        dialog = ConfirmDialog(
            self.window(),
            "Remover índice anterior",
            "O snapshot anterior será removido. O índice ativo e a análise "
            "atual serão mantidos; a restauração rápida continua funcionando.",
            confirm_text="Remover anterior",
        )
        if dialog.exec() != QDialog.Accepted:
            self._refresh_data()
            return
        if self.state.clear_previous_index():
            self.toast("Índice anterior removido.", "success")
        else:
            self.toast("Não foi possível remover o índice anterior.", "warn")
        self._refresh_data()

    def _clear_results(self) -> None:
        dialog = ConfirmDialog(
            self.window(),
            "Limpar resultados da análise",
            "O resumo, os tamanhos e as recomendações armazenados serão apagados. "
            "As pastas selecionadas serão mantidas e poderão ser analisadas novamente.",
            "Limpar resultados",
            danger=True,
        )
        result = dialog.exec()
        dialog.deleteLater()
        if result != QDialog.Accepted:
            return
        self.state.cancel_scan()
        if not self.state.clear_results(persist=True):
            self.toast(
                "Aguarde a remoção da pasta terminar antes de limpar.",
                "warn",
            )
            return
        self.toast("Resultados limpos. As pastas foram mantidas.", "info")

    def on_show(self) -> None:
        self._refresh_identity()
        self._refresh_data()
        self._on_theme_changed(get_theme().key)
