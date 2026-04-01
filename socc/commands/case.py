"""
/case command — manage incident cases.

Usage:
    /case                — list open cases
    /case list           — list all cases
    /case create <title> — create a new case
    /case load <id>      — show case details
    /case close <id>     — close a case
    /case note <id> <text> — add a note to a case
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from socc.core.harness.commands import register_command
from socc.core.harness.models import CommandArg, CommandResult, SOCCommand

__all__ = ["CaseManager", "register"]


@dataclass
class Case:
    """Security incident case."""

    id: str
    title: str
    severity: str = "medium"
    status: str = "open"
    assignee: str | None = None
    created_at: str = ""
    updated_at: str = ""
    findings: list[str] = field(default_factory=list)
    iocs: list[str] = field(default_factory=list)
    timeline: list[dict[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class CaseManager:
    """CRUD for incident cases, persisted as JSON files."""

    def __init__(self, cases_dir: Path | None = None) -> None:
        self.cases_dir = cases_dir or Path.home() / ".socc" / "cases"
        self.cases_dir.mkdir(parents=True, exist_ok=True)

    def create(self, title: str, severity: str = "medium") -> Case:
        now = datetime.now(timezone.utc).isoformat()
        case = Case(
            id=uuid.uuid4().hex[:8],
            title=title,
            severity=severity,
            created_at=now,
            updated_at=now,
        )
        self._save(case)
        return case

    def load(self, case_id: str) -> Case | None:
        path = self.cases_dir / f"{case_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return Case(**data)

    def list_cases(self, status: str | None = None) -> list[Case]:
        cases: list[Case] = []
        for path in self.cases_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                case = Case(**data)
                if status is None or case.status == status:
                    cases.append(case)
            except (json.JSONDecodeError, TypeError):
                continue
        return sorted(cases, key=lambda c: c.updated_at, reverse=True)

    def close(self, case_id: str) -> Case | None:
        case = self.load(case_id)
        if case:
            case.status = "closed"
            case.updated_at = datetime.now(timezone.utc).isoformat()
            self._save(case)
        return case

    def add_note(self, case_id: str, note: str) -> Case | None:
        case = self.load(case_id)
        if case:
            case.notes.append(note)
            case.updated_at = datetime.now(timezone.utc).isoformat()
            self._save(case)
        return case

    def add_finding(self, case_id: str, finding: str) -> Case | None:
        case = self.load(case_id)
        if case:
            case.findings.append(finding)
            case.updated_at = datetime.now(timezone.utc).isoformat()
            self._save(case)
        return case

    def add_ioc(self, case_id: str, ioc: str) -> Case | None:
        case = self.load(case_id)
        if case:
            if ioc not in case.iocs:
                case.iocs.append(ioc)
            case.updated_at = datetime.now(timezone.utc).isoformat()
            self._save(case)
        return case

    def _save(self, case: Case) -> None:
        path = self.cases_dir / f"{case.id}.json"
        path.write_text(
            json.dumps(asdict(case), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


# ── Command handler ───────────────────────────────────────────────────────

_manager: CaseManager | None = None


def _get_manager() -> CaseManager:
    global _manager
    if _manager is None:
        _manager = CaseManager()
    return _manager


def handle_case(args: list[str], context: dict[str, Any]) -> str:
    """Handle /case command."""
    mgr = _get_manager()

    if not args or args[0] == "list":
        status_filter = args[1] if len(args) > 1 else None
        cases = mgr.list_cases(status_filter)
        if not cases:
            return "No cases found."
        emoji = {"open": "🔴", "investigating": "🟡", "contained": "🟢", "closed": "⬜"}
        lines = ["# Cases", ""]
        for c in cases:
            e = emoji.get(c.status, "⚪")
            lines.append(f"{e} `{c.id}` **{c.title}** ({c.severity}) — {c.status}")
        return "\n".join(lines)

    action = args[0].lower()

    if action == "create":
        title = " ".join(args[1:]) if len(args) > 1 else "Untitled Case"
        case = mgr.create(title)
        return f"✅ Created case `{case.id}`: **{case.title}**"

    if action == "load" and len(args) > 1:
        case = mgr.load(args[1])
        if not case:
            return f"❌ Case `{args[1]}` not found."
        lines = [
            f"# Case `{case.id}`: {case.title}",
            f"**Severity:** {case.severity}  |  **Status:** {case.status}",
            f"**Created:** {case.created_at}  |  **Updated:** {case.updated_at}",
            "",
        ]
        if case.findings:
            lines.append("## Findings")
            lines.extend(f"- {f}" for f in case.findings)
            lines.append("")
        if case.iocs:
            lines.append("## IOCs")
            lines.extend(f"- `{i}`" for i in case.iocs)
            lines.append("")
        if case.notes:
            lines.append("## Notes")
            lines.extend(f"- {n}" for n in case.notes)
            lines.append("")
        if case.timeline:
            lines.append("## Timeline")
            for event in case.timeline:
                lines.append(f"- [{event.get('time', '?')}] {event.get('description', '')}")
        return "\n".join(lines)

    if action == "close" and len(args) > 1:
        case = mgr.close(args[1])
        if case:
            return f"✅ Closed case `{case.id}`"
        return f"❌ Case `{args[1]}` not found."

    if action == "note" and len(args) > 2:
        note = " ".join(args[2:])
        case = mgr.add_note(args[1], note)
        if case:
            return f"✅ Added note to case `{case.id}`"
        return f"❌ Case `{args[1]}` not found."

    return (
        "**Usage:** /case [list|create <title>|load <id>|close <id>|note <id> <text>]"
    )


# ── Registration ──────────────────────────────────────────────────────────


def register() -> None:
    """Register the /case command."""
    try:
        register_command(SOCCommand(
            name="case",
            description="Manage incident cases (create, load, close, list)",
            handler=handle_case,
            aliases=["c"],
            arguments=[
                CommandArg(name="action", required=False, default="list",
                           help="create, load, close, list, note"),
                CommandArg(name="args", required=False, help="Arguments for action"),
            ],
        ))
    except ValueError:
        pass  # already registered
