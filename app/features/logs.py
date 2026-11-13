"""Página de logs e diagnóstico com terminal e migração de arquivos."""

from __future__ import annotations

import os
import platform
import re
import sys
import time
from pathlib import Path

from PySide6.QtCore import QTimer, Qt, qVersion
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QSyntaxHighlighter,
    QTextCharFormat,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
)

from .. import APP_NAME, __version__
from ..logging_setup import (
    active_log_dir,
    active_log_file,
    crash_file_path,
    default_log_dir,
    log_tail,
    migrate_logs,
    prune_logs,
)
from ..utils import copy_to_clipboard, format_bytes, format_datetime, open_in_explorer
from ..widgets.buttons import ActionButton, IconButton, SearchField, SelectButton
from ..widgets.common import IconLabel, PageHeader
from ..widgets.dialogs import FolderPickerDialog
from .base import BasePage


_RECORD_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
_LEVEL_RE = re.compile(r"\b(ERROR|CRITICAL|WARNING|WARN|INFO|DEBUG)\b")
_ISO_PREFIX_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})(?:,\d+)?\s+(.*)$"
)
_LEVEL_ICONS = {
    "INFO": "ℹ",
    "WARNING": "⚠",
    "WARN": "⚠",
    "ERROR": "✖",
    "CRITICAL": "✖",
    "DEBUG": "·",
}


def _display_line(line: str, crash: bool = False) -> str:
    """Formata a linha para o terminal sem alterar o arquivo original."""
    if crash:
        if line.startswith("Windows fatal exception"):
            return "✖ " + line
        if line.startswith("Thread 0x") or line.startswith("Current thread"):
            return "▸ " + line
        return "  " + line
    match = _ISO_PREFIX_RE.match(line)
    if not match:
        return "  " + line
    date = (
        f"{match.group(3)}/{match.group(2)}/{match.group(1)} "
        f"{match.group(4)}:{match.group(5)}:{match.group(6)}"
    )
    rest = match.group(7)
    level = rest.split(" ", 1)[0]
    icon = _LEVEL_ICONS.get(level, " ")
    return f"{icon} {date} {rest}"


def _display_text(text: str, crash: bool = False) -> str:
    return "\n".join(_display_line(line, crash) for line in text.splitlines())


class _TerminalHighlighter(QSyntaxHighlighter):
    """Colore níveis de log no estilo terminal, mantendo texto puro."""

    def __init__(self, document) -> None:
        super().__init__(document)
        self._formats: dict[str, QTextCharFormat] = {}
        for names, color in (
            (("ERROR", "CRITICAL"), "#ff7b72"),
            (("WARNING", "WARN"), "#e3b341"),
            (("INFO",), "#7ee787"),
            (("DEBUG",), "#8b949e"),
        ):
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            fmt.setFontWeight(QFont.Bold)
            for name in names:
                self._formats[name] = fmt
        self._icons = {
            "✖": self._formats["ERROR"],
            "⚠": self._formats["WARNING"],
            "ℹ": self._formats["INFO"],
            "·": self._formats["DEBUG"],
        }

    def highlightBlock(self, text: str) -> None:  # noqa: N802
        if "Windows fatal exception" in text:
            self.setFormat(0, len(text), self._formats["ERROR"])
            return
        if text:
            fmt = self._icons.get(text[0])
            if fmt is not None:
                self.setFormat(0, 1, fmt)
        for match in _LEVEL_RE.finditer(text):
            fmt = self._formats.get(match.group(1))
            if fmt is not None:
                self.setFormat(match.start(), len(match.group(1)), fmt)


