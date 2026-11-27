from __future__ import annotations

import json
import os
import time
from pathlib import Path

from app.config import AppConfig
from appshell import utils
from appshell.utils import format_duration


def test_format_duration_uses_hh_mm_ss() -> None:
    assert format_duration(0) == "00:00:00"
    assert format_duration(0.1) == "< 1 s"
    assert format_duration(0.49) == "< 1 s"
    assert format_duration(0.5) == "00:00:01"
    assert format_duration(1.2) == "00:00:01"
    assert format_duration(3.4) == "00:00:03"
    assert format_duration(59.7) == "00:01:00"
    assert format_duration(65) == "00:01:05"
    assert format_duration(3600.3) == "01:00:00"
    assert format_duration(3725) == "01:02:05"
    assert format_duration(None) == "00:00:00"
    assert format_duration(float("inf")) == "00:00:00"
    assert format_duration(float("nan")) == "00:00:00"


def test_open_in_explorer_never_launches_a_file(
    tmp_path: Path, monkeypatch
) -> None:
    target = tmp_path / "arquivo.txt"
    target.write_text("conteudo", encoding="utf-8")
    folder = tmp_path / "pasta"
    folder.mkdir()

    calls: list[list[str]] = []
    started: list[str] = []
    monkeypatch.setattr(utils.sys, "platform", "win32")
    monkeypatch.setattr(
        utils.subprocess, "Popen", lambda args: calls.append(list(args))
    )
    monkeypatch.setattr(
        utils.os, "startfile", lambda path: started.append(path), raising=False
    )

    assert utils.open_in_explorer(str(target), select=False)
    assert calls == [["explorer", str(tmp_path)]]
    assert started == []

    calls.clear()
    assert utils.open_in_explorer(str(target), select=True)
    assert calls == [["explorer", "/select,", str(target)]]
    assert started == []

    calls.clear()
    assert utils.open_in_explorer(str(folder), select=True)
    assert calls == [["explorer", "/select,", str(folder)]]
    assert started == []


