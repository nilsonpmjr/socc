"""MISP plugin for SOCC.

Provides three tools:
- ``misp_search``    — search events/attributes by value or type
- ``misp_add_event`` — create a new MISP event
- ``misp_add_ioc``   — add an attribute (IOC) to an existing event

Requires:
    MISP_URL     — base URL of your MISP instance (e.g. https://misp.corp)
    MISP_API_KEY — automation key from MISP user profile

Attribution: MISP REST API (https://www.misp-project.org/openapi/)
"""

from __future__ import annotations

import json
import logging
import os
import ssl
from pathlib import Path
from typing import Any

from socc.core.tools_registry import (
    ParamSpec,
    RiskLevel,
    ToolCategory,
    ToolSpec,
    register_tool,
    unregister_tool,
)
from socc.plugins import PluginManifest, SOCCPlugin

__all__ = ["PLUGIN", "MISPPlugin"]

_logger = logging.getLogger(__name__)
_MANIFEST = PluginManifest.from_file(Path(__file__).parent / "plugin.json")

# MISP attribute types — subset relevant to SOC work
MISP_ATTRIBUTE_TYPES = {
    "ip-src", "ip-dst", "domain", "hostname", "url",
    "md5", "sha1", "sha256", "filename", "email-src",
    "email-subject", "regkey", "mutex", "user-agent",
    "yara", "sigma", "snort", "pattern-in-file",
}


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _get_config() -> tuple[str, str]:
    url = os.environ.get("MISP_URL", "").rstrip("/")
    key = os.environ.get("MISP_API_KEY", "")
    if not url:
        raise RuntimeError("MISP_URL environment variable not set")
    if not key:
        raise RuntimeError("MISP_API_KEY environment variable not set")
    return url, key


