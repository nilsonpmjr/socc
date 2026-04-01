"""
RBAC permission system for SOCC BashTool.

Defines roles with escalating privileges and maintains an audit log
of all command executions.

Attribution: Inspired by instructkr/claude-code BashTool permissions.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .security import CommandRisk, analyze_command

__all__ = [
    "AuditEntry",
    "AuditLog",
    "Role",
    "check_permission",
    "get_audit_log",
]

_logger = logging.getLogger(__name__)


class Role(str, Enum):
    """SOCC user roles with escalating shell privileges."""

    ANALYST = "analyst"               # Can run SAFE commands only
    SENIOR_ANALYST = "senior_analyst"  # Can run SAFE + MODERATE
    ADMIN = "admin"                   # Can run SAFE + MODERATE + DESTRUCTIVE (with audit)

    @property
    def allowed_risks(self) -> frozenset[CommandRisk]:
        return _ROLE_PERMISSIONS[self]


_ROLE_PERMISSIONS: dict[Role, frozenset[CommandRisk]] = {
    Role.ANALYST:        frozenset({CommandRisk.SAFE}),
    Role.SENIOR_ANALYST: frozenset({CommandRisk.SAFE, CommandRisk.MODERATE}),
    Role.ADMIN:          frozenset({CommandRisk.SAFE, CommandRisk.MODERATE, CommandRisk.DESTRUCTIVE}),
}


# ============================================================================
# Permission check
# ============================================================================


@dataclass(frozen=True, slots=True)
class PermissionResult:
    """Result of a permission check."""

    allowed: bool
    reason: str
    role: str
    risk: str
    requires_audit: bool = False


def check_permission(
    command: str,
    role: Role | str = Role.ANALYST,
) -> PermissionResult:
    """Check whether *role* is allowed to execute *command*.

    Returns a ``PermissionResult`` with the decision and reasoning.
    """
    if isinstance(role, str):
        try:
            role = Role(role.lower())
        except ValueError:
            return PermissionResult(
                allowed=False,
                reason=f"Unknown role: {role}",
                role=str(role),
                risk="unknown",
            )

    analysis = analyze_command(command)

    # Blocked commands are always denied
    if analysis.risk == CommandRisk.BLOCKED:
        return PermissionResult(
            allowed=False,
            reason=f"Command is blocked: {analysis.reason}",
            role=role.value,
            risk=analysis.risk.value,
        )

    # Check role permissions
    if analysis.risk in role.allowed_risks:
        requires_audit = analysis.risk != CommandRisk.SAFE
        return PermissionResult(
            allowed=True,
            reason=f"Role '{role.value}' is allowed to run {analysis.risk.value} commands",
            role=role.value,
            risk=analysis.risk.value,
            requires_audit=requires_audit,
        )

    return PermissionResult(
        allowed=False,
        reason=(
            f"Role '{role.value}' cannot run {analysis.risk.value} commands. "
            f"Requires: {_role_for_risk(analysis.risk)}"
        ),
        role=role.value,
        risk=analysis.risk.value,
    )


def _role_for_risk(risk: CommandRisk) -> str:
    """Return the minimum role required for a given risk level."""
    for role in (Role.ANALYST, Role.SENIOR_ANALYST, Role.ADMIN):
        if risk in role.allowed_risks:
            return role.value
    return "none (blocked)"


# ============================================================================
# Audit log
# ============================================================================


@dataclass(slots=True)
class AuditEntry:
    """Single audit log entry for a command execution."""

    timestamp: float
    command: str
    role: str
    risk: str
    allowed: bool
    exit_code: int | None = None
    timed_out: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class AuditLog:
    """Append-only audit log for command executions.

    Persists entries to ``~/.socc/audit/commands.jsonl``.
    """

    def __init__(self, log_dir: Path | None = None) -> None:
        self._dir = log_dir or Path.home() / ".socc" / "audit"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "commands.jsonl"

    def record(self, entry: AuditEntry) -> None:
        """Append an entry to the audit log."""
        try:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(asdict(entry)) + "\n")
        except OSError:
            _logger.exception("Failed to write audit entry")

    def recent(self, limit: int = 50) -> list[AuditEntry]:
        """Return the most recent entries."""
        if not self._path.exists():
            return []
        try:
            lines = self._path.read_text().strip().splitlines()
            entries = []
            for line in lines[-limit:]:
                data = json.loads(line)
                entries.append(AuditEntry(**data))
            return entries
        except (OSError, json.JSONDecodeError):
            _logger.exception("Failed to read audit log")
            return []

    def search(self, command_pattern: str, limit: int = 50) -> list[AuditEntry]:
        """Search audit log for entries matching *command_pattern*."""
        import re as _re

        pattern = _re.compile(command_pattern, _re.I)
        results: list[AuditEntry] = []
        for entry in self.recent(limit=500):
            if pattern.search(entry.command):
                results.append(entry)
                if len(results) >= limit:
                    break
        return results


# Module-level singleton
_AUDIT_LOG: AuditLog | None = None


def get_audit_log() -> AuditLog:
    """Return the global audit log instance (lazy-created)."""
    global _AUDIT_LOG
    if _AUDIT_LOG is None:
        _AUDIT_LOG = AuditLog()
    return _AUDIT_LOG
