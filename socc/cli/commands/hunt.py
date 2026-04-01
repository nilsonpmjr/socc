"""
/hunt command — interactive threat hunting.

Usage:
    /hunt start <hypothesis> — start a new hunt session
    /hunt finding <text>     — log a finding in the active hunt
    /hunt status             — show current hunt status
    /hunt stop               — end the current hunt
    /hunt list               — list past hunts
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from socc.core.harness.commands import register_command
from socc.core.harness.models import CommandArg, SOCCommand

__all__ = ["HuntSession", "register"]


@dataclass
class HuntSession:
    """A threat hunting session."""

    id: str
    hypothesis: str
    status: str = "active"  # active, completed, abandoned
    started_at: str = ""
    ended_at: str | None = None
    findings: list[str] = field(default_factory=list)
    iocs_discovered: list[str] = field(default_factory=list)
    data_sources: list[str] = field(default_factory=list)
    detection_gaps: list[str] = field(default_factory=list)
    confidence: str = "low"  # low, medium, high


class HuntManager:
    """Manage threat hunting sessions."""

    def __init__(self, hunts_dir: Path | None = None) -> None:
        self.hunts_dir = hunts_dir or Path.home() / ".socc" / "hunts"
        self.hunts_dir.mkdir(parents=True, exist_ok=True)
        self._active: HuntSession | None = None

    def start(self, hypothesis: str) -> HuntSession:
        if self._active and self._active.status == "active":
            self._active.status = "abandoned"
            self._save(self._active)

        session = HuntSession(
            id=uuid.uuid4().hex[:8],
            hypothesis=hypothesis,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        self._active = session
        self._save(session)
        return session

    def add_finding(self, text: str) -> HuntSession | None:
        if not self._active or self._active.status != "active":
            return None
        self._active.findings.append(text)
        self._save(self._active)
        return self._active

    def stop(self) -> HuntSession | None:
        if not self._active or self._active.status != "active":
            return None
        self._active.status = "completed"
        self._active.ended_at = datetime.now(timezone.utc).isoformat()
        self._save(self._active)
        session = self._active
        self._active = None
        return session

    def get_active(self) -> HuntSession | None:
        return self._active if self._active and self._active.status == "active" else None

    def list_hunts(self, limit: int = 20) -> list[HuntSession]:
        hunts: list[HuntSession] = []
        for path in self.hunts_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                hunts.append(HuntSession(**data))
            except (json.JSONDecodeError, TypeError):
                continue
        hunts.sort(key=lambda h: h.started_at, reverse=True)
        return hunts[:limit]

    def _save(self, session: HuntSession) -> None:
        path = self.hunts_dir / f"{session.id}.json"
        path.write_text(
            json.dumps(asdict(session), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


# ── Command handler ───────────────────────────────────────────────────────

_manager: HuntManager | None = None


def _get_manager() -> HuntManager:
    global _manager
    if _manager is None:
        _manager = HuntManager()
    return _manager


def handle_hunt(args: list[str], context: dict[str, Any]) -> str:
    """Handle /hunt command."""
    mgr = _get_manager()

    if not args or args[0] == "status":
        active = mgr.get_active()
        if not active:
            return "No active hunt. Use `/hunt start <hypothesis>` to begin."
        lines = [
            f"# 🔍 Active Hunt `{active.id}`",
            f"**Hypothesis:** {active.hypothesis}",
            f"**Started:** {active.started_at}",
            f"**Findings:** {len(active.findings)}",
        ]
        if active.findings:
            lines.append("")
            for i, f in enumerate(active.findings, 1):
                lines.append(f"  {i}. {f}")
        return "\n".join(lines)

    action = args[0].lower()

    if action == "start":
        hypothesis = " ".join(args[1:]) if len(args) > 1 else "Unnamed hypothesis"
        session = mgr.start(hypothesis)
        return (
            f"🔍 Hunt `{session.id}` started\n"
            f"**Hypothesis:** {session.hypothesis}\n\n"
            "Use `/hunt finding <text>` to log findings.\n"
            "Use `/hunt stop` when done."
        )

    if action == "finding":
        text = " ".join(args[1:]) if len(args) > 1 else ""
        if not text:
            return "Usage: `/hunt finding <description>`"
        session = mgr.add_finding(text)
        if session:
            return f"✅ Finding #{len(session.findings)} logged in hunt `{session.id}`"
        return "❌ No active hunt. Start one with `/hunt start <hypothesis>`"

    if action == "stop":
        session = mgr.stop()
        if session:
            return (
                f"✅ Hunt `{session.id}` completed\n"
                f"**Findings:** {len(session.findings)}\n"
                f"**Duration:** {session.started_at} → {session.ended_at}"
            )
        return "❌ No active hunt to stop."

    if action == "list":
        hunts = mgr.list_hunts()
        if not hunts:
            return "No hunts recorded."
        emoji = {"active": "🔍", "completed": "✅", "abandoned": "⬜"}
        lines = ["# Hunt Sessions", ""]
        for h in hunts:
            e = emoji.get(h.status, "⚪")
            lines.append(f"{e} `{h.id}` {h.hypothesis[:50]} ({len(h.findings)} findings)")
        return "\n".join(lines)

    return "**Usage:** /hunt [start <hypothesis>|finding <text>|status|stop|list]"


# ── Registration ──────────────────────────────────────────────────────────


def register() -> None:
    """Register the /hunt command."""
    try:
        register_command(SOCCommand(
            name="hunt",
            description="Start or manage a threat hunting session",
            handler=handle_hunt,
            aliases=["h"],
            arguments=[
                CommandArg(name="action", required=False, default="status",
                           help="start, finding, status, stop, list"),
                CommandArg(name="args", required=False, help="Arguments for action"),
            ],
        ))
    except ValueError:
        pass  # already registered
