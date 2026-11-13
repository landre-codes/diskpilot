"""Configuração e migração dos arquivos de log do DiskPilot.

Por padrão os logs ficam em ``~/DiskPilot/logs`` (diretório do usuário),
fora da pasta de instalação. O usuário pode escolher outro diretório pela
página de Logs; a troca é aplicada em tempo de execução, sem reiniciar.
"""

from __future__ import annotations

import faulthandler
import logging
import logging.handlers
import os
import shutil
from pathlib import Path

from .config import AppConfig


LOG_FILENAME = "diskpilot.log"
CRASH_FILENAME = "diskpilot-crash.log"
DEFAULT_DIR_NAME = ("DiskPilot", "logs")
MAX_BYTES = 2_000_000
BACKUP_COUNT = 3

_CRASH_FILE = None


def default_log_dir() -> Path:
    return Path.home().joinpath(*DEFAULT_DIR_NAME)


def configured_log_dir(config: AppConfig) -> Path:
    raw = str(config.get("logging.directory", "") or "").strip()
    if not raw:
        return default_log_dir()
    try:
        expanded = os.path.expandvars(os.path.expanduser(raw))
        path = Path(expanded)
        if not path.is_absolute():
            path = Path.home() / path
        return path
    except Exception:
        return default_log_dir()


def _file_handler() -> logging.Handler | None:
    for handler in logging.getLogger().handlers:
        if getattr(handler, "_diskpilot_file", False):
            return handler
    return None


def active_log_file(config: AppConfig) -> Path:
    handler = _file_handler()
    base = getattr(handler, "baseFilename", None) if handler is not None else None
    if base:
        return Path(base)
    return configured_log_dir(config) / LOG_FILENAME


def active_log_dir(config: AppConfig) -> Path:
    return active_log_file(config).parent


def crash_file_path(config: AppConfig) -> Path:
    return active_log_dir(config) / CRASH_FILENAME


def log_tail(path: str | Path, max_lines: int = 8000) -> str:
    """Lê as últimas linhas de um log sem falhar em arquivos grandes."""
    try:
        with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()
        return "".join(lines[-max_lines:])
    except OSError:
        return ""


def configure_logging(
    config: AppConfig, stream: bool = False, strict: bool = False
) -> Path:
    """Instala o handler rotativo e o crash log; devolve a pasta ativa."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    old = _file_handler()
    if old is not None:
        root.removeHandler(old)
        try:
            old.close()
        except Exception:
            pass

    configured = configured_log_dir(config)
    candidates: list[Path] = [configured]
    if not strict:
        default = default_log_dir()
        fallback = config.path.parent
        for candidate in (default, fallback):
            if os.path.normcase(str(candidate)) not in {
                os.path.normcase(str(item)) for item in candidates
            }:
                candidates.append(candidate)

    chosen: Path | None = None
    selected_dir: Path | None = None
    for directory in candidates:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / LOG_FILENAME
            if directory == default_log_dir():
                _import_legacy_logs(config, directory)
            handler = logging.handlers.RotatingFileHandler(
                path,
                maxBytes=MAX_BYTES,
                backupCount=BACKUP_COUNT,
                encoding="utf-8",
            )
            handler._diskpilot_file = True
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s %(levelname)s %(name)s: %(message)s"
                )
            )
            root.addHandler(handler)
            chosen = path
            selected_dir = directory
            break
        except Exception:
            continue

    if chosen is None:
        if strict:
            raise OSError(f"Não foi possível gravar logs em {configured}")
        selected_dir = config.path.parent
        chosen = selected_dir / LOG_FILENAME

    if stream and not any(
        getattr(handler, "_diskpilot_stream", False) for handler in root.handlers
    ):
        stream_handler = logging.StreamHandler()
        stream_handler._diskpilot_stream = True
        stream_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        root.addHandler(stream_handler)

    _enable_crash_log(selected_dir)
    return selected_dir


def _import_legacy_logs(config: AppConfig, destination: Path) -> None:
    """Traz logs antigos da pasta de configuração para o novo padrão."""
    target = destination / LOG_FILENAME
    if target.exists() and target.stat().st_size > 0:
        return
    legacy_dir = config.path.parent
    for name in (LOG_FILENAME, CRASH_FILENAME):
        source = legacy_dir / name
        target_file = destination / name
        if not source.exists():
            continue
        try:
            if source.resolve() == target_file.resolve():
                continue
            destination.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target_file)
        except OSError:
            continue


def _enable_crash_log(directory: Path) -> Path | None:
    global _CRASH_FILE
    path = directory / CRASH_FILENAME
    try:
        directory.mkdir(parents=True, exist_ok=True)
        handle = open(path, "a", encoding="utf-8", buffering=1)
        faulthandler.enable(file=handle, all_threads=True)
    except Exception:
        return None
    previous = _CRASH_FILE
    _CRASH_FILE = handle
    if previous is not None:
        try:
            previous.close()
        except Exception:
            pass
    return path


def _flush() -> None:
    for handler in logging.getLogger().handlers:
        try:
            handler.flush()
        except Exception:
            pass
    if _CRASH_FILE is not None:
        try:
            _CRASH_FILE.flush()
        except Exception:
            pass


def _append_file(source: Path, destination: Path) -> None:
    if not source.exists() or source.resolve() == destination.resolve():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("r", encoding="utf-8", errors="replace") as src:
        with destination.open("a", encoding="utf-8") as dst:
            shutil.copyfileobj(src, dst)


def migrate_logs(config: AppConfig, destination: str, stream: bool = False) -> Path:
    """Move os logs atuais para ``destination`` e reconfigura na hora."""
    dest = Path(os.path.expandvars(os.path.expanduser(str(destination))))
    if not dest.is_absolute():
        dest = Path.cwd() / dest
    if dest.exists() and not dest.is_dir():
        raise NotADirectoryError(str(dest))
    dest.mkdir(parents=True, exist_ok=True)
    probe = dest / ".diskpilot-write-test"
    try:
        probe.write_text("ok", encoding="utf-8")
    finally:
        try:
            probe.unlink()
        except OSError:
            pass

    source_dir = active_log_dir(config)
    source_log = source_dir / LOG_FILENAME
    source_crash = source_dir / CRASH_FILENAME
    if os.path.normcase(str(source_dir)) == os.path.normcase(str(dest)):
        return source_dir

    _flush()
    dest_log = dest / LOG_FILENAME
    for suffix in (".3", ".2", ".1", ""):
        _append_file(Path(str(source_log) + suffix), dest_log)
    _append_file(source_crash, dest / CRASH_FILENAME)

    previous = str(config.get("logging.directory", "") or "")
    config.set("logging.directory", str(dest), save=False)
    try:
        configure_logging(config, stream=stream, strict=True)
    except Exception:
        config.set("logging.directory", previous, save=False)
        configure_logging(config, stream=stream)
        raise
    config.save()

    for suffix in (".1", ".2", ".3", ""):
        for name in (LOG_FILENAME, CRASH_FILENAME):
            source = Path(str(source_dir / name) + suffix)
            try:
                if source.exists() and os.path.normcase(str(source)) != os.path.normcase(
                    str(dest / name)
                ):
                    source.unlink()
            except OSError:
                continue
    return dest


def restore_default_logs(config: AppConfig, stream: bool = False) -> Path:
    return migrate_logs(config, str(default_log_dir()), stream=stream)


def current_paths(config: AppConfig) -> tuple[Path, Path]:
    return active_log_file(config), crash_file_path(config)
