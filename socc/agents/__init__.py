"""SOCC Agents package.

Public API
----------
register_builtin_agents()   — register all built-in SOCAgentSpecs in RUNTIME.
                              Safe to call multiple times (idempotent).
"""
from __future__ import annotations

__all__ = ["register_builtin_agents"]


def register_builtin_agents() -> None:
    """Register the three built-in agent specs in the global RUNTIME.

    Idempotent: a second call is a no-op (ValueError from RUNTIME.register_agent
    is silently caught).
    """
    from socc.core.harness.runtime import RUNTIME
    from socc.agents.built_in.soc_analyst import SOC_ANALYST_SPEC
    from socc.agents.built_in.ir_agent import IR_AGENT_SPEC
    from socc.agents.built_in.threat_hunt import THREAT_HUNT_SPEC

    for spec in (SOC_ANALYST_SPEC, IR_AGENT_SPEC, THREAT_HUNT_SPEC):
        try:
            RUNTIME.register_agent(spec)
        except ValueError:
            pass  # already registered — idempotent
