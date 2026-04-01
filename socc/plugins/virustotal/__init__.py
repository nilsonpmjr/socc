"""VirusTotal plugin for SOCC.

Provides three tools:
- ``vt_lookup_hash``   — look up a file hash (MD5/SHA1/SHA256)
- ``vt_lookup_url``    — look up a URL
- ``vt_lookup_domain`` — look up a domain

All tools require ``VT_API_KEY`` environment variable.

Rate limiting: VirusTotal public API allows 4 requests/minute.
This plugin adds a simple token-bucket rate limiter.

Attribution: VirusTotal Public API v3 (https://docs.virustotal.com)
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

from socc.core.tools_registry import (
    ParamSpec,
    RiskLevel,
    ToolCategory,
    ToolResult,
    ToolSpec,
    register_tool,
    unregister_tool,
)
from socc.plugins import PluginManifest, SOCCPlugin

__all__ = ["PLUGIN", "VirusTotalPlugin"]

_logger = logging.getLogger(__name__)
_MANIFEST = PluginManifest.from_file(Path(__file__).parent / "plugin.json")

# ---------------------------------------------------------------------------
# Rate limiter (4 req / 60s for free tier)
# ---------------------------------------------------------------------------

_RATE_LOCK = threading.Lock()
_REQUEST_TIMES: list[float] = []
_MAX_REQUESTS = 4
_WINDOW_SECONDS = 60.0


def _rate_limit() -> None:
    """Block until a VT API call is within the rate limit."""
    with _RATE_LOCK:
        now = time.monotonic()
        # Purge timestamps outside the window
        cutoff = now - _WINDOW_SECONDS
        while _REQUEST_TIMES and _REQUEST_TIMES[0] < cutoff:
            _REQUEST_TIMES.pop(0)

        if len(_REQUEST_TIMES) >= _MAX_REQUESTS:
            wait_for = _WINDOW_SECONDS - (now - _REQUEST_TIMES[0]) + 0.1
            _logger.debug("VT rate limit — sleeping %.1fs", wait_for)
            time.sleep(wait_for)

        _REQUEST_TIMES.append(time.monotonic())


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

_VT_BASE = "https://www.virustotal.com/api/v3"


def _get_api_key() -> str:
    key = os.environ.get("VT_API_KEY", "")
    if not key:
        raise RuntimeError(
            "VT_API_KEY environment variable not set. "
            "Get a free key at https://www.virustotal.com"
        )
    return key


def _vt_get(endpoint: str) -> dict[str, Any]:
    """Make a GET request to the VT API and return parsed JSON."""
    try:
        import urllib.request

        _rate_limit()
        url = f"{_VT_BASE}/{endpoint}"
        req = urllib.request.Request(
            url,
            headers={
                "x-apikey": _get_api_key(),
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        raise RuntimeError(f"VT API request failed: {type(exc).__name__}: {exc}") from exc


def _parse_stats(attrs: dict[str, Any]) -> dict[str, Any]:
    """Extract last_analysis_stats from VT attributes."""
    stats = attrs.get("last_analysis_stats", {})
    total = sum(stats.values()) if stats else 0
    malicious = stats.get("malicious", 0)
    return {
        "malicious": malicious,
        "suspicious": stats.get("suspicious", 0),
        "undetected": stats.get("undetected", 0),
        "harmless": stats.get("harmless", 0),
        "total_engines": total,
        "detection_ratio": f"{malicious}/{total}" if total else "0/0",
    }


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

_HASH_RE = re.compile(r"^[0-9a-fA-F]{32,64}$")


def vt_lookup_hash(hash_value: str) -> dict[str, Any]:
    """Look up a file hash on VirusTotal.

    Args:
        hash_value: MD5 (32 chars), SHA1 (40 chars) or SHA256 (64 chars) hash.

    Returns:
        Dict with detection stats, file type, names, and permalink.
    """
    hash_value = hash_value.strip()
    if not _HASH_RE.match(hash_value):
        return {
            "error": f"Invalid hash format: {hash_value!r}. Expected MD5/SHA1/SHA256.",
            "found": False,
        }

    try:
        data = _vt_get(f"files/{hash_value}")
        attrs = data.get("data", {}).get("attributes", {})
        stats = _parse_stats(attrs)

        return {
            "found": True,
            "hash": hash_value,
            "type": attrs.get("type_description", attrs.get("magic", "unknown")),
            "size": attrs.get("size"),
            "names": attrs.get("names", [])[:10],
            "first_seen": attrs.get("first_submission_date"),
            "last_seen": attrs.get("last_analysis_date"),
            "permalink": f"https://www.virustotal.com/gui/file/{hash_value}",
            **stats,
        }
    except RuntimeError as exc:
        if "404" in str(exc):
            return {"found": False, "hash": hash_value, "message": "Hash not found in VT"}
        return {"found": False, "hash": hash_value, "error": str(exc)}


def vt_lookup_url(url: str) -> dict[str, Any]:
    """Look up a URL on VirusTotal.

    Args:
        url: URL to check (will be base64url-encoded for the API call).

    Returns:
        Dict with detection stats and categories.
    """
    import base64

    url = url.strip()
    url_id = base64.urlsafe_b64encode(url.encode()).rstrip(b"=").decode()

    try:
        data = _vt_get(f"urls/{url_id}")
        attrs = data.get("data", {}).get("attributes", {})
        stats = _parse_stats(attrs)

        return {
            "found": True,
            "url": url,
            "categories": attrs.get("categories", {}),
            "last_analysis_date": attrs.get("last_analysis_date"),
            "times_submitted": attrs.get("times_submitted", 0),
            "permalink": f"https://www.virustotal.com/gui/url/{url_id}",
            **stats,
        }
    except RuntimeError as exc:
        if "404" in str(exc):
            return {"found": False, "url": url, "message": "URL not found in VT"}
        return {"found": False, "url": url, "error": str(exc)}


def vt_lookup_domain(domain: str) -> dict[str, Any]:
    """Look up a domain on VirusTotal.

    Args:
        domain: Domain name to check (e.g. ``evil.example.com``).

    Returns:
        Dict with detection stats, categories, WHOIS, and DNS records.
    """
    domain = domain.strip().lower().lstrip(".")

    try:
        data = _vt_get(f"domains/{domain}")
        attrs = data.get("data", {}).get("attributes", {})
        stats = _parse_stats(attrs)

        return {
            "found": True,
            "domain": domain,
            "registrar": attrs.get("registrar"),
            "creation_date": attrs.get("creation_date"),
            "reputation": attrs.get("reputation", 0),
            "categories": attrs.get("categories", {}),
            "whois_summary": (attrs.get("whois") or "")[:500],
            "last_dns_records": attrs.get("last_dns_records", [])[:5],
            "permalink": f"https://www.virustotal.com/gui/domain/{domain}",
            **stats,
        }
    except RuntimeError as exc:
        if "404" in str(exc):
            return {"found": False, "domain": domain, "message": "Domain not found in VT"}
        return {"found": False, "domain": domain, "error": str(exc)}


# ---------------------------------------------------------------------------
# Plugin class
# ---------------------------------------------------------------------------


class VirusTotalPlugin(SOCCPlugin):
    """VirusTotal integration plugin."""

    manifest = _MANIFEST

    def register(self) -> None:
        """Register VT tools in the global tool registry."""
        _specs = [
            ToolSpec(
                name="vt_lookup_hash",
                description=(
                    "Look up a file hash (MD5/SHA1/SHA256) on VirusTotal. "
                    "Returns detection ratio, file type, and AV engine results."
                ),
                parameters={
                    "hash_value": ParamSpec(
                        type="string",
                        description="MD5, SHA1, or SHA256 hash to look up",
                        required=True,
                    ),
                },
                handler=vt_lookup_hash,
                category=ToolCategory.THREAT_INTEL,
                risk_level=RiskLevel.LOW,
                tags=["virustotal", "hash", "malware", "ioc", "vt"],
                example='vt_lookup_hash(hash_value="d41d8cd98f00b204e9800998ecf8427e")',
            ),
            ToolSpec(
                name="vt_lookup_url",
                description=(
                    "Look up a URL on VirusTotal. "
                    "Returns detection ratio and category classifications."
                ),
                parameters={
                    "url": ParamSpec(
                        type="string",
                        description="URL to look up",
                        required=True,
                    ),
                },
                handler=vt_lookup_url,
                category=ToolCategory.THREAT_INTEL,
                risk_level=RiskLevel.LOW,
                tags=["virustotal", "url", "phishing", "ioc", "vt"],
                example='vt_lookup_url(url="https://evil.example.com/payload")',
            ),
            ToolSpec(
                name="vt_lookup_domain",
                description=(
                    "Look up a domain on VirusTotal. "
                    "Returns detection ratio, WHOIS, DNS records, and reputation."
                ),
                parameters={
                    "domain": ParamSpec(
                        type="string",
                        description="Domain name to look up",
                        required=True,
                    ),
                },
                handler=vt_lookup_domain,
                category=ToolCategory.THREAT_INTEL,
                risk_level=RiskLevel.LOW,
                tags=["virustotal", "domain", "dns", "ioc", "vt"],
                example='vt_lookup_domain(domain="evil.example.com")',
            ),
        ]

        for spec in _specs:
            # Unregister first so re-registration is idempotent
            unregister_tool(spec.name)
            register_tool(spec)

        _logger.info("VirusTotal plugin registered: %d tools", len(_specs))


PLUGIN = VirusTotalPlugin()
