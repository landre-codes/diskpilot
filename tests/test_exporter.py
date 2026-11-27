from __future__ import annotations

import csv
from pathlib import Path

import pytest
from openpyxl import load_workbook

from app.services.exporter import safe_spreadsheet_text, write_csv, write_xlsx
from app.services.model import Node, ScanResult, Suggestion


def _scan(tmp_path: Path) -> tuple[ScanResult, list[Node]]:
    root = Node(path=str(tmp_path), name="=raiz", is_dir=True, dirs=1)
    node = Node(
        path="=1+1",
        name="=1+1.txt",
        is_dir=False,
        size=10,
        files=1,
        error="+ERRO",
    )
    result = ScanResult(
        roots=[root],
        total_size=10,
        total_files=1,
        total_dirs=1,
        errors=1,
        suggestions=[
            Suggestion(
                key="=CHAVE",
                title="=HYPERLINK(\"http://exemplo\")",
                description="+descricao",
                savings=10,
                count=1,
                confidence="safe",
                icon="cache",
                note="@nota",
                paths=["-caminho"],
            )
        ],
    )
    return result, [node]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("=1+1", "'=1+1"),
        ("+1", "'+1"),
        ("-1", "'-1"),
        ("@x", "'@x"),
        ("  =1+1", "'  =1+1"),
        ("\t=1+1", "'\t=1+1"),
        ("\r=1+1", "'\r=1+1"),
        ("normal.txt", "normal.txt"),
        ("", ""),
        (10, 10),
        (None, None),
    ],
)
def test_safe_spreadsheet_text(value, expected) -> None:
    assert safe_spreadsheet_text(value) == expected


def test_csv_neutralizes_formula_like_fields(tmp_path: Path) -> None:
    result, files = _scan(tmp_path)
    output = tmp_path / "export.csv"
    write_csv(result, [], files, str(output))

    with output.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle, delimiter=";"))

    assert rows[1][2] == "'=1+1"
    assert rows[1][3] == "'=1+1.txt"
    assert rows[1][11] == "'+ERRO"
    assert rows[1][12] == "GB"
    assert rows[1][13] == "item"
    assert rows[-1][2] == "'-caminho"
    assert rows[-1][13] == "sugestao_path"
    assert rows[-1][16] == "safe"
    assert files[0].path == "=1+1"
    assert files[0].name == "=1+1.txt"
    assert files[0].error == "+ERRO"


def test_xlsx_keeps_formula_like_fields_as_text(tmp_path: Path) -> None:
    result, files = _scan(tmp_path)
    output = tmp_path / "export.xlsx"
    write_xlsx(result, [], files, str(output))

    workbook = load_workbook(output, data_only=False)
    top = workbook["Top 1000"]
    assert top["C2"].value == "=1+1"
    assert top["C2"].data_type == "s"
    assert top["D2"].value == "=1+1.txt"
    assert top["D2"].data_type == "s"
    assert top["F2"].value == 0.0
    assert top["F2"].number_format == "0.000"
    assert top["L2"].value == "+ERRO"
    assert top["L2"].data_type == "s"
    assert top["M2"].value == "GB"

    suggestions = workbook["Sugestões"]
    assert suggestions["B2"].value == "=HYPERLINK(\"http://exemplo\")"
    assert suggestions["B2"].data_type == "s"
    assert suggestions["C2"].value == "+descricao"
    assert suggestions["C2"].data_type == "s"
    assert suggestions["H2"].value == "@nota"
    assert suggestions["H2"].data_type == "s"
    assert suggestions["I2"].value == 1

    paths = workbook["Caminhos das sugestões"]
    assert paths["F2"].value == "-caminho"
    assert paths["F2"].data_type == "s"

    for sheet in workbook.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.startswith(
                    ("=", "+", "-", "@")
                ):
                    assert cell.data_type == "s"


def test_suggestion_paths_are_exported_one_per_row(tmp_path: Path) -> None:
    suggestion = Suggestion(
        key="caches",
        title="Caches",
        description="Pastas regeneráveis",
        savings=2 * 1024**3,
        count=2,
        confidence="safe",
        icon="delete-outline",
        paths=[r"C:\dados\cache1", r"C:\dados\cache2"],
    )
    result = ScanResult(total_size=2 * 1024**3, suggestions=[suggestion])

    output = tmp_path / "sugestoes.xlsx"
    write_xlsx(result, [], [], str(output))
    workbook = load_workbook(output, data_only=True)
    paths = workbook["Caminhos das sugestões"]
    assert paths.max_row == 3
    assert paths["F2"].value == r"C:\dados\cache1"
    assert paths["F3"].value == r"C:\dados\cache2"

    csv_path = tmp_path / "sugestoes.csv"
    write_csv(result, [], [], str(csv_path))
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle, delimiter=";"))
    suggestion_rows = [row for row in rows[1:] if row[13] == "sugestao_path"]
    assert [row[2] for row in suggestion_rows] == [
        r"C:\dados\cache1",
        r"C:\dados\cache2",
    ]


def test_xlsx_includes_verified_gain_sheet(tmp_path: Path) -> None:
    result, files = _scan(tmp_path)
    root = str(tmp_path)
    history = [
        {
            "version": 1,
            "started_at": 100.0,
            "total_size": 1000,
            "total_files": 2,
            "total_dirs": 1,
            "safe_savings": 0,
            "review_savings": 0,
            "index_entries": 3,
            "roots": [
                {
                    "path": root,
                    "size": 1000,
                    "files": 2,
                    "dirs": 1,
                }
            ],
        },
        {
            "version": 1,
            "started_at": 200.0,
            "total_size": 600,
            "total_files": 2,
            "total_dirs": 1,
            "safe_savings": 100,
            "review_savings": 50,
            "index_entries": 3,
            "roots": [
                {
                    "path": root,
                    "size": 600,
                    "files": 2,
                    "dirs": 1,
                }
            ],
        },
    ]
    output = tmp_path / "export.xlsx"

    write_xlsx(result, [], files, str(output), history=history)

    workbook = load_workbook(output, data_only=False)
    assert "Ganho verificado" in workbook.sheetnames
    values = [
        cell.value
        for row in workbook["Ganho verificado"].iter_rows()
        for cell in row
        if cell.value is not None
    ]
    assert "Redução líquida observada" in values
    assert "400 B" in values
    assert "Comparável" in values
    assert "Sim" in values
    assert "Histórico de snapshots" in values
