"""Configuração JSON genérica do shell.

O domínio pode herdar de :class:`JsonSettings` e acrescentar seus próprios
defaults e propriedades tipadas.
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


GENERIC_CONFIG: dict[str, Any] = {
    "theme": "dark",
    "sidebar_collapsed": False,
    "geometry": "",
    "window_state": "normal",
    "user": {
        "name": "",
        "avatar": "",
        "avatar_focus_x": 0.5,
        "avatar_focus_y": 0.3,
        "avatar_zoom": 1.0,
    },
    "logging": {
        "directory": "",
    },
}


def default_config_dir(fallback_name: str = "appshell") -> Path:
    location = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
    if not location:
        location = str(Path.home() / f".{fallback_name}")
    return Path(location)


def merge_defaults(
    base: dict[str, Any], incoming: dict[str, Any]
) -> dict[str, Any]:
    """Merge recursivo que preserva chaves desconhecidas."""
    result = copy.deepcopy(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_defaults(result[key], value)
        else:
            result[key] = value
    return result


def _normalize_asset_ext(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".svg", ".ico"}:
        return ext
    return ".png"


def logical_user() -> str:
    try:
        name = getpass.getuser().strip()
    except Exception:
        name = ""
    if not name:
        name = os.environ.get("USERNAME") or "Usuário"
    return name[:1].upper() + name[1:]


class JsonSettings:
    """Configuração global, com leitura tolerante a arquivos corrompidos."""

    def __init__(
        self,
        path: str | Path | None = None,
        defaults: dict[str, Any] | None = None,
        *,
        fallback_name: str = "appshell",
    ) -> None:
        base = Path(path) if path else default_config_dir(fallback_name)
        self.path = base / "config.json"
        self.assets_dir = base / "assets"
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.defaults = merge_defaults(GENERIC_CONFIG, defaults or {})
        self.data: dict[str, Any] = copy.deepcopy(self.defaults)
        self.data["user"]["name"] = logical_user()
        self._prune_corrupt_backups()
        self._loaded_ok = self._load()

    def _prune_corrupt_backups(self, keep: int = 5) -> None:
        """Mantém apenas os backups de configuração corrompida mais recentes."""
        try:
            backups = sorted(
                self.path.parent.glob(f"{self.path.stem}.corrompido-*.json"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return
        for old in backups[max(1, keep) :]:
            try:
                old.unlink()
            except OSError:
                continue

    # ------------------------------------------------------------------ I/O
    def _load(self) -> bool:
        if not self.path.exists():
            self.save()
            return False
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("config raiz não é um objeto")
            self.data = merge_defaults(self.defaults, raw)
            self.data.pop("native_frame", None)
            self.data.pop("logo", None)
            if isinstance(self.data.get("user"), dict):
                self.data["user"].pop("role", None)
            if not str(self.data.get("user", {}).get("name", "")).strip():
                self.data["user"]["name"] = logical_user()
            return True
        except Exception:
            backup = self.path.with_suffix(
                f".corrompido-{time.strftime('%Y%m%d-%H%M%S')}.json"
            )
            try:
                shutil.copy2(self.path, backup)
                self._prune_corrupt_backups()
            except Exception:
                pass
            good = self.path.with_name(f"{self.path.stem}.good.json")
            if good.exists():
                try:
                    raw = json.loads(good.read_text(encoding="utf-8"))
                    if not isinstance(raw, dict):
                        raise ValueError("backup raiz não é um objeto")
                    self.data = merge_defaults(self.defaults, raw)
                    self.data.pop("native_frame", None)
                    self.data.pop("logo", None)
                    if isinstance(self.data.get("user"), dict):
                        self.data["user"].pop("role", None)
                    if not str(
                        self.data.get("user", {}).get("name", "")
                    ).strip():
                        self.data["user"]["name"] = logical_user()
                    return True
                except Exception:
                    pass
            self.data = copy.deepcopy(self.defaults)
            self.data["user"]["name"] = logical_user()
            return False

    def _sanitize_backup(self, data: dict[str, Any]) -> dict[str, Any]:
        """Permite à aplicação remover dados sensíveis da cópia de segurança."""
        return data

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        good = self.path.with_name(f"{self.path.stem}.good.json")
        payload = json.dumps(self.data, ensure_ascii=False, indent=2)
        try:
            if self.path.exists():
                try:
                    current = json.loads(self.path.read_text(encoding="utf-8"))
                    if isinstance(current, dict):
                        backup = self._sanitize_backup(
                            copy.deepcopy(current)
                        )
                        good.write_text(
                            json.dumps(backup, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                except Exception:
                    pass
            tmp.write_text(payload, encoding="utf-8")
            os.replace(tmp, self.path)
        except Exception:
            try:
                tmp.unlink()
            except OSError:
                pass
            raise

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
        for old in self.assets_dir.glob(f"{prefix}_*"):
            if old != dest:
                try:
                    old.unlink()
                except OSError:
                    pass
        return str(dest)

    # ---------------------------------------------------------- preferências
    @property
    def theme(self) -> str:
        value = str(self.get("theme", "dark")).lower()
        return value if value in {"dark", "light"} else "dark"

    @theme.setter
    def theme(self, value: str) -> None:
        self.set("theme", value if value in {"dark", "light"} else "dark")

    @property
    def user_name(self) -> str:
        return str(self.get("user.name", "") or logical_user())

    @property
    def avatar_path(self) -> str:
        path = str(self.get("user.avatar", "") or "")
        return path if path and Path(path).exists() else ""

    @property
    def avatar_framing(self) -> tuple[float, float, float]:
        """Ponto focal (x, y) e zoom do avatar, com valores seguros."""
        try:
            focus_x = float(self.get("user.avatar_focus_x", 0.5))
        except (TypeError, ValueError):
            focus_x = 0.5
        try:
            focus_y = float(self.get("user.avatar_focus_y", 0.3))
        except (TypeError, ValueError):
            focus_y = 0.3
        try:
            zoom = float(self.get("user.avatar_zoom", 1.0))
        except (TypeError, ValueError):
            zoom = 1.0
        return (
            max(0.0, min(1.0, focus_x)),
            max(0.0, min(1.0, focus_y)),
            max(1.0, min(4.0, zoom)),
        )
