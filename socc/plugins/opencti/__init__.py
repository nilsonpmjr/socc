"""OpenCTI plugin for SOCC.

Provides two tools:
- ``opencti_search``           — search indicators, malware, threat actors
- ``opencti_create_indicator`` — create a STIX 2.1 indicator in OpenCTI

Requires:
    OPENCTI_URL     — base URL of your OpenCTI instance
    OPENCTI_API_KEY — API token from OpenCTI user profile

All queries use the OpenCTI GraphQL API.
Indicators are created as STIX 2.1 Pattern objects.

Attribution: OpenCTI REST/GraphQL API (https://docs.opencti.io/latest/reference/api/)
"""

from __future__ import annotations

import json
import logging
import os
import ssl
from datetime import datetime, timezone
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

__all__ = ["PLUGIN", "OpenCTIPlugin"]

_logger = logging.getLogger(__name__)
_MANIFEST = PluginManifest.from_file(Path(__file__).parent / "plugin.json")

# STIX 2.1 indicator pattern types and their template strings
STIX_PATTERN_TEMPLATES: dict[str, str] = {
    "ipv4-addr": "[ipv4-addr:value = '{value}']",
    "ipv6-addr": "[ipv6-addr:value = '{value}']",
    "domain-name": "[domain-name:value = '{value}']",
    "url": "[url:value = '{value}']",
    "file:md5": "[file:hashes.MD5 = '{value}']",
    "file:sha1": "[file:hashes.'SHA-1' = '{value}']",
    "file:sha256": "[file:hashes.'SHA-256' = '{value}']",
    "email-addr": "[email-message:from_ref.value = '{value}']",
    "mutex": "[mutex:name = '{value}']",
    "process": "[process:command_line LIKE '%{value}%']",
}

# OpenCTI entity types for search
OPENCTI_ENTITY_TYPES = [
    "Indicator", "Malware", "ThreatActor", "IntrusionSet",
    "Campaign", "AttackPattern", "Tool", "Vulnerability",
    "Report", "Note", "ObservedData",
]


# ---------------------------------------------------------------------------
# GraphQL helpers
# ---------------------------------------------------------------------------

def _get_config() -> tuple[str, str]:
    url = os.environ.get("OPENCTI_URL", "").rstrip("/")
    key = os.environ.get("OPENCTI_API_KEY", "")
    if not url:
        raise RuntimeError("OPENCTI_URL environment variable not set")
    if not key:
        raise RuntimeError("OPENCTI_API_KEY environment variable not set")
    return url, key


