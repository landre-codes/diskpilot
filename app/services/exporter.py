"""Exportação dos resultados da análise em CSV, XLSX e XLSB."""

from __future__ import annotations

import csv
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from .. import APP_NAME
from ..utils import format_bytes, format_datetime
from .model import Node, ScanResult


def default_export_path(prefix: str, extension: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    return str(Path.home() / f"DiskPilot-{prefix}-{stamp}.{extension}")


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
                    "formatado": format_bytes(node.size),
                    "percentual": round(percent, 2),
                    "arquivos": node.files,
                    "pastas": node.dirs,
                    "modificado": format_datetime(node.mtime),
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
                "tamanho",
                "percentual",
                "arquivos",
                "pastas",
                "modificado",
                "erro",
            ]
        )
        for row in item_rows(dirs, files, result.total_size):
            writer.writerow(
                [
                    row["categoria"],
                    row["ranking"],
                    row["caminho"],
                    row["nome"],
                    row["bytes"],
                    row["formatado"],
                    f"{row['percentual']:.2f}".replace(".", ","),
                    row["arquivos"],
                    row["pastas"],
                    row["modificado"],
                    row["erro"],
                ]
            )


def _style_header(ws, row: int, count: int) -> None:
    from openpyxl.styles import Alignment, Font, PatternFill

    for column in range(1, count + 1):
        cell = ws.cell(row=row, column=column)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="008E9C")
        cell.alignment = Alignment(horizontal="center", vertical="center")


def write_xlsx(
    result: ScanResult, dirs: list[Node], files: list[Node], path: str
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
        ("Avisos de acesso", payload.get("erros", 0)),
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
        ["Caminho", "Nome", "Tamanho", "Bytes", "Arquivos", "Pastas"]
    )
    _style_header(summary, roots_row + 1, 6)
    for root in payload.get("raizes", []):
        summary.append(
            [
                root["caminho"],
                root["nome"],
                root["formatado"],
                root["bytes"],
                root["arquivos"],
                root["pastas"],
            ]
        )
    for column, width in (
        ("A", 52),
        ("B", 24),
        ("C", 16),
        ("D", 16),
        ("E", 12),
        ("F", 12),
    ):
        summary.column_dimensions[column].width = width
    summary.freeze_panes = "A2"

    top = workbook.create_sheet("Top 100")
    headers = [
        "Categoria",
        "Ranking",
        "Caminho completo",
        "Nome",
        "Bytes",
        "Tamanho",
        "Percentual",
        "Arquivos",
        "Pastas",
        "Modificado",
        "Erro",
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
                row["formatado"],
                row["percentual"],
                row["arquivos"],
                row["pastas"],
                row["modificado"],
                row["erro"],
            ]
        )
    for column, width in (
        ("A", 12),
        ("B", 9),
        ("C", 70),
        ("D", 30),
        ("E", 14),
        ("F", 12),
        ("G", 11),
        ("H", 10),
        ("I", 10),
        ("J", 18),
        ("K", 30),
    ):
        top.column_dimensions[column].width = width
    for cell in top["E"][1:]:
        cell.number_format = "#,##0"
    for cell in top["G"][1:]:
        cell.number_format = '0.00"%"'
    top.freeze_panes = "A2"
    if top.max_row > 1:
        top.auto_filter.ref = f"A1:K{top.max_row}"

    suggestions = workbook.create_sheet("Sugestões")
    sug_headers = [
        "Chave",
        "Título",
        "Descrição",
        "Economia",
        "Bytes",
        "Quantidade",
        "Confiança",
        "Nota",
        "Caminhos",
    ]
    suggestions.append(sug_headers)
    _style_header(suggestions, 1, len(sug_headers))
    for suggestion in result.suggestions:
        suggestions.append(
            [
                suggestion.key,
                suggestion.title,
                suggestion.description,
                format_bytes(suggestion.savings),
                suggestion.savings,
                suggestion.count,
                suggestion.confidence,
                suggestion.note,
                "\n".join(suggestion.paths),
            ]
        )
    for column, width in (
        ("A", 20),
        ("B", 34),
        ("C", 48),
        ("D", 14),
        ("E", 14),
        ("F", 12),
        ("G", 12),
        ("H", 34),
        ("I", 60),
    ):
        suggestions.column_dimensions[column].width = width
    for row in suggestions.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    suggestions.freeze_panes = "A2"

    workbook.save(path)


def write_xlsb(
    result: ScanResult, dirs: list[Node], files: list[Node], path: str
) -> None:
    temp_dir = Path(tempfile.mkdtemp(prefix="diskpilot-xlsb-"))
    temp_xlsx = temp_dir / "export.xlsx"
    try:
        write_xlsx(result, dirs, files, str(temp_xlsx))
        import win32com.client as win32

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
        shutil.rmtree(temp_dir, ignore_errors=True)
