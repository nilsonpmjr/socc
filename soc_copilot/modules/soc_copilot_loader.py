from __future__ import annotations

import os
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
    references: Dict[str, str]
    skills: Dict[str, SkillDefinition]


_REQUIRED_AGENT_FILES = (
    "SOUL.md",
    "USER.md",
    "AGENTS.md",
    "MEMORY.md",
    "TOOLS.md",
    "identity.md",
    "skills.md",
)

_URL_PATTERN = re.compile(r"https?://|www\\.|\\b[a-z0-9-]+\\.[a-z]{2,}\\b")
_CVE_PATTERN = re.compile(r"\\bcve-\\d{4}-\\d{4,7}\\b", re.IGNORECASE)
_HASH_PATTERN = re.compile(r"\\b(?:[a-f0-9]{32}|[a-f0-9]{40}|[a-f0-9]{64}|[a-f0-9]{128})\\b", re.IGNORECASE)
_STRUCTURED_PAYLOAD_PATTERN = re.compile(
    r"(?:\\b\\w+[.-]?\\w*\\s*=\\s*[^\\s]+)|(?:\\b\\w+[.-]?\\w*\\s*:\\s*[^\\s])"
)


def _is_agent_root(path: Path) -> bool:
    return all((path / filename).exists() for filename in _REQUIRED_AGENT_FILES)


def _agent_search_roots() -> list[tuple[str, Path]]:
    repo_root = Path(__file__).resolve().parents[2]
    runtime_root = Path(os.getenv("SOCC_HOME", "")).expanduser() if os.getenv("SOCC_HOME", "").strip() else (Path.home().expanduser() / ".socc")
    return [
        ("runtime_workspace", runtime_root / "workspace"),
        ("repo_agents", repo_root / ".agents"),
    ]


def _default_base_path() -> Path:
    explicit = os.getenv("SOCC_AGENT_HOME", "").strip()
    candidates = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    candidates.append(Path.home().expanduser() / ".socc" / "workspace" / "soc-copilot")
    candidates.append(Path(__file__).resolve().parents[2] / ".agents" / "soc-copilot")

    for candidate in candidates:
        if _is_agent_root(candidate):
            return candidate

    return candidates[-1]


def _repo_agent_base_path() -> Path:
    return Path(__file__).resolve().parents[2] / ".agents" / "soc-copilot"


def list_available_agents() -> list[dict[str, str | int | bool]]:
    selected = _default_base_path().expanduser()
    entries: list[dict[str, str | int | bool]] = []
    seen: set[str] = set()

    explicit = os.getenv("SOCC_AGENT_HOME", "").strip()
    if explicit:
        explicit_path = Path(explicit).expanduser()
        if _is_agent_root(explicit_path):
            resolved = str(explicit_path.resolve())
            seen.add(resolved)
            entries.append(
                {
                    "id": explicit_path.name or "agent",
                    "label": explicit_path.name or explicit_path.as_posix(),
                    "path": str(explicit_path),
                    "source": "explicit_env",
                    "selected": explicit_path.resolve() == selected.resolve(),
                    "skills_count": len(_load_skills(explicit_path / "skills")),
                    "references_count": len(_load_references(explicit_path / "references")),
                }
            )

    for source, root in _agent_search_roots():
        if not root.exists():
            continue
        for candidate in sorted(path for path in root.iterdir() if path.is_dir()):
            if not _is_agent_root(candidate):
                continue
            resolved = str(candidate.resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            entries.append(
                {
                    "id": candidate.name,
                    "label": candidate.name.replace("-", " ").strip() or candidate.name,
                    "path": str(candidate),
                    "source": source,
                    "selected": candidate.resolve() == selected.resolve(),
                    "skills_count": len(_load_skills(candidate / "skills")),
                    "references_count": len(_load_references(candidate / "references")),
                }
            )

    return entries


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


def _load_references(references_dir: Path) -> Dict[str, str]:
    result: Dict[str, str] = {}
    if not references_dir.exists():
        return result

    for path in sorted(references_dir.glob("*.md")):
        result[path.stem] = _read_text(path)

    return result


def load_soc_copilot(base_path: Optional[Path] = None) -> SocCopilotConfig:
    root = base_path or _default_base_path()
    repo_root = _repo_agent_base_path()
    references = _load_references(root / "references")
    skills = _load_skills(root / "skills")

    if root.resolve() != repo_root.resolve() and _is_agent_root(repo_root):
        repo_references = _load_references(repo_root / "references")
        repo_skills = _load_skills(repo_root / "skills")
        references = {**repo_references, **references}
        skills = {**repo_skills, **skills}

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
        references=references,
        skills=skills,
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

    def contains_any(keywords: tuple[str, ...]) -> bool:
        return any(keyword in text for keyword in keywords)

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

    if _URL_PATTERN.search(text) and is_allowed(
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
    if contains_any(phishing_keywords) and is_allowed(
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
    if contains_any(malware_keywords) and is_allowed(
        "malware-behavior"
    ):
        return "malware-behavior"

    payload_keywords = (
        "srcip=",
        "dstip=",
        "action=",
        "devname=",
        "logid=",
        "eventid=",
        "alert",
        "payload",
        "raw log",
        "json",
        "cef:",
        "leef:",
        "syslog",
    )
    payload_field_count = len(_STRUCTURED_PAYLOAD_PATTERN.findall(user_input or ""))
    if (
        contains_any(payload_keywords)
        or payload_field_count >= 4
    ) and is_allowed("payload-triage"):
        return "payload-triage"

    generalist_keywords = (
        "hash",
        "sha1",
        "sha256",
        "sha512",
        "md5",
        "ioc",
        "iocs",
        "ttp",
        "ttps",
        "mitre",
        "att&ck",
        "sigma",
        "yara",
        "cve",
        "comportamento",
        "behavior",
        "detecção",
        "deteccao",
        "detecção",
        "hunting",
        "hunt",
        "investigar",
        "investigacao",
        "correlacao",
        "correlação",
        "prioridade",
        "impacto",
        "isso é normal",
        "isso e normal",
        "o que significa",
        "como investigar",
        "qual impacto",
    )
    if (
        _CVE_PATTERN.search(user_input or "")
        or _HASH_PATTERN.search(user_input or "")
        or contains_any(generalist_keywords)
    ) and is_allowed("soc-generalist"):
        return "soc-generalist"

    if is_allowed("soc-generalist"):
        return "soc-generalist"
    return "payload-triage"


def build_prompt_context(
    user_input: str,
    artifact_type: Optional[str] = None,
    session_context: Optional[str] = None,
    selected_skill: Optional[str] = None,
    knowledge_context: Optional[str] = None,
    knowledge_sources: Optional[str] = None,
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
        "references_index": ", ".join(sorted(config.references.keys())),
        "evidence_rules": config.references.get("evidence-rules", ""),
        "ioc_extraction": config.references.get("ioc-extraction", ""),
        "security_json_patterns": config.references.get("security-json-patterns", ""),
        "telemetry_investigation_patterns": config.references.get("telemetry-investigation-patterns", ""),
        "mitre_guidance": config.references.get("mitre-guidance", ""),
        "output_contract": config.references.get("output-contract", ""),
        "selected_skill": skill_name,
        "skill_content": skill.content,
        "schema_path": str(config.schema_path),
        "session_context": (session_context or "").strip(),
        "knowledge_context": (knowledge_context or "").strip(),
        "knowledge_sources": (knowledge_sources or "").strip(),
        "user_input": user_input.strip(),
    }
