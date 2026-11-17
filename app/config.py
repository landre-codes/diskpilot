"""Configuração específica do DiskPilot sobre ``appshell.config``."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from appshell.config import GENERIC_CONFIG, JsonSettings, merge_defaults


DOMAIN_DEFAULTS: dict[str, Any] = {
    "scan": {
        "roots": [],
        "last_scan": "",
        "summary": {},
    },
    "ui": {
        "tree_sort": "size_desc",
        "tree_filter": "all",
        "tree_path": False,
        "size_unit": "auto",
    },
}

DEFAULT_CONFIG = merge_defaults(GENERIC_CONFIG, DOMAIN_DEFAULTS)


class AppConfig(JsonSettings):
    """Configuração do DiskPilot: preferências genéricas + estado de disco."""

    def __init__(self, path: str | Path | None = None) -> None:
        super().__init__(path, DOMAIN_DEFAULTS, fallback_name="diskpilot")

    def _load(self) -> bool:
        loaded = super()._load()
        scan_cfg = self.data.get("scan")
        if isinstance(scan_cfg, dict):
            scan_cfg.pop("hash_duplicates", None)
        return loaded

    @property
    def roots(self) -> list[str]:
        value = self.get("scan.roots", [])
        if not isinstance(value, list):
            return []
        result: list[str] = []
        seen: set[str] = set()
        for item in value:
            try:
                path = os.path.abspath(os.path.expanduser(str(item)))
            except Exception:
                continue
            key = os.path.normcase(path)
            if key not in seen:
                seen.add(key)
                result.append(path)
        return result

    @roots.setter
    def roots(self, paths: list[str]) -> None:
        self.set("scan.roots", list(dict.fromkeys(paths)))
