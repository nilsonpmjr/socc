from __future__ import annotations

from pathlib import Path


AGENT_ROOT = Path(__file__).resolve().parents[2] / ".agents" / "soc-copilot"


def _read_fragment(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except FileNotFoundError:
        return ""


def load_prompt_fragments() -> dict[str, str]:
    files = {
        "persona": AGENT_ROOT / "persona" / "SOUL.md",
        "rules": AGENT_ROOT / "persona" / "RULES.md",
        "memory": AGENT_ROOT / "persona" / "MEMORY.md",
    }
    return {name: _read_fragment(path) for name, path in files.items()}


def compose_system_prompt(payload: str = "", user_prompt: str = "", extra_sections: list[str] | None = None) -> str:
    fragments = load_prompt_fragments()
    sections = [value for value in fragments.values() if value]
    if user_prompt.strip():
        sections.append(f"User request:\n{user_prompt.strip()}")
    if payload.strip():
        sections.append(f"Payload:\n{payload.strip()}")
    if extra_sections:
        sections.extend(section.strip() for section in extra_sections if section and section.strip())
    return "\n\n".join(sections).strip()
