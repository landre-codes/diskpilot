"""Histórico compacto de snapshots e comparação de ganho observado.

O histórico é intencionalmente pequeno: guarda apenas agregados e os totais
por raiz, sem listas de arquivos. A comparação mede a **redução líquida
observada** entre dois snapshots; ela não prova que os arquivos foram
excluídos, pois movimentos, permissões e mudanças de raiz também alteram os
totais.
"""

from __future__ import annotations

import time
from typing import Any

from appshell.utils import path_key

SNAPSHOT_VERSION = 1
HISTORY_LIMIT = 50


def _as_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _as_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _root_payload(root: Any) -> dict[str, Any]:
    return {
        "path": str(getattr(root, "path", "") or ""),
        "size": max(0, _as_int(getattr(root, "size", 0))),
        "files": max(0, _as_int(getattr(root, "files", 0))),
        "dirs": max(0, _as_int(getattr(root, "dirs", 0))),
    }


def _roots(entry: dict[str, Any]) -> list[dict[str, Any]]:
    raw = entry.get("roots", [])
    if not isinstance(raw, list):
        return []
    roots: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", "") or "")
        if not path:
            continue
        roots.append(
            {
                "path": path,
                "size": max(0, _as_int(item.get("size"))),
                "files": max(0, _as_int(item.get("files"))),
                "dirs": max(0, _as_int(item.get("dirs"))),
            }
        )
    return roots


def snapshot_entry(
    result: Any,
    *,
    index_entries: int = 0,
    recorded_at: float | None = None,
) -> dict[str, Any]:
    """Monta uma entrada de histórico a partir de um ``ScanResult``."""
    return {
        "version": SNAPSHOT_VERSION,
        "started_at": _as_float(getattr(result, "started_at", 0.0)),
        "recorded_at": _as_float(
            time.time() if recorded_at is None else recorded_at
        ),
        "total_size": max(0, _as_int(getattr(result, "total_size", 0))),
        "total_files": max(0, _as_int(getattr(result, "total_files", 0))),
        "total_dirs": max(0, _as_int(getattr(result, "total_dirs", 0))),
        "safe_savings": max(
            0, _as_int(getattr(result, "safe_savings", 0))
        ),
        "review_savings": max(
            0, _as_int(getattr(result, "review_savings", 0))
        ),
        "index_entries": max(0, _as_int(index_entries)),
        "truncated": bool(getattr(result, "truncated", False)),
        "roots": [
            _root_payload(root)
            for root in getattr(result, "roots", [])
        ],
    }


