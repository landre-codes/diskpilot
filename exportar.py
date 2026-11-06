"""Gera pacotes de distribuição do DiskPilot para ambientes sem Git.

Uso:
    py -3.14 exportar.py

Saída em ``dist/``:
    DiskPilot-<versao>-source.zip       código-fonte limpo
    DiskPilot-<versao>-offline-win64.zip  código + wheels + instalador offline
    SHA256SUMS.txt                      conferência de integridade

O pacote offline é gerado para o Python que executa este script
(normalmente Python 3.14 no Windows x64). Para outra versão de Python,
execute este script novamente usando o interpretador de destino.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
IGNORE = shutil.ignore_patterns(
    "__pycache__",
    "*.py[cod]",
    ".venv",
    "venv",
    ".idea",
    ".pytest_cache",
    "*.egg-info",
    "dist",
    "build",
)


def version() -> str:
    text = (ROOT / "app" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)', text)
    return match.group(1) if match else "0.0.0"


def copy_source(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "app", destination / "app", ignore=IGNORE)
    for name in (
        "main.py",
        "run.py",
        "requirements.txt",
        "README.md",
        "iniciar.cmd",
        "exportar.py",
        ".gitignore",
    ):
        source = ROOT / name
        if source.exists():
            shutil.copy2(source, destination / name)


def make_zip(source_dir: Path, zip_path: Path) -> Path:
    base = zip_path.with_suffix("")
    # make_archive adiciona .zip; removemos um anterior para não aninhar.
    archive = shutil.make_archive(str(base), "zip", root_dir=source_dir)
    return Path(archive)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_offline_helpers(destination: Path) -> None:
    install = r"""@echo off
setlocal
cd /d "%~dp0"

set "PYCMD="
py -3.14 -c "import sys" >nul 2>nul
if not errorlevel 1 set "PYCMD=py -3.14"
if not defined PYCMD (
    py -3 -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYCMD=py -3"
)
if not defined PYCMD (
    python -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYCMD=python"
)
if not defined PYCMD (
    echo Python 3 nao encontrado.
    echo Instale Python 3.10 a 3.14 e execute novamente.
    pause
    exit /b 1
)

if not exist "%~dp0.venv\Scripts\python.exe" (
    echo Criando ambiente virtual local...
    %PYCMD% -m venv "%~dp0.venv"
    if errorlevel 1 (
        echo Falha ao criar o ambiente virtual.
        pause
        exit /b 1
    )
)

set "APP_PY=%~dp0.venv\Scripts\python.exe"
echo Instalando dependencias sem acessar a internet...
"%APP_PY%" -m pip install --disable-pip-version-check --no-index --find-links "%~dp0wheels" -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo.
    echo Falha na instalacao.
    echo Este pacote requer Python 3.10 a 3.14 no Windows x64.
    echo Se o ambiente usa outra versao, gere o pacote novamente nela.
    pause
    exit /b 1
)

echo Abrindo o DiskPilot...
"%APP_PY%" "%~dp0main.py"
endlocal
"""
    (destination / "instalar_offline.cmd").write_text(install, encoding="ascii", newline="\r\n")

    readme = r"""DiskPilot - pacote offline (Windows x64)

REQUISITOS
- Windows 10/11 x64
- Python 3.10 a 3.14
- Nenhuma conexao com a internet necessaria

INSTALACAO
1. Extraia todo o conteudo deste ZIP em uma pasta local.
2. Execute "instalar_offline.cmd" com duplo clique.
3. O instalador cria um ambiente virtual em .venv, instala as dependencias
   sem acessar a internet e abre o aplicativo.

Nas proximas vezes, execute "iniciar.cmd".

INSTALACAO MANUAL
    python -m venv .venv
    .venv\Scripts\python -m pip install --no-index --find-links wheels -r requirements.txt
    .venv\Scripts\python main.py

O que ha neste pacote
- Todo o codigo-fonte do DiskPilot.
- A pasta wheels/ com as dependencias para instalacao offline.
- O instalador instalar_offline.cmd.
- README.md com a documentacao completa.

OBSERVACOES
- As configuracoes de cada usuario ficam em %LOCALAPPDATA%\DiskPilot.
- O pacote nao inclui dados pessoais, senhas ou pastas analisadas.
- Para outra versao de Python ou outra plataforma, gere um novo pacote
  com "python exportar.py" no interpretador de destino.
"""
    (destination / "LEIA-ME-OFFLINE.txt").write_text(readme, encoding="utf-8")


def main() -> int:
    DIST.mkdir(parents=True, exist_ok=True)
    v = version()
    staging = Path(tempfile.mkdtemp(prefix="diskpilot-export-"))
    try:
        source_dir = staging / "source"
        copy_source(source_dir)
        source_zip = make_zip(source_dir, DIST / f"DiskPilot-{v}-source.zip")
        print(f"[ok] fonte: {source_zip}")

        offline_dir = staging / "offline"
        copy_source(offline_dir)
        wheels = offline_dir / "wheels"
        wheels.mkdir(parents=True, exist_ok=True)
        print("[..] baixando wheels para uso offline...")
        try:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "download",
                    "-r",
                    str(ROOT / "requirements.txt"),
                    "-d",
                    str(wheels),
                    "--only-binary=:all:",
                    "--disable-pip-version-check",
                ],
                check=True,
            )
            # MarkupSafe é o único pacote com extensão binária específica de
            # CPython. Incluímos as versões de 3.10 a 3.14 para que o mesmo
            # wheelhouse funcione em qualquer Python 3.10+ x64.
            for pyver, abi in (
                ("3.10", "cp310"),
                ("3.11", "cp311"),
                ("3.12", "cp312"),
                ("3.13", "cp313"),
            ):
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pip",
                        "download",
                        "markupsafe",
                        "-d",
                        str(wheels),
                        "--only-binary=:all:",
                        "--no-deps",
                        "--platform",
                        "win_amd64",
                        "--python-version",
                        pyver,
                        "--implementation",
                        "cp",
                        "--abi",
                        abi,
                        "--disable-pip-version-check",
                    ],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except subprocess.CalledProcessError as exc:
            print(f"[erro] não foi possível baixar as wheels: {exc}")
            print("       O ZIP de código-fonte foi gerado mesmo assim.")
            return 1
        write_offline_helpers(offline_dir)
        offline_zip = make_zip(
            offline_dir, DIST / f"DiskPilot-{v}-offline-win64.zip"
        )
        print(f"[ok] offline: {offline_zip}")

        lines = [f"{sha256(source_zip)}  {source_zip.name}", f"{sha256(offline_zip)}  {offline_zip.name}"]
        (DIST / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"[ok] hashes: {DIST / 'SHA256SUMS.txt'}")
        return 0
    finally:
        shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
