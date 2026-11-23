"""Limites de análise ajustados à memória disponível.

O scanner ainda mantém a árvore em memória. Para não trocar um teto fixo por
um risco de OOM, o limite efetivo é derivado da memória física disponível e
fica entre um piso conservador e o teto duro de 5 milhões de entradas.
"""

from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes


MIN_ENTRIES = 250_000
DEFAULT_ENTRIES = 1_500_000
MAX_ENTRIES = 5_000_000
BYTES_PER_ENTRY = 700
RESERVE_BYTES = 512 * 1024 * 1024
BUDGET_FRACTION = 0.50


def available_memory_bytes() -> int | None:
    """Memória física disponível, ou ``None`` quando não for possível medir."""
    if sys.platform.startswith("win"):
        class _MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", wintypes.DWORD),
                ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = _MemoryStatusEx()
        status.dwLength = ctypes.sizeof(_MemoryStatusEx)
        try:
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(
                ctypes.byref(status)
            ):
                return int(status.ullAvailPhys)
        except Exception:
            return None
        return None
    try:
        pages = os.sysconf("SC_AVPHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return int(pages) * int(page_size)
    except (AttributeError, OSError, ValueError):
        return None


def estimate_max_entries(
    available_bytes: int | None = None,
    override: int | None = None,
) -> int:
    """Calcula o teto efetivo, sempre limitado pelo teto duro de 5 milhões.

    ``override`` pode reduzir o limite, mas nunca ultrapassar o orçamento
    estimado pela memória disponível.
    """
    if available_bytes is None:
        available_bytes = available_memory_bytes()
    if available_bytes is None:
        budget_limit = DEFAULT_ENTRIES
    else:
        usable = max(0, int(available_bytes) - RESERVE_BYTES)
        budget_limit = int(usable * BUDGET_FRACTION / BYTES_PER_ENTRY)
    requested = int(override or 0)
    if requested > 0:
        budget_limit = min(budget_limit, requested)
    return max(MIN_ENTRIES, min(MAX_ENTRIES, budget_limit))
