"""Harness runtime that merges snapshot metadata with the live registry."""

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
from .models import (
    AgentResult,
    AgentSpecialty,
    CommandArg,
    InventoryRecord,
    InventoryStatus,
    SOCAgentSpec,
    SOCCommand,
)

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
    available: bool = True
    status: str = InventoryStatus.IMPLEMENTED.value


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
        self._agent_sources: dict[str, str] = {}
        self._tool_snapshots: dict[str, dict[str, Any]] = {}
        self._command_snapshots: dict[str, dict[str, Any]] = {}
        self._initialised = False

    def bootstrap(self) -> None:
        """Load snapshot metadata and cache a first live-inventory view."""
        if self._initialised:
            self.refresh_live_inventory()
            return
        self._tool_snapshots = self._load_snapshot_file("socc_tools_snapshot.json")
        self._command_snapshots = self._load_snapshot_file(
            "socc_commands_snapshot.json"
        )
        self._load_agents_snapshot()
        self.refresh_live_inventory()
        self._initialised = True
        _logger.info(
            "SOCC Runtime bootstrapped: %d tools, %d agents, %d commands",
            len(self.list_tool_inventory(limit=1000)),
            len(self.list_agent_inventory(limit=1000)),
            len(self.list_command_inventory(limit=1000, include_hidden=True)),
        )

    def refresh_live_inventory(self) -> None:
        """Refresh cached registry-derived state."""
        self._live_tool_names = set(TOOL_REGISTRY)
        self._live_command_names = {
            command.name: command for command in COMMAND_REGISTRY.list(include_hidden=True)
        }

    # ── agent operations ──────────────────────────────────────────────

    def register_agent(self, spec: SOCAgentSpec) -> None:
        existing_source = self._agent_sources.get(spec.name)
        if spec.name in self._agents and existing_source != "snapshot":
            raise ValueError(f"Agent '{spec.name}' is already registered")
        self._agents[spec.name] = spec
        self._agent_sources[spec.name] = (
            "live+snapshot" if existing_source == "snapshot" else "live"
        )
        _logger.debug("Registered agent: %s (%s)", spec.name, spec.specialty.value)

    def unregister_agent(self, name: str) -> bool:
        removed = self._agents.pop(name, None) is not None
        self._agent_sources.pop(name, None)
        return removed

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

    @staticmethod
    def command_help(name: str | None = None) -> str:
        return COMMAND_REGISTRY.help(name)

    # ── routing ───────────────────────────────────────────────────────

    def route_prompt(self, prompt: str, limit: int = 5) -> list[RoutedMatch]:
        """Route a user prompt to the most relevant tools, agents, and commands."""
        tokens = self._tokenise(prompt)
        if not tokens:
            return []

        matches: list[RoutedMatch] = []

        for record in self.list_tool_inventory(limit=1000):
            score = self._inventory_score(tokens, record)
            if score > 0:
                matches.append(
                    RoutedMatch(
                        "tool",
                        record.name,
                        score,
                        record.category,
                        available=record.available,
                        status=record.status.value,
                    )
                )

        for record in self.list_agent_inventory(limit=1000):
            score = self._inventory_score(tokens, record)
            if score > 0:
                matches.append(
                    RoutedMatch(
                        "agent",
                        record.name,
                        score,
                        record.specialty,
                        available=record.available,
                        status=record.status.value,
                    )
                )

        for record in self.list_command_inventory(limit=1000, include_hidden=True):
            score = self._inventory_score(tokens, record)
            if score > 0:
                matches.append(
                    RoutedMatch(
                        "command",
                        record.name,
                        score,
                        "command",
                        available=record.available,
                        status=record.status.value,
                    )
                )

        matches.sort(key=lambda item: (-item.score, not item.available, item.name))
        return matches[:limit]

    def list_tool_inventory(
        self,
        *,
        query: str = "",
        limit: int = 50,
    ) -> list[InventoryRecord]:
        self.refresh_live_inventory()
        records = [
            self._build_tool_record(name)
            for name in sorted(set(self._tool_snapshots) | set(TOOL_REGISTRY))
        ]
        return self._filter_records(records, query=query, limit=limit)

    def get_tool_record(self, name: str) -> InventoryRecord | None:
        self.refresh_live_inventory()
        key = name.strip().lower()
        if not key:
            return None
        if key in TOOL_REGISTRY or key in self._tool_snapshots:
            return self._build_tool_record(key)
        return None

    def list_command_inventory(
        self,
        *,
        query: str = "",
        limit: int = 50,
        include_hidden: bool = False,
    ) -> list[InventoryRecord]:
        self.refresh_live_inventory()
        live_names = {
            command.name
            for command in COMMAND_REGISTRY.list(include_hidden=include_hidden)
        }
        snapshot_names = set(self._command_snapshots)
        records = [
            self._build_command_record(name)
            for name in sorted(live_names | snapshot_names)
        ]
        if not include_hidden:
            records = [record for record in records if not record.metadata.get("hidden")]
        return self._filter_records(records, query=query, limit=limit)

    def get_command_record(self, name: str) -> InventoryRecord | None:
        self.refresh_live_inventory()
        key = name.lower().lstrip("/")
        live_command = COMMAND_REGISTRY.get(key)
        if live_command:
            return self._build_command_record(live_command.name)
        for snapshot_name, snapshot in self._command_snapshots.items():
            aliases = [alias.lower().lstrip("/") for alias in snapshot.get("aliases", [])]
            if snapshot_name == key or key in aliases:
                return self._build_command_record(snapshot_name)
        return None

    def list_agent_inventory(
        self,
        *,
        query: str = "",
        limit: int = 50,
    ) -> list[InventoryRecord]:
        self.refresh_live_inventory()
        records = [
            self._build_agent_record(name)
            for name in sorted(self._agents)
        ]
        return self._filter_records(records, query=query, limit=limit)

    def get_agent_record(self, name: str) -> InventoryRecord | None:
        key = name.strip().lower()
        if not key:
            return None
        spec = self.get_agent(key)
        if spec:
            return self._build_agent_record(spec.name)
        for agent_name, agent_spec in self._agents.items():
            if agent_spec.specialty.value == key:
                return self._build_agent_record(agent_name)
        return None

    # ── snapshot loading ──────────────────────────────────────────────

    @staticmethod
    def _load_snapshot_file(filename: str) -> dict[str, dict[str, Any]]:
        path = _REFERENCE_DIR / filename
        if not path.exists():
            return {}
        try:
            raw_entries = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            _logger.exception("Failed to parse snapshot file %s", path)
            return {}
        entries: dict[str, dict[str, Any]] = {}
        for entry in raw_entries:
            name = str(entry.get("name") or "").strip().lower().lstrip("/")
            if name:
                entries[name] = entry
        return entries

    def _load_agents_snapshot(self) -> None:
        entries = self._load_snapshot_file("socc_agents_snapshot.json")
        for name, entry in entries.items():
            specialty_value = str(entry.get("specialty") or AgentSpecialty.GENERAL.value)
            try:
                specialty = AgentSpecialty(specialty_value)
            except ValueError:
                specialty = AgentSpecialty.GENERAL
            spec = SOCAgentSpec(
                name=name,
                specialty=specialty,
                description=str(entry.get("description") or ""),
                prompt_template=str(entry.get("prompt_template") or ""),
                tools_whitelist=list(entry.get("tools_whitelist") or []),
                tools_blacklist=list(entry.get("tools_blacklist") or []),
                max_steps=int(entry.get("max_steps") or 10),
                timeout_seconds=int(entry.get("timeout_seconds") or 300),
                metadata=dict(entry.get("metadata") or {}),
            )
            if name not in self._agents:
                self._agents[name] = spec
                self._agent_sources[name] = "snapshot"
        _logger.debug("Loaded %d agent snapshots", len(entries))

    # ── helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _tokenise(text: str) -> set[str]:
        tokens = text.lower().replace("/", " ").replace("-", " ").replace("_", " ").split()
        return {t for t in tokens if t}

    @staticmethod
    def _score_value(token: str, value: str) -> int:
        normalised = value.lower().strip()
        if not normalised:
            return 0
        if token == normalised:
            return 6
        parts = {part for part in normalised.replace("/", " ").replace("-", " ").replace("_", " ").split() if part}
        if token in parts:
            return 4
        if any(part.startswith(token) for part in parts):
            return 2
        if token in normalised:
            return 1
        return 0

    def _inventory_score(self, tokens: set[str], record: InventoryRecord) -> int:
        fields = [
            record.name,
            record.description,
            record.category,
            record.risk_level,
            record.specialty,
            *record.aliases,
            *record.tags,
            *(argument.name for argument in record.arguments),
            *(argument.help for argument in record.arguments),
        ]
        score = 0
        for token in tokens:
            score += max(
                (self._score_value(token, value) for value in fields if value),
                default=0,
            )
        if score and record.available:
            score += 1
        return score

    def _filter_records(
        self,
        records: list[InventoryRecord],
        *,
        query: str,
        limit: int,
    ) -> list[InventoryRecord]:
        cleaned_query = query.strip()
        if not cleaned_query:
            ordered = sorted(records, key=lambda record: (not record.available, record.name))
            return ordered[:limit]
        tokens = self._tokenise(cleaned_query)
        ranked = []
        for record in records:
            score = self._inventory_score(tokens, record)
            if score > 0:
                ranked.append((score, record))
        ranked.sort(key=lambda item: (-item[0], not item[1].available, item[1].name))
        return [record for _, record in ranked[:limit]]

    @staticmethod
    def _build_source(has_live: bool, has_snapshot: bool) -> str:
        if has_live and has_snapshot:
            return "live+snapshot"
        if has_live:
            return "live"
        return "snapshot"

    @staticmethod
    def _build_status(has_live: bool, has_snapshot: bool) -> InventoryStatus:
        if has_live:
            return InventoryStatus.IMPLEMENTED
        if has_snapshot:
            return InventoryStatus.PLANNED
        return InventoryStatus.UNAVAILABLE

    def _build_tool_record(self, name: str) -> InventoryRecord:
        live_spec = TOOL_REGISTRY.get(name)
        snapshot = self._tool_snapshots.get(name, {})
        has_live = live_spec is not None
        has_snapshot = bool(snapshot)
        return InventoryRecord(
            kind="tool",
            name=name,
            description=(
                live_spec.description
                if live_spec is not None
                else str(snapshot.get("description") or "")
            ),
            available=has_live,
            status=self._build_status(has_live, has_snapshot),
            source=self._build_source(has_live, has_snapshot),
            tags=list(live_spec.tags if live_spec is not None else snapshot.get("tags") or []),
            category=(
                live_spec.category.value
                if live_spec is not None
                else str(snapshot.get("category") or "")
            ),
            risk_level=(
                live_spec.risk_level.value
                if live_spec is not None
                else str(snapshot.get("risk_level") or "")
            ),
            metadata={
                "requires_auth": (
                    bool(live_spec.requires_auth)
                    if live_spec is not None
                    else bool(snapshot.get("requires_auth", False))
                ),
                "timeout_seconds": (
                    live_spec.timeout_seconds
                    if live_spec is not None
                    else snapshot.get("timeout_seconds")
                ),
                "example": (
                    live_spec.example
                    if live_spec is not None
                    else snapshot.get("example")
                ),
            },
        )

    def _build_command_record(self, name: str) -> InventoryRecord:
        live_command = COMMAND_REGISTRY.get(name)
        snapshot = self._command_snapshots.get(name, {})
        has_live = live_command is not None
        has_snapshot = bool(snapshot)
        snapshot_args = [
            CommandArg(
                name=str(argument.get("name") or ""),
                type=str(argument.get("type") or "string"),
                required=bool(argument.get("required", False)),
                default=argument.get("default"),
                help=str(argument.get("help") or ""),
            )
            for argument in snapshot.get("arguments", [])
        ]
        return InventoryRecord(
            kind="command",
            name=name,
            description=(
                live_command.description
                if live_command is not None
                else str(snapshot.get("description") or "")
            ),
            available=has_live,
            status=self._build_status(has_live, has_snapshot),
            source=self._build_source(has_live, has_snapshot),
            aliases=list(
                live_command.aliases
                if live_command is not None
                else snapshot.get("aliases") or []
            ),
            arguments=list(live_command.arguments if live_command is not None else snapshot_args),
            metadata={
                "hidden": (
                    bool(live_command.hidden)
                    if live_command is not None
                    else bool(snapshot.get("hidden", False))
                ),
            },
        )

    def _build_agent_record(self, name: str) -> InventoryRecord:
        spec = self._agents[name]
        source = self._agent_sources.get(name, "live")
        has_live = source in {"live", "live+snapshot"}
        has_snapshot = source in {"snapshot", "live+snapshot"}
        return InventoryRecord(
            kind="agent",
            name=spec.name,
            description=spec.description,
            available=has_live,
            status=self._build_status(has_live, has_snapshot),
            source=source,
            specialty=spec.specialty.value,
            metadata={
                "max_steps": spec.max_steps,
                "timeout_seconds": spec.timeout_seconds,
                "tools_whitelist": list(spec.tools_whitelist),
                "tools_blacklist": list(spec.tools_blacklist),
            },
        )

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