def _graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a GraphQL query against OpenCTI."""
    import urllib.request

    base_url, api_key = _get_config()
    endpoint = f"{base_url}/graphql"
    payload = json.dumps({"query": query, "variables": variables or {}}).encode()

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(
        endpoint,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
            result = json.loads(resp.read())
            if "errors" in result:
                errors = "; ".join(e.get("message", str(e)) for e in result["errors"])
                raise RuntimeError(f"GraphQL errors: {errors}")
            return result.get("data", {})
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"OpenCTI API error: {type(exc).__name__}: {exc}") from exc


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

_SEARCH_QUERY = """
query Search($search: String!, $types: [String!], $first: Int) {
  stixCoreObjects(
    search: $search
    types: $types
    first: $first
    orderBy: created_at
    orderMode: desc
  ) {
    edges {
      node {
        id
        entity_type
        created_at
        updated_at
        ... on Indicator {
          name
          description
          pattern
          pattern_type
          valid_from
          valid_until
          confidence
          x_opencti_score
        }
        ... on Malware {
          name
          description
          malware_types
          is_family
        }
        ... on ThreatActor {
          name
          description
          threat_actor_types
          sophistication
        }
        ... on IntrusionSet {
          name
          description
        }
        ... on AttackPattern {
          name
          description
          x_mitre_id
        }
        ... on Tool {
          name
          description
          tool_types
        }
      }
    }
    pageInfo {
      globalCount
    }
  }
}
"""

_CREATE_INDICATOR_MUTATION = """
mutation CreateIndicator($input: IndicatorAddInput!) {
  indicatorAdd(input: $input) {
    id
    name
    pattern
    pattern_type
    valid_from
    x_opencti_score
    created_at
  }
}
"""


def opencti_search(
    query: str,
    entity_types: list[str] | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Search OpenCTI for indicators, malware, threat actors, and more.

    Args:
        query: Free-text search string.
        entity_types: Filter by OpenCTI entity type(s)
            (e.g. ``["Indicator", "Malware"]``). Default: all types.
        limit: Maximum results to return (default: 20, max: 100).

    Returns:
        Dict with ``results`` list and ``total_count``.
    """
    limit = min(int(limit), 100)
    if entity_types:
        invalid = [t for t in entity_types if t not in OPENCTI_ENTITY_TYPES]
        if invalid:
            return {
                "error": f"Unknown entity type(s): {', '.join(invalid)}. "
                         f"Valid types: {', '.join(OPENCTI_ENTITY_TYPES)}",
            }

    # Resolve base_url for permalinks (best-effort — may be empty without env)
    try:
        base_url, _ = _get_config()
    except RuntimeError:
        base_url = ""

    try:
        data = _graphql(
            _SEARCH_QUERY,
            {
                "search": query,
                "types": entity_types or None,
                "first": limit,
            },
        )

        edges = data.get("stixCoreObjects", {}).get("edges", [])
        total = (
            data.get("stixCoreObjects", {})
                .get("pageInfo", {})
                .get("globalCount", len(edges))
        )

        results = []
        for edge in edges:
            node = edge.get("node", {})
            entry: dict[str, Any] = {
                "id": node.get("id"),
                "type": node.get("entity_type"),
                "name": node.get("name", ""),
                "description": (node.get("description") or "")[:200],
                "created_at": node.get("created_at"),
            }
            # Type-specific extras
            if node.get("pattern"):
                entry["pattern"] = node["pattern"]
            if node.get("x_opencti_score") is not None:
                entry["score"] = node["x_opencti_score"]
            if node.get("x_mitre_id"):
                entry["mitre_id"] = node["x_mitre_id"]
            if node.get("malware_types"):
                entry["malware_types"] = node["malware_types"]
            results.append(entry)

        out: dict[str, Any] = {
            "query": query,
            "total_count": total,
            "returned": len(results),
            "results": results,
        }
        if base_url:
            out["opencti_url"] = base_url
        return out
    except RuntimeError as exc:
        return {"error": str(exc), "query": query}


