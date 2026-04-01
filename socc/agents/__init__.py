"""
SOCC Agent system — specialised subagents for SOC operations.

Attribution: Architecture inspired by instructkr/claude-code AgentTool.
"""

from .fork import SubagentConfig, SubagentHandle, fork_subagent, list_active_subagents
from .memory import AgentMemory

__all__ = [
    "AgentMemory",
    "SubagentConfig",
    "SubagentHandle",
    "fork_subagent",
    "list_active_subagents",
]
