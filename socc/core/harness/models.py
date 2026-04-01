"""
SOCC Harness data models.

Extends ``socc.core.tools_registry`` with agent specs, command specs,
and SOC-specific enums.  The existing ``ToolSpec`` / ``ParamSpec`` from
tools_registry remain the canonical way to *register* tools; the classes
here add the *harness layer* on top (routing, agents, commands).

Attribution: Architecture inspired by instructkr/claude-code (Sigrid Jin).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

# Re-export core enums so consumers can import everything from harness.models
from socc.core.tools_registry import (
    ParamSpec,
    RiskLevel,
    ToolCategory,
    ToolResult,
    ToolSpec,
)

__all__ = [
    # Re-exports
    "ParamSpec",
    "RiskLevel",
    "ToolCategory",
    "ToolResult",
    "ToolSpec",
    # New
    "AgentResult",
    "AgentSpecialty",
    "CommandArg",
    "CommandResult",
    "SOCAgentSpec",
    "SOCCommand",
    "SOCToolSpec",
]


# ============================================================================
# Enums
# ============================================================================


class AgentSpecialty(str, Enum):
    """Specialisation areas for SOC agents."""

    GENERAL = "general"
    IR = "incident_response"
    TI = "threat_intel"
    HUNT = "threat_hunt"
    MALWARE = "malware_analysis"
    FORENSICS = "forensics"


# ============================================================================
# SOCToolSpec — thin wrapper adding SOC-specific metadata
# ============================================================================


@dataclass(slots=True)
class SOCToolSpec:
    """SOC-specific tool metadata that wraps the base ``ToolSpec``.

    This is **not** a replacement for ``ToolSpec`` — it provides extra SOC
    context (aliases, permissions, MITRE mapping) while delegating
    registration and invocation to the existing ``tools_registry``.
    """

    base: ToolSpec
    aliases: list[str] = field(default_factory=list)
    permissions_required: list[str] = field(default_factory=list)
    mitre_techniques: list[str] = field(default_factory=list)

    # Convenience delegates ─────────────────────────────────────────────
    @property
    def name(self) -> str:
        return self.base.name

    @property
    def description(self) -> str:
        return self.base.description

    @property
    def category(self) -> ToolCategory:
        return self.base.category

    @property
    def risk_level(self) -> RiskLevel:
        return self.base.risk_level

    def to_json_schema(self) -> dict[str, Any]:
        schema = self.base.to_json_schema()
        if self.mitre_techniques:
            schema["mitre_techniques"] = self.mitre_techniques
        return schema


# ============================================================================
# Agent specification
# ============================================================================


@dataclass(slots=True)
class SOCAgentSpec:
    """Specification for a specialised SOC agent."""

    name: str
    specialty: AgentSpecialty
    description: str
    prompt_template: str
    tools_whitelist: list[str] = field(default_factory=list)
    tools_blacklist: list[str] = field(default_factory=list)
    max_steps: int = 10
    timeout_seconds: int = 300
    metadata: dict[str, Any] = field(default_factory=dict)

    def can_use_tool(self, tool_name: str) -> bool:
        """Return True if agent is allowed to invoke *tool_name*."""
        if tool_name in self.tools_blacklist:
            return False
        if not self.tools_whitelist:
            return True
        return tool_name in self.tools_whitelist


@dataclass(slots=True)
class AgentResult:
    """Result returned by a completed agent execution."""

    ok: bool
    agent_name: str
    conclusion: str
    findings: list[str] = field(default_factory=list)
    tool_calls: list[ToolResult] = field(default_factory=list)
    reasoning_trace: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "agent_name": self.agent_name,
            "conclusion": self.conclusion,
            "findings": self.findings,
            "reasoning_trace": self.reasoning_trace,
            "elapsed_seconds": self.elapsed_seconds,
        }


# ============================================================================
# Command specification
# ============================================================================


@dataclass(slots=True)
class CommandArg:
    """Single argument for a CLI command."""

    name: str
    type: str = "string"
    required: bool = False
    default: Any = None
    help: str = ""


@dataclass(slots=True)
class SOCCommand:
    """Specification for a slash-command (e.g. ``/case``, ``/hunt``)."""

    name: str
    description: str
    handler: Callable[..., Any]
    aliases: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    arguments: list[CommandArg] = field(default_factory=list)
    hidden: bool = False

    def help_text(self) -> str:
        parts = [f"**/{self.name}** — {self.description}"]
        if self.aliases:
            parts.append(f"  Aliases: {', '.join('/' + a for a in self.aliases)}")
        if self.arguments:
            parts.append("  Arguments:")
            for arg in self.arguments:
                req = "(required)" if arg.required else f"(default: {arg.default})"
                parts.append(f"    {arg.name}: {arg.type} {req} — {arg.help}")
        return "\n".join(parts)


@dataclass(slots=True)
class CommandResult:
    """Result returned by a command handler."""

    ok: bool
    output: str = ""
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
