"""
SOCC Harness — runtime, models, and command system.

Based on Claude Code Python Port architecture (instructkr/claude-code).
Extends the existing tools_registry.py with agent routing, command dispatch,
and SOC-specific models.
"""

from .models import (
    AgentResult,
    AgentSpecialty,
    CommandArg,
    RiskLevel,
    SOCAgentSpec,
    SOCCommand,
    SOCToolSpec,
    ToolCategory,
    ToolResult,
)
from .runtime import RUNTIME, SOCRuntime

__all__ = [
    "AgentResult",
    "AgentSpecialty",
    "CommandArg",
    "RiskLevel",
    "RUNTIME",
    "SOCAgentSpec",
    "SOCCommand",
    "SOCRuntime",
    "SOCToolSpec",
    "ToolCategory",
    "ToolResult",
]
