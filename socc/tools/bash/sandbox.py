"""
Sandbox execution for SOCC BashTool.

Provides resource-limited command execution using Linux cgroups, namespaces,
or simple subprocess constraints when full isolation is not available.

Attribution: Inspired by instructkr/claude-code BashTool sandbox.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .security import CommandRisk, analyze_command, redact_secrets

__all__ = [
    "SandboxConfig",
    "SandboxResult",
    "run_sandboxed",
]

_logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SandboxConfig:
    """Configuration for sandboxed execution."""

    timeout_seconds: int = 30
    max_output_bytes: int = 1_048_576  # 1 MB
    memory_limit_mb: int = 512
    cpu_limit_seconds: int = 30
    network_enabled: bool = True
    read_only_root: bool = False
    working_dir: str | None = None
    env_whitelist: list[str] | None = None  # None = inherit all


@dataclass(slots=True)
class SandboxResult:
    """Result from sandboxed command execution."""

    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False
    oom_killed: bool = False
    sandbox_type: str = "subprocess"  # "subprocess", "unshare", "container"
    metadata: dict[str, Any] | None = None


def run_sandboxed(
    command: str,
    config: SandboxConfig | None = None,
) -> SandboxResult:
    """Execute a command with resource constraints.

    Attempts isolation strategies in order of preference:
    1. ``unshare`` (Linux namespace isolation) — if available and permitted
    2. ``subprocess`` with resource limits — always available

    The command output is automatically redacted for secrets.
    """
    config = config or SandboxConfig()

    # Try unshare if available
    if _can_use_unshare():
        return _run_with_unshare(command, config)

    # Fallback to subprocess with limits
    return _run_with_subprocess(command, config)


# ============================================================================
# Subprocess sandbox (always available)
# ============================================================================


def _run_with_subprocess(
    command: str,
    config: SandboxConfig,
) -> SandboxResult:
    """Run command in a constrained subprocess."""
    env = _build_env(config)
    cwd = config.working_dir or os.getcwd()

    # Build wrapper with ulimit constraints
    wrapper = _build_ulimit_wrapper(command, config)

    try:
        proc = subprocess.run(
            wrapper,
            shell=True,
            capture_output=True,
            text=True,
            timeout=config.timeout_seconds,
            env=env,
            cwd=cwd,
        )

        stdout = _truncate(redact_secrets(proc.stdout), config.max_output_bytes)
        stderr = _truncate(redact_secrets(proc.stderr), config.max_output_bytes)

        return SandboxResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=proc.returncode,
            sandbox_type="subprocess",
        )

    except subprocess.TimeoutExpired:
        return SandboxResult(
            stdout="",
            stderr=f"Command timed out after {config.timeout_seconds}s",
            exit_code=-1,
            timed_out=True,
            sandbox_type="subprocess",
        )

    except Exception as exc:
        return SandboxResult(
            stdout="",
            stderr=f"Sandbox error: {type(exc).__name__}: {exc}",
            exit_code=-1,
            sandbox_type="subprocess",
        )


# ============================================================================
# Unshare sandbox (Linux-only, better isolation)
# ============================================================================


def _can_use_unshare() -> bool:
    """Check if unshare is available AND we have permission to create namespaces.

    A simple ``unshare --help`` just tests the binary exists; we need to test
    an actual (cheap) namespace creation to detect permission denials.
    """
    try:
        result = subprocess.run(
            ["unshare", "--user", "--", "true"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def _run_with_unshare(
    command: str,
    config: SandboxConfig,
) -> SandboxResult:
    """Run command in a Linux namespace via unshare."""
    env = _build_env(config)
    cwd = config.working_dir or os.getcwd()

    # Build unshare command
    unshare_flags = ["unshare", "--fork", "--pid", "--mount-proc"]
    if not config.network_enabled:
        unshare_flags.append("--net")

    ulimit_wrapper = _build_ulimit_wrapper(command, config)
    full_cmd = unshare_flags + ["bash", "-c", ulimit_wrapper]

    try:
        proc = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=config.timeout_seconds,
            env=env,
            cwd=cwd,
        )

        stdout = _truncate(redact_secrets(proc.stdout), config.max_output_bytes)
        stderr = _truncate(redact_secrets(proc.stderr), config.max_output_bytes)

        # Detect runtime permission denial (unshare itself returned non-zero
        # with an "Operation not permitted" / "failed" message in stderr).
        if proc.returncode != 0 and (
            "not permitted" in proc.stderr.lower()
            or ("unshare" in proc.stderr.lower() and "failed" in proc.stderr.lower())
        ):
            _logger.debug("unshare denied at runtime, falling back to subprocess")
            return _run_with_subprocess(command, config)

        return SandboxResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=proc.returncode,
            sandbox_type="unshare",
        )

    except subprocess.TimeoutExpired:
        return SandboxResult(
            stdout="",
            stderr=f"Command timed out after {config.timeout_seconds}s (unshare)",
            exit_code=-1,
            timed_out=True,
            sandbox_type="unshare",
        )

    except PermissionError:
        _logger.debug("unshare not permitted, falling back to subprocess")
        return _run_with_subprocess(command, config)

    except Exception as exc:
        return SandboxResult(
            stdout="",
            stderr=f"Sandbox error: {type(exc).__name__}: {exc}",
            exit_code=-1,
            sandbox_type="unshare",
        )


# ============================================================================
# Helpers
# ============================================================================


def _build_ulimit_wrapper(command: str, config: SandboxConfig) -> str:
    """Wrap command with ulimit constraints.

    Each ulimit is made non-fatal (``|| true``) because some environments
    (containers, non-root users, certain kernel configs) deny virtual-memory
    or CPU-time limits; we still want the command itself to run.
    """
    limits = []
    # Virtual memory limit (KB) — non-fatal
    mem_kb = config.memory_limit_mb * 1024
    limits.append(f"ulimit -v {mem_kb} 2>/dev/null || true")
    # CPU time limit (seconds) — non-fatal
    limits.append(f"ulimit -t {config.cpu_limit_seconds} 2>/dev/null || true")
    # Max file size (~100 MB) — non-fatal
    limits.append("ulimit -f 204800 2>/dev/null || true")

    return "; ".join(limits) + f"; {command}"


def _build_env(config: SandboxConfig) -> dict[str, str]:
    """Build environment for sandboxed execution."""
    if config.env_whitelist is None:
        # Inherit current env but strip sensitive vars
        env = dict(os.environ)
        for key in list(env.keys()):
            key_upper = key.upper()
            if any(secret in key_upper for secret in ("SECRET", "TOKEN", "PASSWORD", "KEY", "CREDENTIAL")):
                del env[key]
        return env

    # Only include whitelisted vars
    env: dict[str, str] = {}
    for key in config.env_whitelist:
        if key in os.environ:
            env[key] = os.environ[key]

    # Always include essential vars
    for key in ("PATH", "HOME", "USER", "LANG", "TERM"):
        if key not in env and key in os.environ:
            env[key] = os.environ[key]

    return env


def _truncate(text: str, max_bytes: int) -> str:
    """Truncate text to max_bytes."""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return truncated + "\n[... output truncated ...]"