def _misp_request(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Make an authenticated MISP API request."""
    import urllib.request

    base_url, api_key = _get_config()
    url = f"{base_url}/{path.lstrip('/')}"
    data = json.dumps(body).encode() if body else None

    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )

    # Allow self-signed certs on internal MISP instances
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        raise RuntimeError(f"MISP API error: {type(exc).__name__}: {exc}") from exc


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

def misp_search(
    value: str,
    type_attribute: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Search MISP for events or attributes matching *value*.

    Args:
        value: The value to search for (IP, domain, hash, etc.).
        type_attribute: Optional MISP attribute type filter
            (e.g. ``"ip-dst"``, ``"domain"``, ``"sha256"``).
        limit: Maximum number of results to return (default: 20, max: 100).

    Returns:
        Dict with ``attributes`` list and ``total_count``.
    """
    limit = min(int(limit), 100)
    payload: dict[str, Any] = {
        "returnFormat": "json",
        "value": value,
        "limit": limit,
        "page": 1,
    }
    if type_attribute:
        if type_attribute not in MISP_ATTRIBUTE_TYPES:
            return {
                "error": f"Unknown attribute type: {type_attribute!r}. "
                         f"Valid types: {', '.join(sorted(MISP_ATTRIBUTE_TYPES))}",
            }
        payload["type"] = type_attribute

    try:
        data = _misp_request("POST", "/attributes/restSearch", payload)
        attrs = data.get("response", {}).get("Attribute", [])
        simplified = [
            {
                "id": a.get("id"),
                "event_id": a.get("event_id"),
                "type": a.get("type"),
                "value": a.get("value"),
                "category": a.get("category"),
                "comment": a.get("comment", ""),
                "timestamp": a.get("timestamp"),
                "to_ids": a.get("to_ids", False),
            }
            for a in attrs
        ]
        return {
            "query": value,
            "type_filter": type_attribute,
            "total_count": len(simplified),
            "attributes": simplified,
        }
    except RuntimeError as exc:
        return {"error": str(exc), "query": value}


def misp_add_event(
    title: str,
    threat_level: int = 2,
    distribution: int = 0,
    analysis: int = 0,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Create a new MISP event.

    Args:
        title: Event info / title string.
        threat_level: 1=High, 2=Medium, 3=Low, 4=Undefined (default: 2).
        distribution: 0=Org only, 1=Community, 2=Connected communities,
            3=All (default: 0).
        analysis: 0=Initial, 1=Ongoing, 2=Completed (default: 0).
        tags: Optional list of tag strings to attach to the event.

    Returns:
        Dict with the created event id and permalink.
    """
    if threat_level not in (1, 2, 3, 4):
        return {"error": f"Invalid threat_level {threat_level}. Must be 1-4."}
    if distribution not in (0, 1, 2, 3):
        return {"error": f"Invalid distribution {distribution}. Must be 0-3."}

    payload: dict[str, Any] = {
        "Event": {
            "info": title,
            "threat_level_id": threat_level,
            "distribution": distribution,
            "analysis": analysis,
        }
    }

    try:
        data = _misp_request("POST", "/events/add", payload)
        event = data.get("Event", {})
        event_id = event.get("id")
        base_url, _ = _get_config()

        # Optionally add tags
        if tags and event_id:
            for tag in tags:
                try:
                    _misp_request(
                        "POST",
                        f"/events/addTag/{event_id}/{tag}",
                    )
                except RuntimeError:
                    _logger.warning("Could not add tag '%s' to event %s", tag, event_id)

        return {
            "created": True,
            "event_id": event_id,
            "title": title,
            "permalink": f"{base_url}/events/view/{event_id}" if event_id else None,
        }
    except RuntimeError as exc:
        return {"created": False, "error": str(exc)}


def misp_add_ioc(
    event_id: str | int,
    ioc_type: str,
    value: str,
    comment: str = "",
    to_ids: bool = True,
    category: str = "Network activity",
) -> dict[str, Any]:
    """Add an attribute (IOC) to an existing MISP event.

    Args:
        event_id: Target event ID.
        ioc_type: MISP attribute type (e.g. ``"ip-dst"``, ``"sha256"``).
        value: The IOC value.
        comment: Optional analyst comment.
        to_ids: If True, this attribute should trigger IDS (default: True).
        category: MISP attribute category (default: ``"Network activity"``).

    Returns:
        Dict with the created attribute id.
    """
    if ioc_type not in MISP_ATTRIBUTE_TYPES:
        return {
            "error": f"Unknown IOC type: {ioc_type!r}. "
                     f"Valid types: {', '.join(sorted(MISP_ATTRIBUTE_TYPES))}",
        }

    payload = {
        "Attribute": {
            "event_id": str(event_id),
            "type": ioc_type,
            "value": value,
            "comment": comment,
            "to_ids": to_ids,
            "category": category,
        }
    }

    try:
        data = _misp_request("POST", "/attributes/add", payload)
        attr = data.get("Attribute", {})
        base_url, _ = _get_config()
        return {
            "created": True,
            "attribute_id": attr.get("id"),
            "event_id": str(event_id),
            "type": ioc_type,
            "value": value,
            "permalink": f"{base_url}/events/view/{event_id}",
        }
    except RuntimeError as exc:
        return {"created": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Plugin class
# ---------------------------------------------------------------------------

class MISPPlugin(SOCCPlugin):
    """MISP threat intelligence platform plugin."""

    manifest = _MANIFEST

    def register(self) -> None:
        _specs = [
            ToolSpec(
                name="misp_search",
                description=(
                    "Search MISP for events/attributes matching a value. "
                    "Supports filtering by attribute type (ip-dst, domain, sha256, etc.)."
                ),
                parameters={
                    "value": ParamSpec(
                        type="string",
                        description="Value to search for (IP, hash, domain, URL, etc.)",
                        required=True,
                    ),
                    "type_attribute": ParamSpec(
                        type="string",
                        description="MISP attribute type filter (optional)",
                        required=False,
                        default=None,
                    ),
                    "limit": ParamSpec(
                        type="integer",
                        description="Maximum results to return (default: 20, max: 100)",
                        required=False,
                        default=20,
                    ),
                },
                handler=misp_search,
                category=ToolCategory.THREAT_INTEL,
                risk_level=RiskLevel.LOW,
                tags=["misp", "threat-intel", "ioc", "search"],
                example='misp_search(value="192.168.1.1", type_attribute="ip-dst")',
            ),
            ToolSpec(
                name="misp_add_event",
                description=(
                    "Create a new MISP event. "
                    "Returns the event ID and a permalink."
                ),
                parameters={
                    "title": ParamSpec(
                        type="string",
                        description="Event title / info string",
                        required=True,
                    ),
                    "threat_level": ParamSpec(
                        type="integer",
                        description="1=High, 2=Medium, 3=Low, 4=Undefined",
                        required=False,
                        default=2,
                    ),
                    "distribution": ParamSpec(
                        type="integer",
                        description="0=Org only, 1=Community, 2=Connected, 3=All",
                        required=False,
                        default=0,
                    ),
                    "analysis": ParamSpec(
                        type="integer",
                        description="0=Initial, 1=Ongoing, 2=Completed",
                        required=False,
                        default=0,
                    ),
                    "tags": ParamSpec(
                        type="array",
                        description="List of tag strings to attach",
                        required=False,
                        default=None,
                    ),
                },
                handler=misp_add_event,
                category=ToolCategory.THREAT_INTEL,
                risk_level=RiskLevel.MEDIUM,
                tags=["misp", "event", "create", "threat-intel"],
                example='misp_add_event(title="Phishing campaign 2026-04-01", threat_level=2)',
            ),
            ToolSpec(
                name="misp_add_ioc",
                description=(
                    "Add an attribute (IOC) to an existing MISP event. "
                    "Supports all standard MISP attribute types."
                ),
                parameters={
                    "event_id": ParamSpec(
                        type="string",
                        description="Target MISP event ID",
                        required=True,
                    ),
                    "ioc_type": ParamSpec(
                        type="string",
                        description=(
                            "MISP attribute type: ip-dst, ip-src, domain, "
                            "sha256, md5, url, email-src, etc."
                        ),
                        required=True,
                    ),
                    "value": ParamSpec(
                        type="string",
                        description="The IOC value",
                        required=True,
                    ),
                    "comment": ParamSpec(
                        type="string",
                        description="Analyst comment (optional)",
                        required=False,
                        default="",
                    ),
                    "to_ids": ParamSpec(
                        type="boolean",
                        description="Trigger IDS signature (default: True)",
                        required=False,
                        default=True,
                    ),
                    "category": ParamSpec(
                        type="string",
                        description="MISP attribute category (default: Network activity)",
                        required=False,
                        default="Network activity",
                    ),
                },
                handler=misp_add_ioc,
                category=ToolCategory.THREAT_INTEL,
                risk_level=RiskLevel.MEDIUM,
                tags=["misp", "ioc", "attribute", "threat-intel"],
                example='misp_add_ioc(event_id="42", ioc_type="ip-dst", value="1.2.3.4")',
            ),
        ]

        for spec in _specs:
            unregister_tool(spec.name)
            register_tool(spec)

        _logger.info("MISP plugin registered: %d tools", len(_specs))


PLUGIN = MISPPlugin()
