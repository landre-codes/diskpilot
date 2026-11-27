"""Exportação dos resultados da análise em CSV, XLSX e XLSB."""

from __future__ import annotations

import csv
import logging
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from .. import APP_NAME
from appshell.utils import file_author_fast, format_bytes, format_datetime
from .history import compare_snapshots
from .model import Node, ScanResult


logger = logging.getLogger("diskpilot.exporter")


def default_export_dir() -> str:
    home = Path.home()
    for name in ("Downloads", "Documents", "Documentos"):
        candidate = home / name
        if candidate.is_dir():
            return str(candidate)
    return str(home)


def default_export_path(prefix: str, extension: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    return str(Path(default_export_dir()) / f"DiskPilot-{prefix}-{stamp}.{extension}")


TOP_EXPORT_LIMIT = 1000
_GB = 1024 ** 3
_RISKY_PREFIXES = ("=", "+", "-", "@")


def _gb_value(size: int | float) -> float:
    return round(float(size) / _GB, 3)


def _decimal(value: float, places: int) -> str:
    """Decimal com vírgula para o CSV aberto no Excel pt-BR."""
    return f"{float(value):.{places}f}".replace(".", ",")


def safe_spreadsheet_text(value: Any) -> Any:
    """Neutraliza texto que planilhas possam interpretar como fórmula.

    Aplica-se apenas à saída; o modelo em memória mantém o nome original.
    O prefixo apostrofo é a forma documentada e testada para CSV.
    """
    if not isinstance(value, str) or not value:
        return value
    if value[0] in "\t\r\n" or value.lstrip(" \t\r\n")[:1] in _RISKY_PREFIXES:
        return "'" + value
    return value


def _force_text_cells(ws) -> None:
    """Garante que strings do XLSX sejam células de texto, não fórmulas."""
    for row in ws.iter_rows():
        for cell in row:
            if isinstance(cell.value, str):
                cell.data_type = "s"


def item_rows(
    dirs: list[Node], files: list[Node], total: int
) -> list[dict[str, Any]]:
    total = max(1, total)
    rows: list[dict[str, Any]] = []
    for category, nodes in (("Diretório", dirs), ("Arquivo", files)):
        for rank, node in enumerate(nodes, 1):
            percent = node.size / total * 100.0 if total else 0.0
            rows.append(
                {
                    "categoria": category,
                    "ranking": rank,
                    "caminho": node.path,
                    "nome": node.name,
                    "bytes": node.size,
                    "size_gb": _gb_value(node.size),
                    "unit": "GB",
                    "formatado": format_bytes(node.size),
                    "percentual": round(percent, 2),
                    "arquivos": node.files,
                    "pastas": node.dirs,
                    "modificado": format_datetime(node.mtime),
                    "autor": file_author_fast(node.path) or "—",
                    "erro": node.error,
                }
            )
    return rows


def summary_payload(result: ScanResult) -> dict[str, Any]:
    return {
        "total_bytes": result.total_size,
        "total_formatado": format_bytes(result.total_size),
        "arquivos": result.total_files,
        "pastas": result.total_dirs,
        "erros": result.errors,
        "duracao_s": round(result.elapsed, 3),
        "iniciado_em": format_datetime(result.started_at),
        "truncado": "Sim" if result.truncated else "Não",
        "raizes": [
            {
                "caminho": root.path,
                "nome": root.name,
                "bytes": root.size,
                "formatado": format_bytes(root.size),
                "arquivos": root.files,
                "pastas": root.dirs,
                "autor": file_author_fast(root.path) or "—",
            }
            for root in result.roots
        ],
    }


def write_csv(
    result: ScanResult, dirs: list[Node], files: list[Node], path: str
) -> None:
    with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(
            [
                "categoria",
                "ranking",
                "caminho",
                "nome",
                "tamanho_bytes",
                "tamanho_gb",
                "percentual",
                "arquivos",
                "pastas",
                "modificado",
                "autor",
                "erro",
                "unidade",
                "registro",
                "sugestao",
                "chave",
                "confianca",
                "economia_bytes",
                "economia_gb",
            ]
        )
        for row in item_rows(dirs, files, result.total_size):
            values = [
                row["categoria"],
                row["ranking"],
                row["caminho"],
                row["nome"],
                row["bytes"],
                _decimal(row["size_gb"], 3),
                _decimal(row["percentual"], 2),
                row["arquivos"],
                row["pastas"],
                row["modificado"],
                row["autor"],
                row["erro"],
                row["unit"],
                "item",
                "",
                "",
                "",
                "",
                "",
            ]
            writer.writerow([safe_spreadsheet_text(value) for value in values])
        for suggestion in result.suggestions:
            for path in suggestion.paths:
                values = [
                    "Sugestão",
                    "",
                    path,
                    Path(path).name,
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "GB",
                    "sugestao_path",
                    suggestion.title,
                    suggestion.key,
                    suggestion.confidence,
                    suggestion.savings,
                    _decimal(_gb_value(suggestion.savings), 3),
                ]
                writer.writerow(
                    [safe_spreadsheet_text(value) for value in values]
                )


def _style_header(ws, row: int, count: int) -> None:
    from openpyxl.styles import Alignment, Font, PatternFill

    for column in range(1, count + 1):
        cell = ws.cell(row=row, column=column)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="008E9C")
        cell.alignment = Alignment(horizontal="center", vertical="center")


