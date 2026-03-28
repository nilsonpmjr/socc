from __future__ import annotations

from datetime import datetime
from pathlib import Path

from soc_copilot.config import DB_PATH
from socc.utils.safety import log_redaction_enabled, redact_sensitive_text


def runtime_home() -> Path:
    return Path.home().expanduser() / ".socc"


def ensure_runtime_home() -> Path:
    path = runtime_home()
    path.mkdir(parents=True, exist_ok=True)
    return path


def runtime_subdir(name: str) -> Path:
    path = ensure_runtime_home() / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def session_db_path() -> Path:
    return DB_PATH


def write_runtime_log(message: str, filename: str | None = None) -> Path:
    logs_dir = runtime_subdir("logs")
    target = logs_dir / (filename or f"{datetime.now():%Y-%m-%d}.log")
    line = redact_sensitive_text(message) if log_redaction_enabled() else message
    with target.open("a", encoding="utf-8") as handle:
        handle.write(line.rstrip() + "\n")
    return target
