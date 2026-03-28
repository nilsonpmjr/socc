from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from socc.cli.installer import (
    runtime_home,
    runtime_service_meta_path,
    runtime_service_pid_path,
    runtime_service_stderr_path,
    runtime_service_stdout_path,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _load_service_meta(home: Path | None = None) -> dict[str, Any]:
    meta_path = runtime_service_meta_path(home)
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_service_meta(payload: dict[str, Any], home: Path | None = None) -> Path:
    meta_path = runtime_service_meta_path(home)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return meta_path


def service_status(home: Path | None = None) -> dict[str, Any]:
    pid_path = runtime_service_pid_path(home)
    meta = _load_service_meta(home)
    pid = 0
    if pid_path.exists():
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
        except ValueError:
            pid = 0
    running = _pid_running(pid)
    return {
        "running": running,
        "pid": pid if running else 0,
        "pid_file": str(pid_path),
        "meta_file": str(runtime_service_meta_path(home)),
        "stdout_log": str(runtime_service_stdout_path(home)),
        "stderr_log": str(runtime_service_stderr_path(home)),
        "meta": meta,
    }


def start_service(
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    log_level: str = "info",
    home: Path | None = None,
    python_executable: str | None = None,
) -> dict[str, Any]:
    base_dir = runtime_home(home)
    base_dir.mkdir(parents=True, exist_ok=True)

    current = service_status(home)
    if current.get("running"):
        return {
            "started": False,
            "already_running": True,
            **current,
        }

    stdout_path = runtime_service_stdout_path(home)
    stderr_path = runtime_service_stderr_path(home)
    stdout_path.parent.mkdir(parents=True, exist_ok=True)

    python_bin = python_executable or sys.executable
    command = [
        python_bin,
        "-m",
        "socc.cli.main",
        "serve",
        "--host",
        str(host),
        "--port",
        str(port),
        "--log-level",
        str(log_level),
    ]

    with stdout_path.open("ab") as stdout_handle, stderr_path.open("ab") as stderr_handle:
        process = subprocess.Popen(
            command,
            cwd=str(Path(__file__).resolve().parents[2]),
            stdout=stdout_handle,
            stderr=stderr_handle,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )

    pid_path = runtime_service_pid_path(home)
    pid_path.write_text(str(process.pid), encoding="utf-8")
    meta = {
        "started_at": _utc_now(),
        "host": host,
        "port": port,
        "log_level": log_level,
        "command": command,
    }
    _save_service_meta(meta, home)

    return {
        "started": True,
        "already_running": False,
        "running": True,
        "pid": process.pid,
        "url": f"http://{host}:{port}",
        "pid_file": str(pid_path),
        "meta_file": str(runtime_service_meta_path(home)),
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "meta": meta,
    }


def stop_service(home: Path | None = None) -> dict[str, Any]:
    status = service_status(home)
    pid = int(status.get("pid") or 0)
    if not pid:
        return {
            "stopped": False,
            "was_running": False,
            **status,
        }

    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass

    runtime_service_pid_path(home).unlink(missing_ok=True)
    meta = _load_service_meta(home)
    meta["stopped_at"] = _utc_now()
    _save_service_meta(meta, home)

    return {
        "stopped": True,
        "was_running": True,
        "pid": pid,
        "pid_file": str(runtime_service_pid_path(home)),
        "meta_file": str(runtime_service_meta_path(home)),
    }


def restart_service(
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    log_level: str = "info",
    home: Path | None = None,
    python_executable: str | None = None,
) -> dict[str, Any]:
    stopped = stop_service(home)
    started = start_service(
        host=host,
        port=port,
        log_level=log_level,
        home=home,
        python_executable=python_executable,
    )
    return {
        "restarted": True,
        "stopped": stopped,
        "started": started,
        "running": bool(started.get("running")),
        "pid": int(started.get("pid") or 0),
        "url": started.get("url") or "",
    }


def dashboard_url(
    home: Path | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
) -> dict[str, Any]:
    status = service_status(home)
    meta = status.get("meta") or {}
    final_host = str(meta.get("host") or host)
    final_port = int(meta.get("port") or port)
    return {
        "url": f"http://{final_host}:{final_port}",
        "running": bool(status.get("running")),
        "pid": int(status.get("pid") or 0),
    }


def open_dashboard(
    home: Path | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
) -> dict[str, Any]:
    payload = dashboard_url(home, host=host, port=port)
    url = str(payload.get("url") or "")
    opened = False
    error = ""
    try:
        opened = bool(webbrowser.open(url))
    except Exception as exc:
        error = str(exc)
    payload["opened"] = opened
    payload["error"] = error
    return payload
