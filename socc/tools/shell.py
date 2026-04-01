"""Shell execution tool for SOCC.

Facade that delegates security analysis to ``socc.tools.bash`` and
provides the ``bash`` tool for the tools registry.

Security features (via socc.tools.bash.security):
- 4-level risk classification (SAFE / MODERATE / DESTRUCTIVE / BLOCKED)
- Pattern-based command analysis
- Automatic secret redaction
- RBAC permission checks
- Optional sandbox isolation
"""
from __future__ import annotations

import subprocess
import time
from typing import Any

from socc.core.tools_registry import (
    ParamSpec,
    RiskLevel,
    ToolCategory,
    ToolSpec,
    register_tool,
    unregister_tool,
)
from socc.tools.bash.permissions import AuditEntry, get_audit_log
from socc.tools.bash.sandbox import SandboxConfig, run_sandboxed
from socc.tools.bash.security import (
    CommandRisk,
    analyze_command,
    redact_secrets,
    should_use_sandbox,
)


# ---------------------------------------------------------------------------
# Tool handler
# ---------------------------------------------------------------------------


def bash(
    command: str,
    timeout: int = 30,
    *,
    role: str = "analyst",
    use_sandbox: bool | None = None,
) -> dict[str, Any]:
    """Execute a shell command and return its output.

    Args:
        command: Shell command to execute.
        timeout: Maximum execution time in seconds (default: 30, max: 120).
        role: User role for permission checks (analyst, senior_analyst, admin).
        use_sandbox: Force sandbox on/off.  None = auto-detect.

    Returns:
        dict with keys: stdout, stderr, exit_code, timed_out, blocked, risk.

    Security:
        - Commands are classified into risk levels before execution.
        - BLOCKED commands are always rejected.
        - DESTRUCTIVE commands require admin role.
        - Secrets are automatically redacted from output.
        - Audit log records all executions.
    """
    safe_timeout = min(max(1, timeout), 120)

    # Analyse command risk
    analysis = analyze_command(command)

    # BLOCKED: always reject
    if analysis.risk == CommandRisk.BLOCKED:
        _audit(command, role, analysis.risk.value, allowed=False)
        return {
            "stdout": "",
            "stderr": f"Command blocked: {analysis.reason}",
            "exit_code": -1,
            "timed_out": False,
            "blocked": True,
            "risk": analysis.risk.value,
        }

    # DESTRUCTIVE: reject for non-admin roles
    if analysis.risk == CommandRisk.DESTRUCTIVE and role != "admin":
        _audit(command, role, analysis.risk.value, allowed=False)
        return {
            "stdout": "",
            "stderr": (
                f"Command blocked by policy: requires admin role (current: {role}). "
                f"Reason: {analysis.reason}"
            ),
            "exit_code": -1,
            "timed_out": False,
            "blocked": True,
            "risk": analysis.risk.value,
        }

    # Decide sandbox
    sandbox = use_sandbox if use_sandbox is not None else should_use_sandbox(
        command, role=role
    )

    if sandbox:
        result = run_sandboxed(command, SandboxConfig(timeout_seconds=safe_timeout))
        _audit(
            command, role, analysis.risk.value,
            allowed=True, exit_code=result.exit_code, timed_out=result.timed_out,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
            "blocked": False,
            "risk": analysis.risk.value,
            "sandbox": result.sandbox_type,
        }

    # Direct execution
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=safe_timeout,
        )
        stdout = redact_secrets(proc.stdout)
        stderr = redact_secrets(proc.stderr)

        _audit(
            command, role, analysis.risk.value,
            allowed=True, exit_code=proc.returncode,
        )
        return {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": proc.returncode,
            "timed_out": False,
            "blocked": False,
            "risk": analysis.risk.value,
        }

    except subprocess.TimeoutExpired:
        _audit(
            command, role, analysis.risk.value,
            allowed=True, exit_code=-1, timed_out=True,
        )
        return {
            "stdout": "",
            "stderr": f"Command timed out after {safe_timeout}s",
            "exit_code": -1,
            "timed_out": True,
            "blocked": False,
            "risk": analysis.risk.value,
        }

    except Exception as exc:  # noqa: BLE001
        _audit(
            command, role, analysis.risk.value,
            allowed=True, exit_code=-1,
        )
        return {
            "stdout": "",
            "stderr": f"Execution error: {type(exc).__name__}: {exc}",
            "exit_code": -1,
            "timed_out": False,
            "blocked": False,
            "risk": analysis.risk.value,
        }


def _audit(
    command: str,
    role: str,
    risk: str,
    *,
    allowed: bool,
    exit_code: int | None = None,
    timed_out: bool = False,
) -> None:
    """Record execution in the audit log."""
    try:
        get_audit_log().record(AuditEntry(
            timestamp=time.time(),
            command=command,
            role=role,
            risk=risk,
            allowed=allowed,
            exit_code=exit_code,
            timed_out=timed_out,
        ))
    except Exception:  # noqa: BLE001
        pass  # audit failure should never break execution


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def _register() -> None:
    register_tool(ToolSpec(
        name="bash",
        description=(
            "Execute a shell command and return its output. "
            "Commands are classified by risk level (safe/moderate/destructive/blocked). "
            "Destructive commands require admin role. "
            "Secrets and tokens are automatically redacted from the output. "
            "Timeout is configurable up to 120 seconds."
        ),
        parameters={
            "command": ParamSpec(
                type="string",
                description="Shell command to execute",
                required=True,
            ),
            "timeout": ParamSpec(
                type="integer",
                description="Timeout in seconds (default: 30, max: 120)",
                required=False,
                default=30,
            ),
        },
        handler=bash,
        category=ToolCategory.SHELL,
        risk_level=RiskLevel.HIGH,
        tags=["shell", "bash", "command", "execution"],
        example='bash(command="ls -la /tmp", timeout=10)',
    ))


_register()


def register_shell_tools() -> None:
    """Register (or re-register) shell tools. Safe to call multiple times.

    Useful in tests after ``clear_registry()`` to restore the shell tool set.
    """
    unregister_tool("bash")
    _register()
