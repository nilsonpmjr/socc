from __future__ import annotations

import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - ambiente mínimo sem dependências
    def load_dotenv(*_args, **_kwargs) -> bool:
        return False


def repo_env_path() -> Path:
    project_root = str(os.getenv("SOCC_PROJECT_ROOT", "")).strip()
    if project_root:
        return Path(project_root).expanduser().resolve() / ".env"
    return Path(__file__).resolve().parents[2] / ".env"


def runtime_env_path() -> Path:
    runtime_home = str(os.getenv("SOCC_HOME", "")).strip()
    if runtime_home:
        return Path(runtime_home).expanduser().resolve() / ".env"
    return Path.home().expanduser() / ".socc" / ".env"


def load_environment() -> dict[str, str]:
    runtime_env = runtime_env_path()
    repo_env = repo_env_path()

    if runtime_env.exists():
        load_dotenv(runtime_env, override=True)
    if repo_env.exists():
        load_dotenv(repo_env, override=False)

    return {
        "runtime_env": str(runtime_env),
        "repo_env": str(repo_env),
    }


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------

def _backup_env(path: Path) -> Path | None:
    """Create a timestamped backup of *path* before writing.  Returns backup path."""
    if not path.exists():
        return None
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup = path.with_suffix(f".bak.{ts}")
    shutil.copy2(path, backup)
    return backup


# ---------------------------------------------------------------------------
# Single-key write
# ---------------------------------------------------------------------------

def update_env_assignment(path: Path, key: str, value: str, *, backup: bool = True) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if backup:
        _backup_env(path)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    pattern = re.compile(rf"^(#\s*)?{re.escape(key)}=.*$", re.MULTILINE)
    line = f"{key}={value}"
    if pattern.search(existing):
        updated = pattern.sub(lambda _match: line, existing, count=1)
    else:
        updated = existing.rstrip() + ("\n" if existing.strip() else "") + line + "\n"
    path.write_text(updated, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Batch write (single backup, multiple keys)
# ---------------------------------------------------------------------------

def batch_update_env(path: Path, assignments: dict[str, str]) -> Path:
    """Write multiple key=value pairs in a single pass with one backup."""
    if not assignments:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    _backup_env(path)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    for key, value in assignments.items():
        pattern = re.compile(rf"^(#\s*)?{re.escape(key)}=.*$", re.MULTILINE)
        line = f"{key}={value}"
        if pattern.search(existing):
            existing = pattern.sub(lambda _match, replacement=line: replacement, existing, count=1)
        else:
            existing = existing.rstrip() + ("\n" if existing.strip() else "") + line + "\n"
    path.write_text(existing, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Remove key
# ---------------------------------------------------------------------------

def remove_env_assignment(path: Path, key: str) -> Path:
    """Comment out a key in the env file."""
    if not path.exists():
        return path
    _backup_env(path)
    existing = path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^{re.escape(key)}=(.*)$", re.MULTILINE)
    updated = pattern.sub(rf"# {key}=\1", existing, count=1)
    path.write_text(updated, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

def read_env_value(path: Path, key: str) -> str | None:
    """Read a single value from an env file without loading into os.environ."""
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"^{re.escape(key)}=(.*)$", text, re.MULTILINE)
    if match:
        return match.group(1).strip().strip('"').strip("'")
    return None


def read_all_env(path: Path) -> dict[str, str]:
    """Read all key=value pairs from an env file (ignoring comments)."""
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip().strip('"').strip("'")
    return result