def sanitize_history(
    history: object, *, include_roots: bool = True
) -> list[dict[str, Any]]:
    """Normaliza o histórico persistido, descartando entradas inválidas."""
    if not isinstance(history, list):
        return []
    entries: list[dict[str, Any]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        entry: dict[str, Any] = {
            "version": _as_int(item.get("version"), SNAPSHOT_VERSION),
            "started_at": _as_float(item.get("started_at")),
            "recorded_at": _as_float(item.get("recorded_at")),
            "total_size": max(0, _as_int(item.get("total_size"))),
            "total_files": max(0, _as_int(item.get("total_files"))),
            "total_dirs": max(0, _as_int(item.get("total_dirs"))),
            "safe_savings": max(0, _as_int(item.get("safe_savings"))),
            "review_savings": max(0, _as_int(item.get("review_savings"))),
            "index_entries": max(0, _as_int(item.get("index_entries"))),
            "truncated": bool(item.get("truncated", False)),
        }
        if include_roots:
            entry["roots"] = _roots(item)
        entries.append(entry)
    return entries


def _identity(entry: dict[str, Any]) -> tuple[float, int, int, int, int]:
    return (
        round(_as_float(entry.get("started_at")), 3),
        _as_int(entry.get("index_entries")),
        _as_int(entry.get("total_size")),
        _as_int(entry.get("total_files")),
        _as_int(entry.get("total_dirs")),
    )


def merge_snapshot(
    history: object,
    result: Any,
    *,
    index_entries: int = 0,
) -> list[dict[str, Any]]:
    """Insere/replace um snapshot e mantém o histórico ordenado e limitado."""
    entries = sanitize_history(history)
    if not getattr(result, "roots", None):
        return entries[-HISTORY_LIMIT:]
    entry = snapshot_entry(result, index_entries=index_entries)
    key = _identity(entry)
    entries = [item for item in entries if _identity(item) != key]
    entries.append(entry)
    entries.sort(
        key=lambda item: (
            _as_float(item.get("started_at")),
            _as_int(item.get("index_entries")),
        )
    )
    return entries[-HISTORY_LIMIT:]


def compare_snapshots(history: object) -> dict[str, Any]:
    """Compara os dois snapshots mais recentes do histórico."""
    entries = sanitize_history(history)
    if not entries:
        return {
            "available": False,
            "comparable": False,
            "reason": "sem histórico de snapshots",
            "previous": None,
            "current": None,
            "history": [],
            "roots": [],
            "net_delta": 0,
            "reclaimed": 0,
            "increase": 0,
            "identified_safe": 0,
            "identified_review": 0,
            "identified_total": 0,
        }
    current = entries[-1]
    if len(entries) < 2:
        return {
            "available": False,
            "comparable": False,
            "reason": "histórico insuficiente para comparar",
            "previous": None,
            "current": current,
            "history": entries,
            "roots": [],
            "net_delta": 0,
            "reclaimed": 0,
            "increase": 0,
            "identified_safe": _as_int(current.get("safe_savings")),
            "identified_review": _as_int(current.get("review_savings")),
            "identified_total": _as_int(current.get("safe_savings"))
            + _as_int(current.get("review_savings")),
        }

    previous = entries[-2]
    reasons: list[str] = []
    if _as_int(previous.get("truncated")):
        reasons.append("snapshot anterior truncado")
    if _as_int(current.get("truncated")):
        reasons.append("snapshot atual truncado")
    prev_roots = {
        path_key(root["path"]): root for root in previous.get("roots", [])
    }
    cur_roots = {
        path_key(root["path"]): root for root in current.get("roots", [])
    }
    if set(prev_roots) != set(cur_roots):
        reasons.append("conjunto de raízes mudou")
    comparable = not reasons

    previous_size = _as_int(previous.get("total_size"))
    current_size = _as_int(current.get("total_size"))
    net_delta = current_size - previous_size
    reclaimed = max(0, -net_delta) if comparable else 0
    increase = max(0, net_delta) if comparable else 0

    root_rows: list[dict[str, Any]] = []
    for key in sorted(set(prev_roots) | set(cur_roots)):
        before = prev_roots.get(key)
        after = cur_roots.get(key)
        if before is not None and after is not None:
            delta = after["size"] - before["size"]
            root_rows.append(
                {
                    "path": after["path"],
                    "before_size": before["size"],
                    "after_size": after["size"],
                    "reclaimed": max(0, -delta) if comparable else 0,
                    "increase": max(0, delta) if comparable else 0,
                    "before_files": before["files"],
                    "after_files": after["files"],
                    "file_delta": after["files"] - before["files"],
                    "dir_delta": after["dirs"] - before["dirs"],
                    "status": (
                        "comparável"
                        if comparable
                        else "fora da comparação"
                    ),
                }
            )
        elif after is not None:
            root_rows.append(
                {
                    "path": after["path"],
                    "before_size": 0,
                    "after_size": after["size"],
                    "reclaimed": 0,
                    "increase": 0,
                    "before_files": 0,
                    "after_files": after["files"],
                    "file_delta": after["files"],
                    "dir_delta": after["dirs"],
                    "status": "nova raiz",
                }
            )
        else:
            root_rows.append(
                {
                    "path": before["path"],
                    "before_size": before["size"],
                    "after_size": 0,
                    "reclaimed": 0,
                    "increase": 0,
                    "before_files": before["files"],
                    "after_files": 0,
                    "file_delta": -before["files"],
                    "dir_delta": -before["dirs"],
                    "status": "raiz removida",
                }
            )

    identified_safe = _as_int(current.get("safe_savings"))
    identified_review = _as_int(current.get("review_savings"))
    return {
        "available": True,
        "comparable": comparable,
        "reason": "; ".join(reasons),
        "previous": previous,
        "current": current,
        "history": entries,
        "roots": root_rows,
        "net_delta": net_delta,
        "reclaimed": reclaimed,
        "increase": increase,
        "identified_safe": identified_safe,
        "identified_review": identified_review,
        "identified_total": identified_safe + identified_review,
    }
