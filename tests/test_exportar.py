from __future__ import annotations

from pathlib import Path

import exportar


def test_source_package_includes_legal_and_diagnostic_files(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "projeto"
    for folder in ("app", "appshell", "templates", "tests"):
        (root / folder).mkdir(parents=True)
        (root / folder / "marcador.txt").write_text(folder, encoding="utf-8")
    for name in (
        "main.py",
        "run.py",
        "requirements.txt",
        "requirements-dev.txt",
        "README.md",
        "LICENSE",
        "THIRD-PARTY.md",
        "diagnostico.py",
        "pyproject.toml",
        "iniciar.cmd",
        "exportar.py",
        ".gitignore",
    ):
        (root / name).write_text(name, encoding="utf-8")

    monkeypatch.setattr(exportar, "ROOT", root)
    destination = tmp_path / "saida"
    exportar.copy_source(destination)

    for name in ("LICENSE", "THIRD-PARTY.md", "diagnostico.py", "pyproject.toml"):
        assert (destination / name).is_file()
