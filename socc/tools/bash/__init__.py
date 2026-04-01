"""
SOCC BashTool — security-hardened shell execution.

Provides command risk analysis, RBAC permissions, and optional sandbox
isolation for shell commands in SOC operations.

Attribution: Security model inspired by instructkr/claude-code BashTool.
"""

from .permissions import AuditEntry, Role, check_permission
from .security import CommandAnalysis, CommandRisk, analyze_command, redact_secrets

__all__ = [
    "AuditEntry",
    "CommandAnalysis",
    "CommandRisk",
    "Role",
    "analyze_command",
    "check_permission",
    "redact_secrets",
]