def opencti_create_indicator(
    name: str,
    pattern_type: str,
    value: str,
    description: str = "",
    score: int = 50,
    valid_days: int = 365,
    labels: list[str] | None = None,
) -> dict[str, Any]:
    """Create a STIX 2.1 indicator in OpenCTI.

    Args:
        name: Human-readable indicator name.
        pattern_type: STIX pattern type key. One of:
            ``ipv4-addr``, ``ipv6-addr``, ``domain-name``, ``url``,
            ``file:md5``, ``file:sha1``, ``file:sha256``,
            ``email-addr``, ``mutex``, ``process``.
        value: The IOC value (e.g. ``"1.2.3.4"`` or ``"evil.com"``).
        description: Optional analyst description.
        score: OpenCTI confidence score 0-100 (default: 50).
        valid_days: Days from now until indicator expires (default: 365).
        labels: Optional list of label names to attach.

    Returns:
        Dict with created indicator id and permalink.
    """
    if pattern_type not in STIX_PATTERN_TEMPLATES:
        return {
            "error": f"Unknown pattern_type: {pattern_type!r}. "
                     f"Valid types: {', '.join(STIX_PATTERN_TEMPLATES)}",
        }

    score = max(0, min(100, int(score)))
    pattern = STIX_PATTERN_TEMPLATES[pattern_type].format(value=value)
    now = datetime.now(timezone.utc)
    valid_from = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    valid_until = now.replace(
        year=now.year + (valid_days // 365),
        day=min(now.day, 28),   # avoid Feb 30 etc.
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    indicator_input: dict[str, Any] = {
        "name": name,
        "pattern": pattern,
        "pattern_type": "stix",
        "valid_from": valid_from,
        "valid_until": valid_until,
        "x_opencti_score": score,
        "description": description,
        "confidence": score,
    }
    if labels:
        indicator_input["labels"] = labels

    try:
        data = _graphql(
            _CREATE_INDICATOR_MUTATION,
            {"input": indicator_input},
        )
        indicator = data.get("indicatorAdd", {})
        base_url, _ = _get_config()
        ind_id = indicator.get("id")

        return {
            "created": True,
            "id": ind_id,
            "name": name,
            "pattern": pattern,
            "score": score,
            "valid_from": valid_from,
            "valid_until": valid_until,
            "permalink": f"{base_url}/dashboard/observations/indicators/{ind_id}" if ind_id else None,
        }
    except RuntimeError as exc:
        return {"created": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Plugin class
# ---------------------------------------------------------------------------

class OpenCTIPlugin(SOCCPlugin):
    """OpenCTI threat intelligence platform plugin."""

    manifest = _MANIFEST

    def register(self) -> None:
        _specs = [
            ToolSpec(
                name="opencti_search",
                description=(
                    "Search OpenCTI for indicators, malware, threat actors, "
                    "attack patterns, and more. Uses GraphQL full-text search."
                ),
                parameters={
                    "query": ParamSpec(
                        type="string",
                        description="Free-text search string",
                        required=True,
                    ),
                    "entity_types": ParamSpec(
                        type="array",
                        description=(
                            "Filter by entity type(s): Indicator, Malware, "
                            "ThreatActor, AttackPattern, etc. (optional)"
                        ),
                        required=False,
                        default=None,
                    ),
                    "limit": ParamSpec(
                        type="integer",
                        description="Max results (default: 20, max: 100)",
                        required=False,
                        default=20,
                    ),
                },
                handler=opencti_search,
                category=ToolCategory.THREAT_INTEL,
                risk_level=RiskLevel.LOW,
                tags=["opencti", "threat-intel", "stix", "indicator", "search"],
                example='opencti_search(query="APT29", entity_types=["ThreatActor"])',
            ),
            ToolSpec(
                name="opencti_create_indicator",
                description=(
                    "Create a STIX 2.1 indicator in OpenCTI. "
                    "Supports IP, domain, URL, file hashes, email, mutex, and process patterns."
                ),
                parameters={
                    "name": ParamSpec(
                        type="string",
                        description="Human-readable indicator name",
                        required=True,
                    ),
                    "pattern_type": ParamSpec(
                        type="string",
                        description=(
                            "STIX pattern type: ipv4-addr, domain-name, url, "
                            "file:md5, file:sha1, file:sha256, email-addr, mutex, process"
                        ),
                        required=True,
                    ),
                    "value": ParamSpec(
                        type="string",
                        description="The IOC value",
                        required=True,
                    ),
                    "description": ParamSpec(
                        type="string",
                        description="Analyst description (optional)",
                        required=False,
                        default="",
                    ),
                    "score": ParamSpec(
                        type="integer",
                        description="Confidence/severity score 0-100 (default: 50)",
                        required=False,
                        default=50,
                    ),
                    "valid_days": ParamSpec(
                        type="integer",
                        description="Days until indicator expires (default: 365)",
                        required=False,
                        default=365,
                    ),
                    "labels": ParamSpec(
                        type="array",
                        description="List of label strings to attach (optional)",
                        required=False,
                        default=None,
                    ),
                },
                handler=opencti_create_indicator,
                category=ToolCategory.THREAT_INTEL,
                risk_level=RiskLevel.MEDIUM,
                tags=["opencti", "indicator", "stix", "create", "threat-intel"],
                example='opencti_create_indicator(name="C2 IP", pattern_type="ipv4-addr", value="1.2.3.4", score=80)',
            ),
        ]

        for spec in _specs:
            unregister_tool(spec.name)
            register_tool(spec)

        _logger.info("OpenCTI plugin registered: %d tools", len(_specs))


PLUGIN = OpenCTIPlugin()
