from __future__ import annotations

import hashlib
import os
import re

_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.\w+\b")
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_URL_RE = re.compile(r"https?://[^\s]+")
_HASH_RE = re.compile(r"\b[a-fA-F0-9]{32}\b|\b[a-fA-F0-9]{40}\b|\b[a-fA-F0-9]{64}\b")
_SECRET_ASSIGN_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|authorization|bearer|password)\b\s*[:=]\s*([^\s,;]+)"
)


def log_redaction_enabled() -> bool:
    return os.getenv("SOCC_LOG_REDACTION_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}


def prompt_audit_enabled() -> bool:
    return os.getenv("SOCC_PROMPT_AUDIT_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def prompt_preview_chars() -> int:
    try:
        return max(40, int(os.getenv("SOCC_PROMPT_PREVIEW_CHARS", "160")))
    except ValueError:
        return 160


def text_fingerprint(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8", errors="replace")).hexdigest()[:16]


def redact_sensitive_text(text: str, limit: int | None = None) -> str:
    content = str(text or "")
    content = _EMAIL_RE.sub("[redacted-email]", content)
    content = _IPV4_RE.sub("[redacted-ip]", content)
    content = _URL_RE.sub("[redacted-url]", content)
    content = _HASH_RE.sub("[redacted-hash]", content)
    content = _SECRET_ASSIGN_RE.sub(lambda match: f"{match.group(1)}=[redacted-secret]", content)
    if limit is not None and limit >= 0 and len(content) > limit:
        return content[:limit].rstrip() + "..."
    return content


def prompt_preview(text: str) -> dict[str, str | int]:
    preview_chars = prompt_preview_chars()
    return {
        "fingerprint": text_fingerprint(text),
        "chars": len(text or ""),
        "preview": redact_sensitive_text(text, limit=preview_chars),
    }
