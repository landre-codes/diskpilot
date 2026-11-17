"""Copia o núcleo appshell para o projeto gerado.

O template é intencionalmente autocontido: o app novo leva uma cópia do
appshell no momento da geração. Quando o núcleo evoluir, o projeto pode trocar
a cópia ou passar a depender de um pacote versionado.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

IGNORE = shutil.ignore_patterns(
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".venv",
    ".idea",
    ".pytest_cache",
)


def main() -> int:
    if len(sys.argv) != 3:
        print("uso: vendor_appshell.py <origem> <destino>")
        return 2
    source = Path(sys.argv[1]).resolve()
    destination = Path(sys.argv[2]).resolve()
    if not (source / "shell.py").is_file():
        print(f"appshell não encontrado em: {source}")
        return 1
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination, ignore=IGNORE)
    print(f"appshell copiado para {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
