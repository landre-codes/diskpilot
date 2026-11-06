"""Persistência de configurações e ativos do aplicativo.

Tudo fica em um único JSON no diretório de configuração do usuário. Ativos
importados (logo, avatar) são copiados para ``assets/`` ao lado do arquivo,
evitando que o app quebre quando o arquivo original for movido.
"""

from __future__ import annotations

import copy
import getpass
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QStandardPaths


DEFAULT_CONFIG: dict[str, Any] = {
    "theme": "dark",
    "sidebar_collapsed": False,
    "geometry": "",
    "window_state": "normal",
    "logo": "",
    "user": {
        "name": "",
        "avatar": "",
    },
    "scan": {
        "roots": [],
        "last_scan": "",
        "summary": {},
    },
    "ui": {
        "tree_sort": "size_desc",
        "tree_filter": "all",
        "size_unit": "auto",
    },
}


def _default_config_dir() -> Path:
    location = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
    if not location:
        location = str(Path.home() / ".diskpilot")
    return Path(location)


def _merge(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Recursive merge that keeps unknown/default keys alive."""
    result = copy.deepcopy(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def _normalize_asset_ext(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".svg", ".ico"}:
        return ext
    return ".png"


def _logical_user() -> str:
    try:
        name = getpass.getuser().strip()
    except Exception:
        name = ""
    if not name:
        name = os.environ.get("USERNAME") or "Usuário"
    return name[:1].upper() + name[1:]


class AppConfig:
    """Configuração global, com leitura tolerante a arquivos corrompidos."""

    def __init__(self, path: str | Path | None = None) -> None:
        base = Path(path) if path else _default_config_dir()
        self.path = base / "config.json"
        self.assets_dir = base / "assets"
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.data: dict[str, Any] = copy.deepcopy(DEFAULT_CONFIG)
        self.data["user"]["name"] = _logical_user()
        self._loaded_ok = self._load()

    # ------------------------------------------------------------------ I/O
    def _load(self) -> bool:
        if not self.path.exists():
            self.save()
            return False
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("config raiz não é um objeto")
            self.data = _merge(DEFAULT_CONFIG, raw)
            # O cargo foi removido do produto; descartamos resíduos de
            # configurações antigas para manter o perfil enxuto.
            if isinstance(self.data.get("user"), dict):
                self.data["user"].pop("role", None)
            if not str(self.data.get("user", {}).get("name", "")).strip():
                self.data["user"]["name"] = _logical_user()
            # Remove raízes que não existem mais? Não: unidades de rede podem
            # estar temporariamente indisponíveis. A UI lida com isso.
            return True
        except Exception:
            backup = self.path.with_suffix(
                f".corrompido-{time.strftime('%Y%m%d-%H%M%S')}.json"
            )
            try:
                shutil.copy2(self.path, backup)
            except Exception:
                pass
            self.data = copy.deepcopy(DEFAULT_CONFIG)
            self.data["user"]["name"] = _logical_user()
            return False

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        payload = json.dumps(self.data, ensure_ascii=False, indent=2)
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, self.path)

    # ------------------------------------------------------------- helpers
    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted: str, value: Any, save: bool = True) -> None:
        parts = dotted.split(".")
        node = self.data
        for part in parts[:-1]:
            nxt = node.get(part)
            if not isinstance(nxt, dict):
                nxt = {}
                node[part] = nxt
            node = nxt
        node[parts[-1]] = value
        if save:
            self.save()

    def import_asset(self, source: str, prefix: str) -> str:
        """Copia um arquivo para o diretório de ativos e devolve o novo path."""
        src = Path(source)
        if not src.exists():
            raise FileNotFoundError(source)
        ext = _normalize_asset_ext(source)
        stamp = int(time.time() * 1000)
        dest = self.assets_dir / f"{prefix}_{stamp}{ext}"
        shutil.copy2(src, dest)
        # Remove versões antigas do mesmo tipo, mantendo o diretório enxuto.
        for old in self.assets_dir.glob(f"{prefix}_*"):
            if old != dest:
                try:
                    old.unlink()
                except OSError:
                    pass
        return str(dest)

    # --------------------------------------------------- domínio específico
    @property
    def theme(self) -> str:
        value = str(self.get("theme", "dark")).lower()
        return value if value in {"dark", "light"} else "dark"

    @theme.setter
    def theme(self, value: str) -> None:
        self.set("theme", value if value in {"dark", "light"} else "dark")

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

    @property
    def user_name(self) -> str:
        return str(self.get("user.name", "") or _logical_user())

    @property
    def avatar_path(self) -> str:
        path = str(self.get("user.avatar", "") or "")
        return path if path and Path(path).exists() else ""

    @property
    def logo_path(self) -> str:
        path = str(self.get("logo", "") or "")
        return path if path and Path(path).exists() else ""