def _write_gain_sheet(
    workbook, history: list[dict[str, Any]] | None
) -> None:
    """Aba de ganho observado entre os dois snapshots mais recentes."""
    from openpyxl.styles import Alignment, Font

    sheet = workbook.create_sheet("Ganho verificado", 1)
    comparison = compare_snapshots(history or [])
    current = comparison.get("current") or {}
    previous = comparison.get("previous") or {}
    available = bool(comparison.get("available"))
    comparable = bool(comparison.get("comparable"))

    sheet.append(["Ganho verificado", ""])
    sheet.merge_cells("A1:H1")
    sheet["A1"].font = Font(bold=True, size=14)
    sheet.append(
        [
            "Redução líquida observada entre os dois snapshots mais recentes; "
            "não é prova de exclusão. Movimentos, permissões e mudanças de "
            "raiz também alteram os totais."
        ]
    )
    sheet.merge_cells("A2:H2")
    sheet["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    sheet.row_dimensions[2].height = 42
    sheet.append([])
    sheet.append(["Comparação", ""])
    _style_header(sheet, 4, 2)

    reason = str(comparison.get("reason", "") or "")
    if not available:
        reason = reason or "histórico insuficiente"
    summary_rows = [
        (
            "Snapshot anterior",
            format_datetime(previous.get("started_at")) if previous else "-",
        ),
        (
            "Snapshot atual",
            format_datetime(current.get("started_at")) if current else "-",
        ),
        ("Comparável", "Sim" if comparable else "Não"),
        (
            "Observação",
            reason
            or "mesmas raízes e snapshots completos",
        ),
        ("Total antes", format_bytes(previous.get("total_size", 0))),
        ("Total depois", format_bytes(current.get("total_size", 0))),
        (
            "Redução líquida observada",
            format_bytes(comparison.get("reclaimed", 0)),
        ),
        (
            "Aumento líquido observado",
            format_bytes(comparison.get("increase", 0)),
        ),
        (
            "Variação líquida",
            format_bytes(abs(int(comparison.get("net_delta", 0) or 0))),
        ),
        (
            "Economia identificada (segura)",
            format_bytes(comparison.get("identified_safe", 0)),
        ),
        (
            "Economia identificada (revisão)",
            format_bytes(comparison.get("identified_review", 0)),
        ),
        (
            "Economia identificada (total)",
            format_bytes(comparison.get("identified_total", 0)),
        ),
        ("Snapshots no histórico", len(comparison.get("history", []))),
    ]
    for label, value in summary_rows:
        sheet.append([label, value])

    root_rows = comparison.get("roots", [])
    if root_rows:
        sheet.append([])
        roots_title = sheet.max_row + 1
        sheet.append(["Por raiz", ""])
        sheet.cell(row=roots_title, column=1).font = Font(bold=True)
        headers = [
            "Caminho",
            "Antes",
            "Depois",
            "Redução observada",
            "Aumento observado",
            "Δ arquivos",
            "Δ pastas",
            "Situação",
        ]
        sheet.append(headers)
        _style_header(sheet, sheet.max_row, len(headers))
        for row in root_rows:
            sheet.append(
                [
                    row.get("path", ""),
                    format_bytes(row.get("before_size", 0)),
                    format_bytes(row.get("after_size", 0)),
                    format_bytes(row.get("reclaimed", 0)),
                    format_bytes(row.get("increase", 0)),
                    int(row.get("file_delta", 0)),
                    int(row.get("dir_delta", 0)),
                    row.get("status", ""),
                ]
            )

    history_rows = comparison.get("history", [])
    if history_rows:
        sheet.append([])
        history_title = sheet.max_row + 1
        sheet.append(["Histórico de snapshots", ""])
        sheet.cell(row=history_title, column=1).font = Font(bold=True)
        history_headers = [
            "Data",
            "Total",
            "Arquivos",
            "Pastas",
            "Economia segura",
            "Economia em revisão",
            "Entradas do índice",
            "Truncado",
        ]
        sheet.append(history_headers)
        _style_header(sheet, sheet.max_row, len(history_headers))
        for entry in history_rows:
            sheet.append(
                [
                    format_datetime(entry.get("started_at")),
                    format_bytes(entry.get("total_size", 0)),
                    int(entry.get("total_files", 0)),
                    int(entry.get("total_dirs", 0)),
                    format_bytes(entry.get("safe_savings", 0)),
                    format_bytes(entry.get("review_savings", 0)),
                    int(entry.get("index_entries", 0)),
                    "Sim" if entry.get("truncated") else "Não",
                ]
            )
    else:
        sheet.append([])
        sheet.append(
            [
                "Ainda não há snapshots publicados. O histórico começa após "
                "a primeira análise concluída."
            ]
        )

    for column, width in (
        ("A", 44),
        ("B", 22),
        ("C", 18),
        ("D", 18),
        ("E", 18),
        ("F", 14),
        ("G", 14),
        ("H", 22),
    ):
        sheet.column_dimensions[column].width = width
    sheet.freeze_panes = "A2"
    _force_text_cells(sheet)


def write_xlsx(
    result: ScanResult,
    dirs: list[Node],
    files: list[Node],
    path: str,
    history: list[dict[str, Any]] | None = None,
) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font

    workbook = Workbook()

    summary = workbook.active
    summary.title = "Resumo"
    payload = summary_payload(result)
    summary.append([APP_NAME, ""])
    summary.merge_cells("A1:B1")
    summary["A1"].font = Font(bold=True, size=14)
    summary.append(
        ["Exportado em", datetime.now().strftime("%d/%m/%Y %H:%M")]
    )
    summary.append([])
    summary.append(["Métrica", "Valor"])
    _style_header(summary, 4, 2)
    for label, value in (
        ("Espaço analisado", payload.get("total_formatado", "")),
        ("Total em bytes", payload.get("total_bytes", 0)),
        ("Arquivos", payload.get("arquivos", 0)),
        ("Pastas", payload.get("pastas", 0)),
        ("Avisos", payload.get("erros", 0)),
        ("Duração (s)", payload.get("duracao_s", 0)),
        ("Início", payload.get("iniciado_em", "")),
        ("Varredura limitada", payload.get("truncado", "Não")),
    ):
        summary.append([label, value])
    summary.append([])
    roots_row = summary.max_row + 1
    summary.append(["Raízes", ""])
    summary.cell(row=roots_row, column=1).font = Font(bold=True)
    summary.append(
        [
            "Caminho",
            "Nome",
            "Tamanho",
            "Bytes",
            "Arquivos",
            "Pastas",
            "Autor",
        ]
    )
    _style_header(summary, roots_row + 1, 7)
    for root in payload.get("raizes", []):
        summary.append(
            [
                root["caminho"],
                root["nome"],
                root["formatado"],
                root["bytes"],
                root["arquivos"],
                root["pastas"],
                root["autor"],
            ]
        )
    _force_text_cells(summary)
    for column, width in (
        ("A", 52),
        ("B", 24),
        ("C", 16),
        ("D", 16),
        ("E", 12),
        ("F", 12),
        ("G", 26),
    ):
        summary.column_dimensions[column].width = width
    summary.freeze_panes = "A2"

    _write_gain_sheet(workbook, history)

    top = workbook.create_sheet("Top 1000")
    headers = [
        "Categoria",
        "Ranking",
        "Caminho completo",
        "Nome",
        "Bytes",
        "Tamanho (GB)",
        "Percentual",
        "Arquivos",
        "Pastas",
        "Modificado",
        "Autor",
        "Erro",
        "Unidade",
    ]
    top.append(headers)
    _style_header(top, 1, len(headers))
    for row in item_rows(dirs, files, result.total_size):
        top.append(
            [
                row["categoria"],
                row["ranking"],
                row["caminho"],
                row["nome"],
                row["bytes"],
                row["size_gb"],
                row["percentual"],
                row["arquivos"],
                row["pastas"],
                row["modificado"],
                row["autor"],
                row["erro"],
                row["unit"],
            ]
        )
    _force_text_cells(top)
    for column, width in (
        ("A", 12),
        ("B", 9),
        ("C", 70),
        ("D", 30),
        ("E", 14),
        ("F", 14),
        ("G", 11),
        ("H", 10),
        ("I", 10),
        ("J", 18),
        ("K", 26),
        ("L", 30),
        ("M", 9),
    ):
        top.column_dimensions[column].width = width
    for cell in top["E"][1:]:
        cell.number_format = "#,##0"
    for cell in top["F"][1:]:
        cell.number_format = "0.000"
    for cell in top["G"][1:]:
        cell.number_format = '0.00"%"'
    top.freeze_panes = "A2"
    if top.max_row > 1:
        top.auto_filter.ref = f"A1:M{top.max_row}"

    suggestions = workbook.create_sheet("Sugestões")
    sug_headers = [
        "Chave",
        "Título",
        "Descrição",
        "Economia (GB)",
        "Economia (bytes)",
        "Quantidade",
        "Confiança",
        "Nota",
        "Qtde. de caminhos",
    ]
    suggestions.append(sug_headers)
    _style_header(suggestions, 1, len(sug_headers))
    for suggestion in result.suggestions:
        suggestions.append(
            [
                suggestion.key,
                suggestion.title,
                suggestion.description,
                _gb_value(suggestion.savings),
                suggestion.savings,
                suggestion.count,
                suggestion.confidence,
                suggestion.note,
                len(suggestion.paths),
            ]
        )
    _force_text_cells(suggestions)
    for column, width in (
        ("A", 20),
        ("B", 34),
        ("C", 48),
        ("D", 15),
        ("E", 18),
        ("F", 12),
        ("G", 12),
        ("H", 34),
        ("I", 18),
    ):
        suggestions.column_dimensions[column].width = width
    for cell in suggestions["D"][1:]:
        cell.number_format = "0.000"
    for cell in suggestions["E"][1:]:
        cell.number_format = "#,##0"
    for row in suggestions.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    suggestions.freeze_panes = "A2"

    paths = workbook.create_sheet("Caminhos das sugestões")
    path_headers = [
        "Chave",
        "Título",
        "Confiança",
        "Economia (bytes)",
        "Economia (GB)",
        "Caminho",
    ]
    paths.append(path_headers)
    _style_header(paths, 1, len(path_headers))
    for suggestion in result.suggestions:
        for path_value in suggestion.paths:
            paths.append(
                [
                    suggestion.key,
                    suggestion.title,
                    suggestion.confidence,
                    suggestion.savings,
                    _gb_value(suggestion.savings),
                    path_value,
                ]
            )
    _force_text_cells(paths)
    for column, width in (
        ("A", 20),
        ("B", 34),
        ("C", 12),
        ("D", 18),
        ("E", 15),
        ("F", 80),
    ):
        paths.column_dimensions[column].width = width
    for cell in paths["D"][1:]:
        cell.number_format = "#,##0"
    for cell in paths["E"][1:]:
        cell.number_format = "0.000"
    for row in paths.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=False)
    paths.freeze_panes = "A2"

    workbook.save(path)


