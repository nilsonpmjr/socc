"""
SOCC Runtime — central orchestrator for tools, agents, and commands.

Bridges the existing ``tools_registry`` with the harness layer, adding
agent management, prompt routing, and unified invocation.

Attribution: Architecture inspired by instructkr/claude-code (Sigrid Jin).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from socc.core.tools_registry import (
    TOOL_REGISTRY,
    ToolResult,
    ToolSpec,
    get_tool,
    invoke_tool,
    list_tools,
    list_tools_specs,
)

from .commands import COMMAND_REGISTRY, CommandResult
from .models import AgentResult, AgentSpecialty, SOCAgentSpec, SOCCommand

__all__ = ["RUNTIME", "RoutedMatch", "SOCRuntime"]

_logger = logging.getLogger(__name__)

_REFERENCE_DIR = Path(__file__).parent / "reference_data"


# ============================================================================
# Routing
# ============================================================================


@dataclass(frozen=True, slots=True)
class RoutedMatch:
    """A single routing suggestion."""

    kind: str  # "tool", "agent", "command"
    name: str
    score: int
    source_hint: str = ""


# ============================================================================
# Runtime
# ============================================================================


class SOCRuntime:
    """Central runtime for the SOCC harness.

    Responsibilities
    ----------------
    * Agent registry (register / get / list)
    * Prompt routing (match user input → tools, agents, commands)
    * Unified tool invocation (delegates to ``tools_registry``)
    * Command dispatch (delegates to ``CommandRegistry``)
    * Snapshot loading from ``reference_data/``
    """

    def __init__(self) -> None:
        self._agents: dict[str, SOCAgentSpec] = {}
        self._initialised = False

    def bootstrap(self) -> None:
        """Load snapshots and mark runtime as ready.

        Safe to call multiple times; subsequent calls are no-ops.
        """
        if self._initialised:
            return
        self._load_agents_snapshot()
        self._initialised = True
        _logger.info(
            "SOCC Runtime bootstrapped: %d tools, %d agents, %d commands",
            len(TOOL_REGISTRY),
            len(self._agents),
            len(COMMAND_REGISTRY.list_names()),
        )

    # ── agent operations ──────────────────────────────────────────────

    def register_agent(self, spec: SOCAgentSpec) -> None:
        if spec.name in self._agents:
            raise ValueError(f"Agent '{spec.name}' is already registered")
        self._agents[spec.name] = spec
        _logger.debug("Registered agent: %s (%s)", spec.name, spec.specialty.value)

    def unregister_agent(self, name: str) -> bool:
        return self._agents.pop(name, None) is not None

    def get_agent(self, name: str) -> SOCAgentSpec | None:
        return self._agents.get(name)

    def list_agents(
        self, specialty: AgentSpecialty | None = None
    ) -> list[SOCAgentSpec]:
        agents = list(self._agents.values())
        if specialty:
            agents = [a for a in agents if a.specialty == specialty]
        return sorted(agents, key=lambda a: a.name)

    # ── tool operations (delegates) ───────────────────────────────────

    @staticmethod
    def get_tool(name: str) -> ToolSpec | None:
        return get_tool(name)

    @staticmethod
    def list_tools(**kwargs: Any) -> list[str]:
        return list_tools(**kwargs)

    @staticmethod
    def list_tools_specs(**kwargs: Any) -> list[ToolSpec]:
        return list_tools_specs(**kwargs)

    @staticmethod
    def invoke_tool(name: str, arguments: dict[str, Any] | None = None) -> ToolResult:
        return invoke_tool(name, arguments)

    # ── command operations (delegates) ────────────────────────────────

    @staticmethod
    def dispatch_command(
        raw_input: str, context: dict[str, Any] | None = None
    ) -> CommandResult:
        return COMMAND_REGISTRY.dispatch(raw_input, context)

    @staticmethod
    def list_commands() -> list[SOCCommand]:
        return COMMAND_REGISTRY.list()

    # ── routing ───────────────────────────────────────────────────────

    def route_prompt(self, prompt: str, limit: int = 5) -> list[RoutedMatch]:
        """Route a user prompt to the most relevant tools / agents / commands.

        Uses simple keyword matching.  Good enough for a first pass;
        can be upgraded to embeddings later.
        """
        tokens = self._tokenise(prompt)
        if not tokens:
            return []

        matches: list[RoutedMatch] = []

        # Score tools
        for name, spec in TOOL_REGISTRY.items():
            score = self._score(
                tokens, [name, spec.description, spec.category.value, *spec.tags]
            )
            if score > 0:
                matches.append(
                    RoutedMatch("tool", name, score, spec.category.value)
                )

        # Score agents
        for name, agent in self._agents.items():
            score = self._score(
                tokens,
                [name, agent.description, agent.specialty.value],
            )
            if score > 0:
                matches.append(
                    RoutedMatch("agent", name, score, agent.specialty.value)
                )

        # Score commands
        for cmd in COMMAND_REGISTRY.list(include_hidden=True):
            score = self._score(
                tokens, [cmd.name, cmd.description, *cmd.aliases]
            )
            if score > 0:
                matches.append(
                    RoutedMatch("command", cmd.name, score, "command")
                )

        matches.sort(key=lambda m: (-m.score, m.name))
        return matches[:limit]

    # ── snapshot loading ──────────────────────────────────────────────

    def _load_agents_snapshot(self) -> None:
        path = _REFERENCE_DIR / "socc_agents_snapshot.json"
        if not path.exists():
            _logger.debug("No agents snapshot at %s", path)
            return
        try:
            data = json.loads(path.read_text())
            for entry in data:
                spec = SOCAgentSpec(
                    name=entry["name"],
                    specialty=AgentSpecialty(entry.get("specialty", "general")),
                    description=entry.get("description", ""),
                    prompt_template=entry.get("prompt_template", ""),
                    tools_whitelist=entry.get("tools_whitelist", []),
                    tools_blacklist=entry.get("tools_blacklist", []),
                    max_steps=entry.get("max_steps", 10),
                    timeout_seconds=entry.get("timeout_seconds", 300),
                    metadata=entry.get("metadata", {}),
                )
                # Use direct dict assignment to skip duplicate check on reload
                self._agents[spec.name] = spec
            _logger.debug("Loaded %d agents from snapshot", len(data))
        except Exception:
            _logger.exception("Failed to load agents snapshot from %s", path)

    # ── helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _tokenise(text: str) -> set[str]:
        tokens = text.lower().replace("/", " ").replace("-", " ").replace("_", " ").split()
        return {t for t in tokens if len(t) > 2}

    @staticmethod
    def _score(tokens: set[str], haystacks: list[str]) -> int:
        score = 0
        for token in tokens:
            for hay in haystacks:
                if token in hay.lower():
                    score += 1
        return score

    # ── repr ──────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"<SOCRuntime tools={len(TOOL_REGISTRY)} "
            f"agents={len(self._agents)} "
            f"commands={len(COMMAND_REGISTRY.list_names())} "
            f"ready={self._initialised}>"
        )


# ── Module-level singleton ────────────────────────────────────────────────

RUNTIME = SOCRuntime()
