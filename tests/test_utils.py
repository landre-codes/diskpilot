from __future__ import annotations

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


def test_cleanup_stale_temp_dirs_only_removes_old_prefixes(
    tmp_path: Path, monkeypatch
) -> None:
    old = tmp_path / "diskpilot-xlsb-antigo"
    fresh = tmp_path / "diskpilot-export-novo"
    unrelated = tmp_path / "outro-app-antigo"
    for folder in (old, fresh, unrelated):
        folder.mkdir()
        (folder / "arquivo.tmp").write_text("x", encoding="utf-8")
    stamp = time.time() - 2 * 24 * 60 * 60
    for folder in (old, unrelated):
        os.utime(folder, (stamp, stamp))
    monkeypatch.setattr(utils.tempfile, "gettempdir", lambda: str(tmp_path))

    removed = utils.cleanup_stale_temp_dirs(max_age_seconds=24 * 60 * 60)

    assert removed == 1
    assert not old.exists()
    assert fresh.exists()
    assert unrelated.exists()
