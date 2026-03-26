from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    path: Path
    content: str


@dataclass(frozen=True)
class SocCopilotConfig:
    base_path: Path
    soul: str
    user: str
    agents: str
    memory: str
    tools: str
    identity: str
    skills_index: str
    schema_path: Path
    skills: Dict[str, SkillDefinition]


def _default_base_path() -> Path:
    return Path(__file__).resolve().parents[2] / ".agents" / "soc-copilot"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _load_skills(skills_dir: Path) -> Dict[str, SkillDefinition]:
    result: Dict[str, SkillDefinition] = {}
    if not skills_dir.exists():
        return result

    for path in sorted(skills_dir.glob("*.md")):
        result[path.stem] = SkillDefinition(
            name=path.stem,
            path=path,
            content=_read_text(path),
        )

    for path in sorted(skills_dir.iterdir()):
        if not path.is_dir():
            continue

        skill_file = path / "SKILL.md"
        if not skill_file.exists():
            continue

        result[path.name] = SkillDefinition(
            name=path.name,
            path=skill_file,
            content=_read_text(skill_file),
        )

    return result


def load_soc_copilot(base_path: Optional[Path] = None) -> SocCopilotConfig:
    root = base_path or _default_base_path()

    return SocCopilotConfig(
        base_path=root,
        soul=_read_text(root / "SOUL.md"),
        user=_read_text(root / "USER.md"),
        agents=_read_text(root / "AGENTS.md"),
        memory=_read_text(root / "MEMORY.md"),
        tools=_read_text(root / "TOOLS.md"),
        identity=_read_text(root / "identity.md"),
        skills_index=_read_text(root / "skills.md"),
        schema_path=root / "schemas" / "analysis_response.json",
        skills=_load_skills(root / "skills"),
    )


def choose_skill(
    user_input: str,
    artifact_type: Optional[str] = None,
    available_skills: Optional[Iterable[str]] = None,
) -> str:
    text = user_input.lower()
    allowed = set(available_skills or [])

    def is_allowed(name: str) -> bool:
        return not allowed or name in allowed

    if artifact_type:
        normalized = artifact_type.strip().lower()
        mapping = {
            "url": "suspicious-url",
            "domain": "suspicious-url",
            "email": "phishing-analysis",
            "phishing": "phishing-analysis",
            "malware": "malware-behavior",
            "process": "malware-behavior",
            "payload": "payload-triage",
        }
        skill_name = mapping.get(normalized)
        if skill_name and is_allowed(skill_name):
            return skill_name

    if re.search(r"https?://|www\\.|\\b[a-z0-9-]+\\.[a-z]{2,}\\b", text) and is_allowed(
        "suspicious-url"
    ):
        return "suspicious-url"

    phishing_keywords = (
        "subject:",
        "reply-to",
        "from:",
        "to:",
        "attachment",
        "invoice",
        "email",
        "mail",
        "phishing",
    )
    if any(keyword in text for keyword in phishing_keywords) and is_allowed(
        "phishing-analysis"
    ):
        return "phishing-analysis"

    malware_keywords = (
        "powershell",
        "cmd.exe",
        "rundll32",
        "regsvr32",
        "schtasks",
        "registry",
        "run key",
        "process",
        "dll",
        "persistence",
    )
    if any(keyword in text for keyword in malware_keywords) and is_allowed(
        "malware-behavior"
    ):
        return "malware-behavior"

    return "payload-triage"


def build_prompt_context(
    user_input: str,
    artifact_type: Optional[str] = None,
    session_context: Optional[str] = None,
    selected_skill: Optional[str] = None,
    base_path: Optional[Path] = None,
) -> Dict[str, str]:
    config = load_soc_copilot(base_path=base_path)
    skill_name = selected_skill or choose_skill(
        user_input=user_input,
        artifact_type=artifact_type,
        available_skills=config.skills.keys(),
    )
    skill = config.skills[skill_name]

    return {
        "identity": config.identity,
        "soul": config.soul,
        "user": config.user,
        "agents": config.agents,
        "memory": config.memory,
        "tools": config.tools,
        "skills_index": config.skills_index,
        "selected_skill": skill_name,
        "skill_content": skill.content,
        "schema_path": str(config.schema_path),
        "session_context": (session_context or "").strip(),
        "user_input": user_input.strip(),
    }
