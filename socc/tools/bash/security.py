"""
Command security analysis for SOCC BashTool.

Classifies shell commands into risk levels and provides analysis
metadata used by the permission and sandbox systems.

Attribution: Inspired by instructkr/claude-code BashTool security modules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

__all__ = [
    "CommandAnalysis",
    "CommandRisk",
    "analyze_command",
    "redact_secrets",
    "should_use_sandbox",
]


class CommandRisk(str, Enum):
    """Risk classification for shell commands."""

    SAFE = "safe"              # Read-only / informational — always allowed
    MODERATE = "moderate"      # May have side effects — logged
    DESTRUCTIVE = "destructive"  # Modifies system state — requires approval
    BLOCKED = "blocked"        # Always rejected regardless of role


@dataclass(frozen=True, slots=True)
class CommandAnalysis:
    """Result of analysing a shell command."""

    risk: CommandRisk
    reason: str
    matched_patterns: tuple[str, ...] = ()
    sanitised_command: str | None = None
    requires_approval: bool = False


# ============================================================================
# Pattern banks
# ============================================================================

# Commands that are ALWAYS blocked — no role can run these via the harness.
_BLOCKED_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("rm -rf / (recursive root delete)",     re.compile(r"\brm\s+(?:-[^\s]*)?r[^\s]*f[^\s]*\s+/(?:\s|$)", re.I)),
    ("rm --recursive (long flag)",           re.compile(r"\brm\s+--recursive", re.I)),
    ("dd if= (raw disk write)",              re.compile(r"\bdd\s+if=", re.I)),
    ("mkfs (format filesystem)",             re.compile(r"\bmkfs\b", re.I)),
    ("fdisk (partition table edit)",          re.compile(r"\bfdisk\b", re.I)),
    ("shred (secure delete)",                re.compile(r"\bshred\b", re.I)),
    ("write to raw device",                  re.compile(r">\s*/dev/[sh]d[a-z]", re.I)),
    ("fork bomb",                            re.compile(r":\(\)\s*\{.*\|\s*:", re.I)),
    ("shutdown/reboot/halt",                 re.compile(r"\b(?:shutdown|poweroff|reboot|halt)\b", re.I)),
    ("init 0/6",                             re.compile(r"\binit\s+[06]\b", re.I)),
    ("systemctl stop/disable/mask",          re.compile(r"\bsystemctl\s+(?:stop|disable|mask)\b", re.I)),
    ("iptables flush",                       re.compile(r"\biptables\s+-F\b", re.I)),
    ("interface down",                       re.compile(r"\b(?:ifconfig|ip\s+link\s+set)\b.*\bdown\b", re.I)),
    ("kill init",                            re.compile(r"\bkill(?:all)?\s+.*\b(?:init|pid\s*1)\b", re.I)),
    ("Windows format C:",                    re.compile(r"\bformat\s+c:", re.I)),
]

# Commands that require explicit approval (destructive).
_DESTRUCTIVE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("sudo",                        re.compile(r"\bsudo\b", re.I)),
    ("su (switch user)",            re.compile(r"\bsu\s+", re.I)),
    ("passwd",                      re.compile(r"\bpasswd\b", re.I)),
    ("chmod (permission change)",   re.compile(r"\bchmod\s+[0-7]{3,4}\b", re.I)),
    ("chown (ownership change)",    re.compile(r"\bchown\b", re.I)),
    ("pipe to bash (RCE vector)",   re.compile(r"\b(?:curl|wget)\b.*\|\s*\bbash\b", re.I)),
    ("eval",                        re.compile(r"\beval\b", re.I)),
    ("rm -f (force delete)",        re.compile(r"\brm\s+-[^\s]*f", re.I)),
    ("mv to /dev/null",            re.compile(r"\bmv\s+.*\s+/dev/null\b", re.I)),
    ("crontab -r (remove all)",    re.compile(r"\bcrontab\s+-r\b", re.I)),
]

# Commands known to be safe (read-only / informational).
_SAFE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ls",          re.compile(r"^\s*ls\b")),
    ("cat",         re.compile(r"^\s*cat\b")),
    ("head",        re.compile(r"^\s*head\b")),
    ("tail",        re.compile(r"^\s*tail\b")),
    ("grep",        re.compile(r"^\s*grep\b")),
    ("rg",          re.compile(r"^\s*rg\b")),
    ("find",        re.compile(r"^\s*find\b")),
    ("wc",          re.compile(r"^\s*wc\b")),
    ("echo",        re.compile(r"^\s*echo\b")),
    ("which",       re.compile(r"^\s*which\b")),
    ("whoami",      re.compile(r"^\s*whoami\b")),
    ("pwd",         re.compile(r"^\s*pwd\b")),
    ("date",        re.compile(r"^\s*date\b")),
    ("uptime",      re.compile(r"^\s*uptime\b")),
    ("hostname",    re.compile(r"^\s*hostname\b")),
    ("uname",       re.compile(r"^\s*uname\b")),
    ("id",          re.compile(r"^\s*id\b")),
    ("env",         re.compile(r"^\s*env\b")),
    ("printenv",    re.compile(r"^\s*printenv\b")),
    ("df",          re.compile(r"^\s*df\b")),
    ("du",          re.compile(r"^\s*du\b")),
    ("free",        re.compile(r"^\s*free\b")),
    ("ps",          re.compile(r"^\s*ps\b")),
    ("top",         re.compile(r"^\s*top\s+-b")),
    ("ss",          re.compile(r"^\s*ss\b")),
    ("netstat",     re.compile(r"^\s*netstat\b")),
    ("ip addr",     re.compile(r"^\s*ip\s+(?:addr|a|route|r)\b")),
    ("file",        re.compile(r"^\s*file\b")),
    ("stat",        re.compile(r"^\s*stat\b")),
    ("sha256sum",   re.compile(r"^\s*sha256sum\b")),
    ("md5sum",      re.compile(r"^\s*md5sum\b")),
    ("strings",     re.compile(r"^\s*strings\b")),
    ("hexdump",     re.compile(r"^\s*hexdump\b")),
    ("xxd",         re.compile(r"^\s*xxd\b")),
    ("whois",       re.compile(r"^\s*whois\b")),
    ("dig",         re.compile(r"^\s*dig\b")),
    ("nslookup",    re.compile(r"^\s*nslookup\b")),
    ("host",        re.compile(r"^\s*host\b")),
    ("curl -sI",    re.compile(r"^\s*curl\s+-[^\|]*[sI]")),
    ("jq",          re.compile(r"^\s*jq\b")),
    ("yq",          re.compile(r"^\s*yq\b")),
    ("sort",        re.compile(r"^\s*sort\b")),
    ("uniq",        re.compile(r"^\s*uniq\b")),
    ("cut",         re.compile(r"^\s*cut\b")),
    ("awk",         re.compile(r"^\s*awk\b")),
    ("sed (print)", re.compile(r"^\s*sed\s+-n\b")),
    ("python -c",   re.compile(r"^\s*python3?\s+-c\b")),
]

# SOC-specific safe tools
_SAFE_PATTERNS.extend([
    ("volatility",  re.compile(r"^\s*vol(?:atility)?3?\b")),
    ("yara",        re.compile(r"^\s*yara\b")),
    ("suricata",    re.compile(r"^\s*suricata\b")),
    ("tcpdump -r",  re.compile(r"^\s*tcpdump\s+-r\b")),
    ("tshark -r",   re.compile(r"^\s*tshark\s+-r\b")),
    ("sigma",       re.compile(r"^\s*sigma\b")),
])


# ============================================================================
# Analysis
# ============================================================================


def analyze_command(command: str) -> CommandAnalysis:
    """Analyse a shell command and return its risk classification.

    Checks patterns in order: blocked → destructive → safe → moderate.
    """
    command = command.strip()

    if not command:
        return CommandAnalysis(risk=CommandRisk.SAFE, reason="Empty command")

    # 1. Check blocked
    for desc, pattern in _BLOCKED_PATTERNS:
        if pattern.search(command):
            return CommandAnalysis(
                risk=CommandRisk.BLOCKED,
                reason=f"Blocked: {desc}",
                matched_patterns=(desc,),
                requires_approval=False,
            )

    # 2. Check destructive
    matched_destructive: list[str] = []
    for desc, pattern in _DESTRUCTIVE_PATTERNS:
        if pattern.search(command):
            matched_destructive.append(desc)

    if matched_destructive:
        return CommandAnalysis(
            risk=CommandRisk.DESTRUCTIVE,
            reason=f"Requires approval: {', '.join(matched_destructive)}",
            matched_patterns=tuple(matched_destructive),
            requires_approval=True,
        )

    # 3. Check safe
    # For piped commands, analyse each segment
    segments = [s.strip() for s in command.split("|")]
    all_safe = True

    for segment in segments:
        segment_safe = False
        for _desc, pattern in _SAFE_PATTERNS:
            if pattern.search(segment):
                segment_safe = True
                break
        if not segment_safe:
            all_safe = False
            break

    if all_safe:
        return CommandAnalysis(
            risk=CommandRisk.SAFE,
            reason="All segments match safe patterns",
        )

    # 4. Default: moderate
    return CommandAnalysis(
        risk=CommandRisk.MODERATE,
        reason="Unknown command — treated as moderate risk",
    )


# ============================================================================
# Sandbox decision
# ============================================================================


def should_use_sandbox(
    command: str,
    *,
    role: str = "analyst",
    sensitive_case: bool = False,
) -> bool:
    """Decide whether a command should execute inside a sandbox.

    Returns True when:
    - The command is classified as DESTRUCTIVE.
    - The user role is ``analyst`` and the command is not SAFE.
    - The active case is marked as sensitive.
    """
    analysis = analyze_command(command)

    if analysis.risk == CommandRisk.BLOCKED:
        return False  # won't run at all

    if analysis.risk == CommandRisk.DESTRUCTIVE:
        return True

    if sensitive_case:
        return True

    if role == "analyst" and analysis.risk != CommandRisk.SAFE:
        return True

    return False


# ============================================================================
# Redaction
# ============================================================================

_REDACT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(api[_-]?key\s*[=:]\s*)[^\s\"']{8,}", re.I), r"\1[REDACTED]"),
    (re.compile(r"(password\s*[=:]\s*)[^\s\"']{4,}", re.I),     r"\1[REDACTED]"),
    (re.compile(r"(token\s*[=:]\s*)[^\s\"']{8,}", re.I),        r"\1[REDACTED]"),
    (re.compile(r"(secret\s*[=:]\s*)[^\s\"']{4,}", re.I),       r"\1[REDACTED]"),
    (re.compile(r"(Bearer\s+)[A-Za-z0-9\-._~+/]{20,}", re.I),  r"\1[REDACTED]"),
    (re.compile(r"(Authorization:\s*)[^\r\n]{10,}", re.I),       r"\1[REDACTED]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"),                            "[REDACTED-AWS-KEY]"),
    (re.compile(r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----[\s\S]*?-----END"), "[PRIVATE KEY REDACTED]"),
]


def redact_secrets(text: str) -> str:
    """Redact potential secrets (API keys, tokens, passwords) from text."""
    for pattern, replacement in _REDACT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text
