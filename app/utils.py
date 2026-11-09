"""Utilidades pequenas e sem dependência de UI."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

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
        return "—"
    try:
        return datetime.fromtimestamp(float(timestamp)).strftime("%d/%m/%Y %H:%M")
    except (OSError, OverflowError, ValueError):
        return "—"


def plural(count: int, singular: str, plural_form: str) -> str:
    return singular if count == 1 else plural_form


def normalize_path(path: str) -> str:
    return os.path.abspath(os.path.expanduser(os.path.normpath(path)))


def resolve_network_path(path: str) -> str:
    """Converte uma unidade mapeada (W:\\...) no caminho UNC equivalente."""
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
        if os.path.isdir(candidate):
            return candidate
    except Exception:
        pass
    return text


def path_key(path: str) -> str:
    return os.path.normcase(normalize_path(path))


def open_in_explorer(path: str, select: bool = False) -> bool:
    """Abre o Explorer no caminho (ou seleciona o arquivo)."""
    target = normalize_path(path)
    try:
        if sys.platform.startswith("win"):
            if select and os.path.isfile(target):
                subprocess.Popen(["explorer", "/select,", target])
            else:
                os.startfile(target)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            args = ["open", "-R", target] if select else ["open", target]
            subprocess.Popen(args)
        else:
            folder = target if os.path.isdir(target) else os.path.dirname(target)
            subprocess.Popen(["xdg-open", folder])
        return True
    except Exception:
        return False


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
