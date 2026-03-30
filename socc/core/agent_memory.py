"""Agent long-term memory for SOCC.

Persists facts, analyst preferences, and recurring patterns across sessions.
Stored in ~/.socc/memory/ as markdown files (daily notes + MEMORY.md).

Design mirrors OpenClaw's memory system:
- memory/YYYY-MM-DD.md  → daily raw notes
- MEMORY.md             → curated long-term memory (loaded in every prompt)
"""

from __future__ import annotations

import os
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _memory_home() -> Path:
    home = Path(os.getenv("SOCC_HOME", "")).expanduser() if os.getenv("SOCC_HOME", "").strip() else (Path.home() / ".socc")
    return home / "memory"


def _agent_home() -> Path:
    from soc_copilot.modules.soc_copilot_loader import _default_base_path
    return _default_base_path()


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _ensure_dir() -> Path:
    d = _memory_home()
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Long-term MEMORY.md (curated, loaded in every session prompt)
# ---------------------------------------------------------------------------

def load_long_term_memory() -> str:
    """Load MEMORY.md from agent home. Returns content or empty string."""
    # Prefer agent home (workspace), fall back to ~/.socc/memory/MEMORY.md
    for candidate in [
        _agent_home() / "MEMORY.md",
        _memory_home() / "MEMORY.md",
    ]:
        if candidate.exists():
            try:
                return candidate.read_text(encoding="utf-8").strip()
            except OSError:
                pass
    return ""


def append_long_term_memory(entry: str) -> Path:
    """Append a timestamped entry to MEMORY.md in agent home."""
    path = _agent_home() / "MEMORY.md"
    timestamp = datetime.now().strftime("%Y-%m-%d")
    line = f"\n[{timestamp}] {entry.strip()}"
    try:
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        path.write_text(existing + line + "\n", encoding="utf-8")
    except OSError:
        # fallback to ~/.socc/memory/MEMORY.md
        path = _memory_home() / "MEMORY.md"
        _ensure_dir()
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        path.write_text(existing + line + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Daily notes (raw session events)
# ---------------------------------------------------------------------------

def load_daily_notes(date: str | None = None) -> str:
    """Load daily notes for a given date (YYYY-MM-DD). Defaults to today."""
    d = date or _today()
    path = _memory_home() / f"{d}.md"
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def append_daily_note(text: str, date: str | None = None) -> Path:
    """Append a timestamped note to today's daily file."""
    _ensure_dir()
    d = date or _today()
    path = _memory_home() / f"{d}.md"
    ts = datetime.now().strftime("%H:%M")
    line = f"\n[{ts}] {text.strip()}"
    try:
        existing = path.read_text(encoding="utf-8") if path.exists() else f"# Notas — {d}"
        path.write_text(existing + line + "\n", encoding="utf-8")
    except OSError:
        pass
    return path


# ---------------------------------------------------------------------------
# Session memory index (maps session_id → summary/tags)
# ---------------------------------------------------------------------------

def _session_index_path() -> Path:
    return _memory_home() / "sessions.json"


def _load_session_index() -> dict[str, Any]:
    path = _session_index_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_session_index(index: dict[str, Any]) -> None:
    _ensure_dir()
    path = _session_index_path()
    try:
        path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def register_session(
    session_id: str,
    *,
    title: str = "",
    skill: str = "",
    tags: list[str] | None = None,
) -> None:
    """Register or update a session in the memory index."""
    index = _load_session_index()
    existing = index.get(session_id, {})
    index[session_id] = {
        **existing,
        "session_id": session_id,
        "title": title or existing.get("title", ""),
        "skill": skill or existing.get("skill", ""),
        "tags": tags or existing.get("tags", []),
        "last_seen": datetime.now().isoformat(),
        "created_at": existing.get("created_at", datetime.now().isoformat()),
    }
    _save_session_index(index)


def get_recent_sessions(limit: int = 10) -> list[dict[str, Any]]:
    """Return recent sessions sorted by last_seen desc."""
    index = _load_session_index()
    sessions = list(index.values())
    sessions.sort(key=lambda s: s.get("last_seen", ""), reverse=True)
    return sessions[:limit]


# ---------------------------------------------------------------------------
# Recent memory context for prompt injection
# ---------------------------------------------------------------------------

def load_recent_memory_context(*, max_chars: int = 1200) -> str:
    """Build a memory context string for injection into prompts.

    Combines:
    1. Long-term MEMORY.md (curated conventions/facts)
    2. Today's daily notes (recent raw context)
    """
    parts = []

    long_term = load_long_term_memory()
    if long_term:
        parts.append("## Memória de longo prazo\n" + long_term)

    today = load_daily_notes()
    if today:
        parts.append("## Notas de hoje\n" + today)

    combined = "\n\n".join(parts).strip()
    if len(combined) > max_chars:
        combined = combined[:max_chars] + "\n... [truncado]"
    return combined


# ---------------------------------------------------------------------------
# Auto-extract memory-worthy facts from a conversation turn
# ---------------------------------------------------------------------------

_MEMORY_TRIGGERS = (
    "lembre",
    "lembrar",
    "anota",
    "anotar",
    "guarda",
    "guardar",
    "salva",
    "salvar",
    "registra",
    "registrar",
    "sempre que",
    "prefiro",
    "prefere",
    "nunca",
    "sempre",
)


def should_remember(message: str) -> bool:
    """Heuristic: does this message ask the agent to remember something?"""
    lower = message.lower()
    return any(t in lower for t in _MEMORY_TRIGGERS)


def extract_memory_fact(message: str, response: str) -> str | None:
    """Try to extract a concise memory fact from a user message."""
    lower = message.lower()
    for trigger in _MEMORY_TRIGGERS:
        if trigger in lower:
            # Take everything after the trigger as the fact
            idx = lower.find(trigger)
            fact = message[idx + len(trigger):].strip().lstrip(":,; ").strip()
            if fact and len(fact) > 5:
                return fact[:240]
    return None
