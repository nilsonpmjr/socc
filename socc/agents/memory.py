"""
Agent memory system for SOCC.

Provides persistent state for agents across sessions, stored as
JSON snapshots in ``~/.socc/agents/<agent_id>/``.

Attribution: Inspired by instructkr/claude-code AgentTool/agentMemory.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["AgentMemory", "MemorySnapshot"]

_logger = logging.getLogger(__name__)


@dataclass
class MemorySnapshot:
    """A point-in-time snapshot of agent state."""

    agent_name: str
    timestamp: float
    entries: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentMemory:
    """Persistent key-value memory for an agent.

    Data is stored as a single JSON file per agent, overwritten on each save.
    A lightweight JSONL append log tracks all mutations for audit.

    Usage::

        mem = AgentMemory("soc_analyst")
        mem.set("last_case_id", "INC-2026-0042")
        mem.set("known_iocs", ["1.2.3.4", "evil.com"])
        mem.save()

        # Later...
        mem = AgentMemory("soc_analyst")
        mem.load()
        case_id = mem.get("last_case_id")
    """

    def __init__(
        self,
        agent_name: str,
        base_dir: Path | None = None,
    ) -> None:
        self.agent_name = agent_name
        self._dir = (base_dir or Path.home() / ".socc" / "agents") / agent_name
        self._dir.mkdir(parents=True, exist_ok=True)
        self._state_path = self._dir / "state.json"
        self._log_path = self._dir / "mutations.jsonl"
        self._data: dict[str, Any] = {}
        self._metadata: dict[str, Any] = {}

    # ── CRUD ──────────────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._append_log("set", key, value)

    def delete(self, key: str) -> bool:
        if key in self._data:
            del self._data[key]
            self._append_log("delete", key, None)
            return True
        return False

    def keys(self) -> list[str]:
        return list(self._data.keys())

    def items(self) -> list[tuple[str, Any]]:
        return list(self._data.items())

    def clear(self) -> None:
        self._data.clear()
        self._append_log("clear", "*", None)

    # ── Persistence ───────────────────────────────────────────────────

    def save(self) -> Path:
        """Save current state to disk."""
        snapshot = MemorySnapshot(
            agent_name=self.agent_name,
            timestamp=time.time(),
            entries=self._data,
            metadata=self._metadata,
        )
        self._state_path.write_text(
            json.dumps(asdict(snapshot), indent=2, default=str),
            encoding="utf-8",
        )
        _logger.debug(
            "Saved agent memory for '%s' (%d entries)",
            self.agent_name, len(self._data),
        )
        return self._state_path

    def load(self) -> bool:
        """Load state from disk. Returns True if state existed."""
        if not self._state_path.exists():
            return False
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            self._data = data.get("entries", {})
            self._metadata = data.get("metadata", {})
            _logger.debug(
                "Loaded agent memory for '%s' (%d entries)",
                self.agent_name, len(self._data),
            )
            return True
        except (json.JSONDecodeError, OSError) as exc:
            _logger.warning("Failed to load agent memory: %s", exc)
            return False

    def snapshot(self) -> MemorySnapshot:
        """Return current state as a snapshot (without saving)."""
        return MemorySnapshot(
            agent_name=self.agent_name,
            timestamp=time.time(),
            entries=dict(self._data),
            metadata=dict(self._metadata),
        )

    # ── Internals ─────────────────────────────────────────────────────

    def _append_log(self, op: str, key: str, value: Any) -> None:
        """Append mutation to JSONL log."""
        try:
            entry = {
                "ts": time.time(),
                "op": op,
                "key": key,
            }
            if value is not None:
                entry["value"] = value
            with self._log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, default=str) + "\n")
        except OSError:
            pass  # logging failure should not break agent

    def __repr__(self) -> str:
        return f"<AgentMemory agent={self.agent_name!r} entries={len(self._data)}>"
