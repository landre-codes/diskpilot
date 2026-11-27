"""Utilidades pequenas e sem dependência de UI."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections import OrderedDict
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from PySide6.QtCore import QStorageInfo


_SIZE_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")
_DISPLAY_UNITS = {"KB": 1, "MB": 2, "GB": 3, "TB": 4}


def format_bytes(value: int | float, decimals: int = 1) -> str:
    """Formata bytes de forma compacta (1.4 GB, 820 MB...)."""
    try:
        size = float(value)
    except (TypeError, ValueError):
        return "—"
    if size < 0:
        return "—"
    unit = 0
    while size >= 1024 and unit < len(_SIZE_UNITS) - 1:
        size /= 1024.0
        unit += 1
    if unit == 0:
        return f"{int(size)} B"
    if size >= 100:
        return f"{size:.0f} {_SIZE_UNITS[unit]}"
    if size >= 10:
        return f"{size:.1f} {_SIZE_UNITS[unit]}" if decimals else f"{size:.0f} {_SIZE_UNITS[unit]}"
    return f"{size:.{decimals}f} {_SIZE_UNITS[unit]}"


def format_size(value: int | float, unit: str = "auto") -> str:
    """Formata em unidade fixa (KB/MB/GB/TB) ou automática."""
    key = str(unit).upper()
    if key == "AUTO" or key not in _DISPLAY_UNITS:
        return format_bytes(value)
    try:
        size = float(value)
    except (TypeError, ValueError):
        return "—"
    if size < 0:
        return "—"
    scaled = size / (1024 ** _DISPLAY_UNITS[key])
    if size == 0:
        return f"0 {key}"
    if scaled < 0.0001:
        return f"<0.0001 {key}"
    if scaled >= 100:
        text = f"{scaled:.0f}"
    elif scaled >= 10:
        text = f"{scaled:.1f}"
    elif scaled >= 1:
        text = f"{scaled:.2f}"
    else:
        text = f"{scaled:.4f}"
    return f"{text} {key}"


def format_number(value: int | float) -> str:
    try:
        return f"{int(value):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


def format_datetime(timestamp: float | int | None) -> str:
    if not timestamp:
        return "-"
    try:
        return datetime.fromtimestamp(float(timestamp)).strftime("%d/%m/%Y %H:%M")
    except (OSError, OverflowError, ValueError):
        return "-"


def format_duration(seconds: float | int | None) -> str:
    """Formata segundos como ``hh:mm:ss`` para exibição ao usuário.

    Durações positivas abaixo de meio segundo aparecem como ``< 1 s`` para
    não sugerir que a operação foi instantânea.
    """
    try:
        value = max(0.0, float(seconds or 0))
    except (TypeError, ValueError, OverflowError):
        return "00:00:00"
    if value <= 0:
        return "00:00:00"
    if value < 0.5:
        return "< 1 s"
    try:
        total = int(value + 0.5)
    except (OverflowError, ValueError):
        return "00:00:00"
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def plural(count: int, singular: str, plural_form: str) -> str:
    return singular if count == 1 else plural_form


def normalize_path(path: str) -> str:
    return os.path.abspath(os.path.expanduser(os.path.normpath(path)))


def resolve_network_path(path: str, verify: bool = True) -> str:
    """Converte uma unidade mapeada (W:\\...) no caminho UNC equivalente.

    ``verify=False`` evita o ``isdir`` no UNC, útil ao montar listas de
    unidades onde uma verificação de rede bloquearia a abertura do diálogo.
    """
    text = str(path)
    if len(text) < 2 or text[1] != ":":
        return text
    root = text[:3] if len(text) >= 3 and text[2] in "\\/" else text[:2] + "\\"
    try:
        device = QStorageInfo(root).device()
        if isinstance(device, bytes):
            device = device.decode("utf-8", "ignore")
        else:
            device = bytes(device).decode("utf-8", "ignore")
        device = str(device)
        if not device.startswith("\\\\") or device.startswith("\\\\?\\"):
            return text
        unc = device.rstrip("\\/")
        suffix = text[2:].lstrip("\\/")
        candidate = f"{unc}\\{suffix}" if suffix else unc
        if not verify or os.path.isdir(candidate):
            return candidate
    except Exception:
        pass
    return text


def avatar_photo(
    path: str,
    size: int,
    dpr: float = 2.0,
    focus_x: float = 0.5,
    focus_y: float = 0.5,
    zoom: float = 1.0,
):
    """Chama circular_pixmap com apenas os parâmetros suportados pela versão."""
    parameters = _circular_parameters()
    kwargs: dict[str, Any] = {}
    if "dpr" in parameters:
        kwargs["dpr"] = dpr
    if "focus_x" in parameters:
        kwargs["focus_x"] = focus_x
    if "focus_y" in parameters:
        kwargs["focus_y"] = focus_y
    if "zoom" in parameters:
        kwargs["zoom"] = zoom
    from .icons import circular_pixmap

    return circular_pixmap(path, size, **kwargs)


@lru_cache(maxsize=1)
def _circular_parameters():
    from inspect import signature

    from .icons import circular_pixmap

    return signature(circular_pixmap).parameters


def path_key(path: str) -> str:
    return os.path.normcase(normalize_path(path))


def open_in_explorer(path: str, select: bool = False) -> bool:
    """Mostra o item no Explorer, sem executar arquivos.

    ``select=True`` abre a pasta pai e seleciona o arquivo ou diretório.
    ``select=False`` abre a pasta (para um arquivo, abre a pasta pai).
    """
    target = normalize_path(path)
    is_dir = os.path.isdir(target)
    is_file = os.path.isfile(target)
    try:
        if sys.platform.startswith("win"):
            if select and (is_dir or is_file):
                subprocess.Popen(["explorer", "/select,", target])
            elif is_file:
                subprocess.Popen(
                    ["explorer", os.path.dirname(target) or target]
                )
            else:
                os.startfile(target)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            if select and (is_dir or is_file):
                subprocess.Popen(["open", "-R", target])
            elif is_file:
                subprocess.Popen(["open", os.path.dirname(target)])
            else:
                subprocess.Popen(["open", target])
        else:
            folder = target if is_dir else os.path.dirname(target)
            subprocess.Popen(["xdg-open", folder])
        return True
    except Exception:
        return False


_author_cache: OrderedDict[str, str] = OrderedDict()
_AUTHOR_CACHE_LIMIT = 4096
_OOXML_EXT = {
    ".docx",
    ".docm",
    ".dotx",
    ".xlsx",
    ".xlsm",
    ".xltx",
    ".pptx",
    ".pptm",
    ".potx",
    ".ppsx",
    ".vsdx",
}


def cached_file_author(path: str) -> str | None:
    """Autor já resolvido, ou ``None`` se ainda não foi consultado."""
    key = normalize_path(str(path))
    value = _author_cache.get(key)
    if value is not None:
        _author_cache.move_to_end(key)
    return value


def clear_author_cache() -> None:
    """Invalida metadados de autores ao trocar ou limpar a análise."""
    _author_cache.clear()


def cleanup_stale_temp_dirs(max_age_seconds: float = 24 * 60 * 60) -> int:
    """Remove staging do DiskPilot que ficou órfão após uma queda.

    Só atua em diretórios com os prefixos criados pelo próprio app, no
    diretório temporário do sistema, e apenas depois da carência.
    """
    root = Path(tempfile.gettempdir())
    now = time.time()
    removed = 0
    for prefix in ("diskpilot-xlsb-", "diskpilot-export-"):
        for candidate in root.glob(f"{prefix}*"):
            if not candidate.is_dir():
                continue
            marker = candidate / ".diskpilot-owner"
            if not marker.is_file():
                continue
            try:
                age = now - candidate.stat().st_mtime
            except OSError:
                continue
            if age < max(0.0, float(max_age_seconds)):
                continue
            try:
                shutil.rmtree(candidate)
                removed += 1
            except OSError as exc:
                logging.getLogger("appshell.utils").warning(
                    "temporário órfão não removido: %s (%s)", candidate, exc
                )
    return removed


def file_author(path: str) -> str:
    """Autor gravado nos metadados do arquivo (campo “Authors”)."""
    text = str(path)
    key = normalize_path(text)
    cached = _author_cache.get(key)
    if cached is not None:
        _author_cache.move_to_end(key)
        return cached
    author = ""
    if sys.platform.startswith("win"):
        author = _windows_author(text)
    if not author:
        author = _embedded_author(text)
    _author_cache[key] = author
    _author_cache.move_to_end(key)
    while len(_author_cache) > _AUTHOR_CACHE_LIMIT:
        _author_cache.popitem(last=False)
    return author


def _windows_author(text: str) -> str:
    """Lê ``System.Author`` pelo Property System do Windows."""
    try:
        import pythoncom
        from win32com.propsys import propsys, pscon  # noqa: F401
    except Exception:
        return ""
    try:
        pythoncom.CoInitialize()
    except Exception:
        return ""
    try:
        return _property_author(text)
    except Exception:
        return ""
    finally:
        pythoncom.CoUninitialize()


def _property_author(text: str) -> str:
    from win32com.propsys import propsys, pscon

    store = propsys.SHGetPropertyStoreFromParsingName(text)
    value = store.GetValue(pscon.PKEY_Author).GetValue()
    if isinstance(value, (list, tuple)):
        authors = [str(item).strip() for item in value if str(item).strip()]
        return "; ".join(authors)
    return str(value).strip() if value else ""


def file_author_fast(path: str) -> str:
    """Autor para exportação: cache ou metadados OOXML/PDF, sem bloquear.

    A consulta ao Property System do Windows pode carregar handlers na
    primeira chamada de uma thread; em exportações isso atrasaria a gravação.
    """
    cached = cached_file_author(path)
    if cached is not None:
        return cached
    return _embedded_author(str(path))


def _embedded_author(text: str) -> str:
    """Fallback para OOXML/PDF quando o Property System não responde."""
    suffix = Path(text).suffix.lower()
    try:
        if suffix in _OOXML_EXT:
            return _ooxml_author(text)
        if suffix == ".pdf":
            return _pdf_author(text)
    except Exception:
        pass
    return ""


def _ooxml_author(text: str) -> str:
    import zipfile
    from xml.etree import ElementTree

    with zipfile.ZipFile(text) as archive:
        data = archive.read("docProps/core.xml")
    root = ElementTree.fromstring(data)
    node = root.find("{http://purl.org/dc/elements/1.1/}creator")
    if node is not None and (node.text or "").strip():
        return (node.text or "").strip()
    node = root.find(
        "{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}creator"
    )
    return (node.text or "").strip() if node is not None else ""


def _pdf_author(text: str) -> str:
    import re

    data = Path(text).read_bytes()[:4_000_000]
    match = re.search(rb"/Author\s*\(((?:\\.|[^\\)])*)\)", data)
    if match:
        raw = match.group(1)
        raw = raw.replace(b"\\(", b"(").replace(b"\\)", b")")
        raw = raw.replace(b"\\\\", b"\\")
        return raw.decode("latin-1", "ignore").strip()
    match = re.search(rb"/Author\s*<([0-9A-Fa-f\s]+)>", data)
    if match:
        try:
            return bytes.fromhex(
                "".join(match.group(1).decode("ascii").split())
            ).decode("utf-16-be", "ignore").strip()
        except Exception:
            return ""
    return ""


def copy_to_clipboard(text: str) -> None:
    from PySide6.QtGui import QGuiApplication

    QGuiApplication.clipboard().setText(text)


def human_ext(name: str) -> str:
    suffix = Path(name).suffix.lower().lstrip(".")
    if not suffix:
        return "Arquivo"
    if len(suffix) > 7:
        return "Arquivo"
    return suffix.upper()