class LogsPage(BasePage):
    page_id = "logs"
    page_title = "Logs e diagnóstico"
    page_subtitle = "Terminal de eventos e localização dos arquivos"
    page_icon = "console"

    def __init__(self, state, parent=None) -> None:
        super().__init__(state, parent)
        self._last_signature: tuple[str, float, int] | None = None
        self._last_prune = 0.0
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        self.header = PageHeader(
            "Logs e diagnóstico",
            "Acompanhe os eventos do aplicativo. Os arquivos ficam em uma pasta "
            "do seu usuário e podem ser movidos para outro local.",
            "Diagnóstico",
        )
        self.open_btn = ActionButton("Abrir pasta", "folder-open-outline", "ghost")
        self.open_btn.clicked.connect(self._open_folder)
        self.header.add_action(self.open_btn)
        self.diagnostic_btn = ActionButton(
            "Copiar diagnóstico", "content-copy", "soft"
        )
        self.diagnostic_btn.clicked.connect(self._copy_diagnostic)
        self.header.add_action(self.diagnostic_btn)
        root.addWidget(self.header)

        path_card = QFrame(self)
        path_card.setObjectName("Card")
        pc = QHBoxLayout(path_card)
        pc.setContentsMargins(14, 10, 14, 10)
        pc.setSpacing(10)
        pc.addWidget(IconLabel("file-document-outline", 20, "primary", path_card), 0, Qt.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        self.path_caption = QLabel("ARQUIVO DE LOG")
        self.path_caption.setObjectName("Eyebrow")
        self.path_label = QLabel("")
        self.path_label.setObjectName("PathText")
        self.path_label.setWordWrap(True)
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        texts.addWidget(self.path_caption)
        texts.addWidget(self.path_label)
        pc.addLayout(texts, 1)
        self.change_dir_btn = ActionButton(
            "Alterar pasta…", "folder-cog-outline", "soft", path_card, 16
        )
        self.change_dir_btn.clicked.connect(self._change_log_dir)
        pc.addWidget(self.change_dir_btn)
        self.default_dir_btn = ActionButton(
            "Padrão", "restore", "ghost", path_card, 16
        )
        self.default_dir_btn.clicked.connect(self._use_default_dir)
        pc.addWidget(self.default_dir_btn)
        root.addWidget(path_card)

        hint = QLabel(
            "Arquivos rotativos (2 MB × 3) com retenção de 3 dias. A troca de "
            "pasta move o log e o crash log atuais. Datas no formato dd/mm/aaaa. "
            "Os logs contêm caminhos completos: revise antes de compartilhar."
        )
        hint.setObjectName("Faint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        toolbar = QFrame(self)
        toolbar.setObjectName("Card")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(10, 8, 10, 8)
        tb.setSpacing(8)
        self.file_btn = SelectButton("file-document-outline", "Aplicativo", self)
        self.file_btn.setMinimumWidth(150)
        self.file_btn.set_options(
            [
                ("app", "Aplicativo", "file-document-outline"),
                ("crash", "Crash", "alert-octagon-outline"),
            ],
            "app",
        )
        self.file_btn.changed.connect(self._file_changed)
        tb.addWidget(self.file_btn)
        self.level_btn = SelectButton("filter-variant", "Todos", self)
        self.level_btn.setMinimumWidth(140)
        self.level_btn.set_options(
            [
                ("all", "Todos", "filter-variant"),
                ("info", "INFO", "information-outline"),
                ("warning", "WARNING", "alert-outline"),
                ("error", "ERRO", "alert-octagon-outline"),
            ],
            "all",
        )
        self.level_btn.changed.connect(self._filter_changed)
        tb.addWidget(self.level_btn)
        self.search = SearchField("Filtrar linhas do log…", 160, self)
        self.search.searchChanged.connect(self._filter_changed)
        tb.addWidget(self.search, 1)
        self.auto_refresh = QCheckBox("Tempo real")
        self.auto_refresh.setChecked(True)
        self.auto_refresh.toggled.connect(self._toggle_auto)
        tb.addWidget(self.auto_refresh)
        self.refresh_btn = IconButton("refresh", "Atualizar agora", self, 17)
        self.refresh_btn.clicked.connect(lambda: self._refresh(force=True))
        tb.addWidget(self.refresh_btn)
        root.addWidget(toolbar)

        self.terminal = QPlainTextEdit(self)
        self.terminal.setObjectName("LogTerminal")
        self.terminal.setReadOnly(True)
        self.terminal.setUndoRedoEnabled(False)
        self.terminal.setLineWrapMode(QPlainTextEdit.NoWrap)
        font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        font.setPointSize(10)
        self.terminal.setFont(font)
        self._highlighter = _TerminalHighlighter(self.terminal.document())
        root.addWidget(self.terminal, 1)

        foot = QHBoxLayout()
        foot.setSpacing(8)
        self.status = QLabel("")
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)
        foot.addWidget(self.status, 1)
        self.copy_btn = ActionButton("Copiar terminal", "content-copy", "soft", self, 16)
        self.copy_btn.clicked.connect(self._copy_terminal)
        foot.addWidget(self.copy_btn)
        root.addLayout(foot)

        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(lambda: self._refresh(force=False))
        self._refresh(force=True)

    # ------------------------------------------------------------- arquivos
    def _current_path(self) -> Path:
        if self.file_btn.current() == "crash":
            return crash_file_path(self.state.config)
        return active_log_file(self.state.config)

    def _file_changed(self, *_args) -> None:
        crash = self.file_btn.current() == "crash"
        self.level_btn.setEnabled(not crash)
        self.level_btn.setToolTip(
            "O crash log não usa níveis de log." if crash else "Filtrar por nível"
        )
        self.path_caption.setText("ARQUIVO DE CRASH" if crash else "ARQUIVO DE LOG")
        self._refresh(force=True)

    def _filter_changed(self, *_args) -> None:
        self._refresh(force=True)

    def _toggle_auto(self, checked: bool) -> None:
        if checked and self.isVisible():
            self._timer.start()
            self._refresh(force=False)
        else:
            self._timer.stop()

    def _level_matches(self, line: str, level: str) -> bool:
        if level == "info":
            return " INFO " in line
        if level == "warning":
            return " WARNING " in line or " WARN " in line
        if level == "error":
            return " ERROR " in line or " CRITICAL " in line
        return True

    def _filter_lines(self, lines: list[str], crash: bool) -> list[str]:
        query = self.search.text().strip().casefold()
        if crash:
            if not query:
                return lines
            return [
                line
                for line in lines
                if query in line.casefold()
                or query in _display_line(line, True).casefold()
            ]
        level = self.level_btn.current()
        blocks: list[list[str]] = []
        current: list[str] = []
        for line in lines:
            if _RECORD_RE.match(line):
                if current:
                    blocks.append(current)
                current = [line]
            elif current:
                current.append(line)
            else:
                blocks.append([line])
        if current:
            blocks.append(current)
        result: list[str] = []
        for block in blocks:
            if not block:
                continue
            if not self._level_matches(block[0], level):
                continue
            text = "\n".join(block)
            if query:
                displayed = "\n".join(_display_line(line) for line in block)
                if query not in text.casefold() and query not in displayed.casefold():
                    continue
            result.extend(block)
        return result

    # ------------------------------------------------------------- terminal
    def _refresh(self, force: bool = False) -> None:
        if not force and self.terminal.textCursor().hasSelection():
            return
        now = time.time()
        if now - self._last_prune > 3600:
            self._last_prune = now
            prune_logs(self.state.config)
        path = self._current_path()
        crash = self.file_btn.current() == "crash"
        try:
            stat = path.stat()
            signature = (str(path), stat.st_mtime, stat.st_size)
        except OSError:
            stat = None
            signature = (str(path), 0.0, 0)
        self.path_label.setText(str(path))
        self.path_label.setToolTip(str(path))
        if not force and signature == self._last_signature:
            return
        self._last_signature = signature

        raw = log_tail(path, 8000)
        lines = raw.splitlines()
        shown = self._filter_lines(lines, crash)
        displayed = [_display_line(line, crash) for line in shown]
        bar = self.terminal.verticalScrollBar()
        at_bottom = bar.value() >= max(0, bar.maximum() - 4)
        self.terminal.setPlainText("\n".join(displayed))
        if at_bottom or force:
            bar.setValue(bar.maximum())

        if stat is None:
            placeholder = (
                "Nenhum crash registrado."
                if crash
                else "Arquivo de log ainda não criado."
            )
            self.terminal.setPlaceholderText(placeholder)
            self.status.setText(placeholder)
            return
        if not lines:
            placeholder = (
                "Nenhum crash registrado."
                if crash
                else "Arquivo de log vazio."
            )
            self.terminal.setPlaceholderText(placeholder)
            self.status.setText(placeholder)
            return
        if not shown:
            self.terminal.setPlaceholderText(
                "Nenhuma linha corresponde aos filtros."
            )
        else:
            self.terminal.setPlaceholderText("")
        updated = format_datetime(stat.st_mtime)
        self.status.setText(
            f"{len(shown)} de {len(lines)} linhas · atualizado em {updated} · "
            f"{path.name}"
        )

    # ------------------------------------------------------------- comandos
    def _open_folder(self) -> None:
        folder = active_log_dir(self.state.config)
        if not open_in_explorer(str(folder)):
            self.toast(f"Não foi possível abrir a pasta: {folder}", "danger")

    def _copy_terminal(self) -> None:
        text = self.terminal.toPlainText()
        if not text:
            self.toast("Não há linhas para copiar.", "info")
            return
        copy_to_clipboard(text)
        self.toast("Conteúdo do terminal copiado.", "success")

    def _copy_diagnostic(self) -> None:
        config = self.state.config
        path = self._current_path()
        roots = "\n".join(f"  - {root}" for root in self.state.roots) or "  (nenhuma)"
        result = self.state.last_result
        if result is not None:
            scan = (
                f"{format_bytes(result.total_size)} · {result.total_files} arquivos · "
                f"{result.errors} avisos · {result.elapsed:.1f}s"
            )
        else:
            scan = "(nenhuma análise nesta sessão)"
        tail = _display_text(
            log_tail(path, 200), self.file_btn.current() == "crash"
        ).rstrip()
        lines = [
            f"{APP_NAME} — diagnóstico",
            f"Versão: {__version__}",
            f"SO: {platform.platform()}",
            f"Python: {sys.version.split()[0]}",
            f"Qt: {qVersion()}",
            f"Configuração: {config.path.parent}",
            f"Pasta de logs: {active_log_dir(config)}",
            f"Arquivo atual: {path}",
            "Raízes:",
            roots,
            f"Última análise: {scan}",
            "",
            f"--- últimas linhas ({path.name}) ---",
            tail,
        ]
        copy_to_clipboard("\n".join(lines))
        self.toast("Diagnóstico copiado com ambiente e últimas linhas.", "success")

    def _change_log_dir(self) -> None:
        current = active_log_dir(self.state.config)
        dialog = FolderPickerDialog(self.window(), str(current))
        try:
            if dialog.exec() == QDialog.DialogCode.Accepted:
                paths = dialog.selected_paths()
                if paths:
                    self._migrate_to(paths[0])
        finally:
            dialog.deleteLater()

    def _use_default_dir(self) -> None:
        target = default_log_dir()
        config = self.state.config
        if os.path.normcase(str(target)) == os.path.normcase(
            str(active_log_dir(config))
        ):
            if str(config.get("logging.directory", "") or ""):
                config.set("logging.directory", "")
            self.toast("Os logs já estão na pasta padrão.", "info")
            return
        self._migrate_to(str(target))

    def _migrate_to(self, destination: str) -> None:
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            target = migrate_logs(self.state.config, destination, stream=True)
        except Exception as exc:
            self.toast(f"Não foi possível migrar os logs: {exc}", "danger")
            return
        finally:
            QApplication.restoreOverrideCursor()
        self._last_signature = None
        self._refresh(force=True)
        self.toast(f"Logs migrados para: {target}", "success")

    # --------------------------------------------------------------- ciclo
    def on_show(self) -> None:
        self._refresh(force=True)
        if self.auto_refresh.isChecked():
            self._timer.start()

    def on_hide(self) -> None:
        self._timer.stop()