def test_corrupt_config_backups_are_bounded(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.json").write_text("{ invalido", encoding="utf-8")
    for number in range(8):
        backup = config_dir / (
            f"config.corrompido-2026010{number + 1}-000000.json"
        )
        backup.write_text("{}", encoding="utf-8")

    AppConfig(config_dir)

    backups = list(config_dir.glob("config.corrompido-*.json"))
    assert len(backups) == 5


def test_corrupt_config_recovers_last_good_backup(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.json").write_text("{ invalido", encoding="utf-8")
    (config_dir / "config.good.json").write_text(
        '{"theme": "light"}', encoding="utf-8"
    )

    config = AppConfig(config_dir)

    assert config.get("theme") == "light"


def test_save_keeps_last_good_config(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config = AppConfig(config_dir)
    config.set("theme", "light")

    good = config_dir / "config.good.json"
    assert good.is_file()
    assert '"theme": "dark"' in good.read_text(encoding="utf-8")


def test_good_config_drops_detailed_summary_paths(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps(
            {
                "theme": "dark",
                "scan": {
                    "summary": {
                        "started_at": 1.0,
                        "suggestions": [
                            {"key": "caches", "paths": ["C:/segredo"]}
                        ],
                        "top_dirs": [{"path": "C:/segredo"}],
                    },
                    "history": [
                        {
                            "started_at": 1.0,
                            "total_size": 10,
                            "roots": [{"path": "C:/segredo"}],
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    config = AppConfig(config_dir)
    config.set("theme", "light")

    stored = json.loads(
        (config_dir / "config.good.json").read_text(encoding="utf-8")
    )
    summary = stored["scan"]["summary"]
    assert "suggestions" not in summary
    assert "top_dirs" not in summary
    assert "roots" not in stored["scan"]["history"][0]
    assert stored["theme"] == "dark"


def test_owner_cache_is_separate_from_author(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(utils.sys, "platform", "win32")
    monkeypatch.setattr(
        utils,
        "_windows_owner",
        lambda path: calls.append(path) or r"DOMINIO\usuario",
    )
    utils.clear_file_metadata_cache()
    path = "C:/exemplo/pasta"

    assert utils.cached_file_owner(path) is None
    assert utils.file_owner(path) == r"DOMINIO\usuario"
    assert utils.cached_file_owner(path) == r"DOMINIO\usuario"
    assert utils.file_owner(path) == r"DOMINIO\usuario"
    assert calls == [path]
    assert utils.cached_file_author(path) is None

    utils.clear_file_metadata_cache()
    assert utils.cached_file_owner(path) is None


def test_owner_fast_does_not_touch_unc_cache_miss(monkeypatch) -> None:
    utils.clear_file_metadata_cache()
    monkeypatch.setattr(utils.sys, "platform", "win32")

    def fail(_path: str) -> str:
        raise AssertionError("consulta de rede não deveria ocorrer")

    monkeypatch.setattr(utils, "_windows_owner", fail)
    assert utils.file_owner_fast(r"\\servidor\pasta") == ""


def test_system_identities_are_filtered() -> None:
    hidden = [
        "SYSTEM",
        "SISTEMA",
        r"AUTORIDADE NT\SISTEMA",
        r"NT AUTHORITY\SYSTEM",
        r"BUILTIN\Administradores",
        r"BUILTIN\Administrators",
        r"BUILINT\Administradores",
        r"BUILTIN\Usuários",
        r"NT SERVICE\TrustedInstaller",
        "TrustedInstaller",
        "Todos",
        "CREATOR OWNER",
        "S-1-5-18",
        "S-1-5-32-544",
        "S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464",
    ]
    visible = [
        r"DESKTOP-49P2M7O\usuario",
        r"DOMINIO\Maria",
        "Administrator",
        "Landre Codes",
        "S-1-5-21-1-2-3-1001",
    ]
    for value in hidden:
        assert utils.is_system_identity(value), value
    for value in visible:
        assert not utils.is_system_identity(value), value


def test_file_metadata_hides_system_accounts(monkeypatch) -> None:
    monkeypatch.setattr(utils.sys, "platform", "win32")
    monkeypatch.setattr(
        utils, "_windows_owner", lambda path: r"AUTORIDADE NT\SISTEMA"
    )
    monkeypatch.setattr(utils, "_windows_author", lambda path: "SYSTEM")
    monkeypatch.setattr(utils, "_embedded_author", lambda path: "")
    utils.clear_file_metadata_cache()
    path = "C:/exemplo/sistema"

    assert utils.file_owner(path) == ""
    assert utils.file_author(path) == ""
    assert utils.cached_file_owner(path) == ""
    assert utils.cached_file_author(path) == ""


def test_cleanup_stale_temp_dirs_only_removes_old_prefixes(
    tmp_path: Path, monkeypatch
) -> None:
    old = tmp_path / "diskpilot-xlsb-antigo"
    fresh = tmp_path / "diskpilot-export-novo"
    unprotected = tmp_path / "diskpilot-xlsb-sem-dono"
    unrelated = tmp_path / "outro-app-antigo"
    for folder in (old, fresh, unprotected, unrelated):
        folder.mkdir()
        (folder / "arquivo.tmp").write_text("x", encoding="utf-8")
    for folder in (old, fresh):
        (folder / ".diskpilot-owner").write_text("123", encoding="utf-8")
    stamp = time.time() - 2 * 24 * 60 * 60
    for folder in (old, unprotected, unrelated):
        os.utime(folder, (stamp, stamp))
    monkeypatch.setattr(utils.tempfile, "gettempdir", lambda: str(tmp_path))

    removed = utils.cleanup_stale_temp_dirs(max_age_seconds=24 * 60 * 60)

    assert removed == 1
    assert not old.exists()
    assert fresh.exists()
    assert unprotected.exists()
    assert unrelated.exists()