def write_xlsb(
    result: ScanResult,
    dirs: list[Node],
    files: list[Node],
    path: str,
    history: list[dict[str, Any]] | None = None,
) -> None:
    temp_dir = Path(tempfile.mkdtemp(prefix="diskpilot-xlsb-"))
    (temp_dir / ".diskpilot-owner").write_text(
        str(os.getpid()), encoding="utf-8"
    )
    temp_xlsx = temp_dir / "export.xlsx"
    try:
        write_xlsx(result, dirs, files, str(temp_xlsx), history)
        import pythoncom
        import win32com.client as win32

        # O Excel é automação COM: inicializar e finalizar na mesma thread
        # evita RPC_E_WRONG_THREAD em diálogos/exportações seguintes.
        pythoncom.CoInitialize()
        try:
            excel = win32.DispatchEx("Excel.Application")
            try:
                excel.Visible = False
                excel.DisplayAlerts = False
                book = excel.Workbooks.Open(str(temp_xlsx))
                try:
                    book.SaveAs(str(Path(path).resolve()), FileFormat=50)
                finally:
                    book.Close(False)
            finally:
                excel.Quit()
        finally:
            pythoncom.CoUninitialize()
    finally:
        try:
            shutil.rmtree(temp_dir)
        except OSError as exc:
            logger.warning(
                "temporário da exportação não removido: %s (%s)",
                temp_dir,
                exc,
            )
