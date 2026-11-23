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
    assert files[0].path == "=1+1"
    assert files[0].name == "=1+1.txt"
    assert files[0].error == "+ERRO"


def test_xlsx_keeps_formula_like_fields_as_text(tmp_path: Path) -> None:
    result, files = _scan(tmp_path)
    output = tmp_path / "export.xlsx"
    write_xlsx(result, [], files, str(output))

    workbook = load_workbook(output, data_only=False)
    top = workbook["Top 100"]
    assert top["C2"].value == "=1+1"
    assert top["C2"].data_type == "s"
    assert top["D2"].value == "=1+1.txt"
    assert top["D2"].data_type == "s"
    assert top["L2"].value == "+ERRO"
    assert top["L2"].data_type == "s"

    suggestions = workbook["Sugestões"]
    assert suggestions["B2"].value == "=HYPERLINK(\"http://exemplo\")"
    assert suggestions["B2"].data_type == "s"
    assert suggestions["C2"].value == "+descricao"
    assert suggestions["C2"].data_type == "s"
    assert suggestions["H2"].value == "@nota"
    assert suggestions["H2"].data_type == "s"
    assert suggestions["I2"].value == "-caminho"
    assert suggestions["I2"].data_type == "s"

    for sheet in workbook.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.startswith(
                    ("=", "+", "-", "@")
                ):
                    assert cell.data_type == "s"
