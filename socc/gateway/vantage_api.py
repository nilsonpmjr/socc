from __future__ import annotations

import json
import os
import re
from typing import Any

import requests


DEFAULT_TIMEOUT_SECONDS = 12.0
_QUERY_TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_.:/@-]{3,}")
_CVE_PATTERN = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE)
_HASH_PATTERN = re.compile(r"\b(?:[a-f0-9]{32}|[a-f0-9]{40}|[a-f0-9]{64}|[a-f0-9]{128})\b", re.IGNORECASE)
_IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_DOMAIN_PATTERN = re.compile(r"\b[a-z0-9.-]+\.[a-z]{2,}\b", re.IGNORECASE)
DEFAULT_MODULES: tuple[dict[str, Any], ...] = (
    {
        "id": "dashboard",
        "label": "Dashboard",
        "path": "/api/stats",
        "capabilities": ["overview", "metrics"],
        "enabled_by_default": True,
    },
    {
        "id": "feed",
        "label": "Feed",
        "path": "/api/feed",
        "capabilities": ["intel_feed", "rss_future"],
        "enabled_by_default": True,
    },
    {
        "id": "recon",
        "label": "Recon",
        "path": "/api/recon",
        "capabilities": ["recon", "surface_discovery"],
        "enabled_by_default": True,
    },
    {
        "id": "watchlist",
        "label": "Watchlist",
        "path": "/api/watchlist",
        "capabilities": ["watching", "curation"],
        "enabled_by_default": True,
    },
    {
        "id": "hunting",
        "label": "Hunting",
        "path": "/api/hunting",
        "capabilities": ["hunt_cases", "investigation"],
        "enabled_by_default": True,
    },
    {
        "id": "exposure",
        "label": "Exposure",
        "path": "/api/exposure",
        "capabilities": ["external_exposure", "asset_risk"],
        "enabled_by_default": True,
    },
    {
        "id": "users",
        "label": "Users",
        "path": "/api/users",
        "capabilities": ["identity_context"],
        "enabled_by_default": False,
    },
    {
        "id": "admin",
        "label": "Admin",
        "path": "/api/admin",
        "capabilities": ["administration"],
        "enabled_by_default": False,
    },
)


def _env_flag(name: str, default: bool = False) -> bool:
    value = str(os.getenv(name, "")).strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def _timeout_seconds() -> float:
    try:
        return max(1.0, float(os.getenv("SOCC_VANTAGE_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS))))
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS


def _verify_tls() -> bool:
    return _env_flag("SOCC_VANTAGE_VERIFY_TLS", True)


def _context_max_chars() -> int:
    try:
        return max(300, min(6000, int(os.getenv("SOCC_VANTAGE_CONTEXT_CHARS", "1400"))))
    except ValueError:
        return 1400


def _context_max_modules() -> int:
    try:
        return max(1, min(8, int(os.getenv("SOCC_VANTAGE_CONTEXT_MAX_MODULES", "4"))))
    except ValueError:
        return 4


def _context_query_limit() -> int:
    try:
        return max(1, min(20, int(os.getenv("SOCC_VANTAGE_QUERY_LIMIT", "3"))))
    except ValueError:
        return 3


def _base_url() -> str:
    return str(os.getenv("SOCC_VANTAGE_BASE_URL", "")).strip().rstrip("/")


def _bearer_token() -> str:
    return str(os.getenv("SOCC_VANTAGE_BEARER_TOKEN", "")).strip()


def _api_key() -> str:
    return str(os.getenv("SOCC_VANTAGE_API_KEY", "")).strip()


def _default_enabled_modules() -> list[str]:
    configured = str(os.getenv("SOCC_VANTAGE_ENABLED_MODULES", "")).strip()
    if configured:
        return [
            item.strip().lower()
            for item in configured.split(",")
            if item.strip()
        ]
    return [str(item.get("id") or "").lower() for item in DEFAULT_MODULES if item.get("enabled_by_default")]


def vantage_enabled() -> bool:
    return _env_flag("SOCC_VANTAGE_ENABLED", False)


def auth_mode() -> str:
    if _bearer_token():
        return "bearer"
    if _api_key():
        return "api_key"
    return "none"


def module_catalog() -> list[dict[str, Any]]:
    enabled_ids = set(_default_enabled_modules())
    catalog: list[dict[str, Any]] = []
    for item in DEFAULT_MODULES:
        entry = dict(item)
        entry["selected"] = str(entry.get("id") or "").lower() in enabled_ids
        catalog.append(entry)
    return catalog


def build_context_query(query_text: str, *, fields: dict[str, Any] | None = None) -> str:
    tokens: list[str] = []

    def append_unique(value: str) -> None:
        normalized = str(value or "").strip()
        if normalized and normalized not in tokens:
            tokens.append(normalized)

    text = str(query_text or "")
    for match in _CVE_PATTERN.findall(text):
        append_unique(match.upper())
    for match in _HASH_PATTERN.findall(text):
        append_unique(match.lower())
    for match in _IP_PATTERN.findall(text):
        append_unique(match)
    for match in _DOMAIN_PATTERN.findall(text):
        append_unique(match.lower())

    if isinstance(fields, dict):
        for key in (
            "IP_Origem",
            "IP_Destino",
            "Dominio",
            "Hostname",
            "Servidor",
            "Hash_Observado",
            "Assunto",
            "Regra",
            "URL",
            "Email",
        ):
            value = fields.get(key)
            if isinstance(value, str):
                append_unique(value[:120])

    if len(tokens) < 6:
        for token in _QUERY_TOKEN_PATTERN.findall(text):
            lowered = token.lower()
            if lowered in {"alert", "evento", "payload", "json", "https", "http", "www"}:
                continue
            append_unique(token[:80])
            if len(tokens) >= 8:
                break

    return " ".join(tokens[:8]).strip()


def extract_artifacts(query_text: str, *, fields: dict[str, Any] | None = None) -> dict[str, list[str]]:
    artifacts = {
        "cves": [],
        "hashes": [],
        "ips": [],
        "domains": [],
        "urls": [],
        "hostnames": [],
        "users": [],
    }

    def append_unique(group: str, value: Any) -> None:
        text = str(value or "").strip()
        if text and text not in artifacts[group]:
            artifacts[group].append(text)

    text = str(query_text or "")
    for value in _CVE_PATTERN.findall(text):
        append_unique("cves", value.upper())
    for value in _HASH_PATTERN.findall(text):
        append_unique("hashes", value.lower())
    for value in _IP_PATTERN.findall(text):
        append_unique("ips", value)
    for value in _DOMAIN_PATTERN.findall(text):
        append_unique("domains", value.lower())
    for token in re.findall(r"https?://[^\s\"'>]+", text, flags=re.IGNORECASE):
        append_unique("urls", token)

    if isinstance(fields, dict):
        for key, group in (
            ("IP_Origem", "ips"),
            ("IP_Destino", "ips"),
            ("Hash_Observado", "hashes"),
            ("URL_Completa", "urls"),
            ("DNS_Consulta", "domains"),
            ("HTTP_Host", "domains"),
            ("TLS_SNI", "domains"),
            ("Hostname", "hostnames"),
            ("Servidor", "hostnames"),
            ("Usuario", "users"),
            ("Email_Remetente", "users"),
            ("Email_Destinatario", "users"),
        ):
            value = fields.get(key)
            if isinstance(value, str):
                append_unique(group, value[:160])

    return artifacts


def select_context_modules(query_text: str) -> list[str]:
    selected = [str(item.get("id") or "") for item in module_catalog() if item.get("selected")]
    if not selected:
        return []

    text = str(query_text or "").lower()
    ranked: list[str] = []

    def add(module_id: str) -> None:
        if module_id in selected and module_id not in ranked:
            ranked.append(module_id)

    if any(token in text for token in ("cve-", "ioc", "hash", "sha256", "sha1", "md5", "feed", "threat intel")):
        for module_id in ("feed", "watchlist", "exposure"):
            add(module_id)
    if any(token in text for token in ("hunt", "hunting", "detec", "behavior", "comportamento", "ttp", "mitre")):
        for module_id in ("hunting", "recon", "feed"):
            add(module_id)
    if any(token in text for token in ("ip", "dominio", "domain", "url", "hostname", "server", "host")):
        for module_id in ("exposure", "watchlist", "recon"):
            add(module_id)
    if any(token in text for token in ("user", "usuario", "login", "auth", "mfa", "conta")):
        add("users")

    for module_id in selected:
        add(module_id)

    return ranked[: _context_max_modules()]


def resolve_module(module_id: str) -> dict[str, Any]:
    target = str(module_id or "").strip().lower()
    for item in module_catalog():
        if str(item.get("id") or "").lower() == target:
            return item
    raise LookupError("Módulo do Vantage não encontrado.")


def build_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "socc-vantage-client/0.1",
    }
    if _bearer_token():
        headers["Authorization"] = f"Bearer {_bearer_token()}"
    elif _api_key():
        headers["X-API-Key"] = _api_key()
    return headers


def status_payload() -> dict[str, Any]:
    base_url = _base_url()
    catalog = module_catalog()
    return {
        "enabled": vantage_enabled(),
        "base_url": base_url,
        "configured": bool(base_url),
        "auth_mode": auth_mode(),
        "timeout_seconds": _timeout_seconds(),
        "verify_tls": _verify_tls(),
        "catalog_size": len(catalog),
        "selected_modules": [item.get("id") for item in catalog if item.get("selected")],
        "modules": catalog,
        "future_rss_via_api": True,
    }


def query_module(
    module_id: str,
    *,
    params: dict[str, Any] | None = None,
    method: str = "GET",
) -> dict[str, Any]:
    status = status_payload()
    if not status.get("enabled"):
        raise RuntimeError("Integração com Vantage está desabilitada.")
    base_url = str(status.get("base_url") or "")
    if not base_url:
        raise RuntimeError("SOCC_VANTAGE_BASE_URL não configurado.")

    module = resolve_module(module_id)
    url = f"{base_url}{module.get('path')}"
    response = requests.request(
        method.upper(),
        url,
        params=params or None,
        headers=build_headers(),
        timeout=_timeout_seconds(),
        verify=_verify_tls(),
    )
    response.raise_for_status()
    try:
        body = response.json()
    except Exception:
        body = {
            "raw_text": response.text,
        }
    return {
        "module": module,
        "request": {
            "method": method.upper(),
            "url": url,
            "params": params or {},
        },
        "response": body,
        "status_code": response.status_code,
    }


def _module_query_params(module_id: str, context_query: str, artifacts: dict[str, list[str]]) -> dict[str, Any]:
    params: dict[str, Any] = {
        "q": context_query,
        "limit": _context_query_limit(),
    }

    if artifacts.get("cves"):
        params["cve"] = artifacts["cves"][0]
    if artifacts.get("hashes"):
        params["hash"] = artifacts["hashes"][0]
        params["ioc"] = artifacts["hashes"][0]
    elif artifacts.get("ips"):
        params["ip"] = artifacts["ips"][0]
        params["ioc"] = artifacts["ips"][0]
    elif artifacts.get("domains"):
        params["domain"] = artifacts["domains"][0]
        params["ioc"] = artifacts["domains"][0]
    elif artifacts.get("urls"):
        params["url"] = artifacts["urls"][0]
        params["ioc"] = artifacts["urls"][0]

    if module_id == "users" and artifacts.get("users"):
        params["user"] = artifacts["users"][0]
    if module_id == "recon" and artifacts.get("hostnames"):
        params["host"] = artifacts["hostnames"][0]
    if module_id == "exposure" and artifacts.get("domains"):
        params["asset"] = artifacts["domains"][0]
    return params


def probe_module(module_id: str) -> dict[str, Any]:
    try:
        result = query_module(module_id)
        return {
            "ok": True,
            "module": module_id,
            "status_code": result.get("status_code"),
            "error": "",
        }
    except Exception as exc:
        return {
            "ok": False,
            "module": module_id,
            "status_code": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _short_json(value: Any, *, max_chars: int = 280) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except Exception:
        text = str(value)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_chars:
        return text[: max_chars - 3].rstrip() + "..."
    return text


def _summarize_response(module: dict[str, Any], payload: Any) -> str:
    label = str(module.get("label") or module.get("id") or "module")
    if isinstance(payload, dict):
        for key in ("items", "results", "data", "entries"):
            value = payload.get(key)
            if isinstance(value, list):
                count = len(value)
                preview = _short_json(value[: min(2, count)], max_chars=220)
                return f"{label}: {count} item(ns) relevantes. Preview: {preview}"
        preview = _short_json(payload, max_chars=260)
        return f"{label}: {preview}"
    if isinstance(payload, list):
        preview = _short_json(payload[: min(2, len(payload))], max_chars=220)
        return f"{label}: {len(payload)} item(ns). Preview: {preview}"
    return f"{label}: {_short_json(payload, max_chars=260)}"


def retrieve_context(
    query_text: str,
    *,
    fields: dict[str, Any] | None = None,
    module_ids: list[str] | None = None,
) -> dict[str, Any]:
    status = status_payload()
    context_query = build_context_query(query_text, fields=fields)
    artifacts = extract_artifacts(query_text, fields=fields)
    modules = list(module_ids or select_context_modules(context_query or query_text))
    result = {
        "enabled": bool(status.get("enabled")),
        "configured": bool(status.get("configured")),
        "query_text": context_query,
        "artifacts": artifacts,
        "modules": modules,
        "matches": [],
        "sources": [],
        "errors": [],
        "context": "",
    }
    if not status.get("enabled") or not status.get("configured") or not modules or not context_query:
        return result

    sections: list[str] = []
    remaining_chars = _context_max_chars()

    for module_id in modules:
        try:
            payload = query_module(module_id, params=_module_query_params(module_id, context_query, artifacts))
            module = dict(payload.get("module") or {})
            response = payload.get("response")
            summary = _summarize_response(module, response)
            if summary:
                clipped = summary[:remaining_chars].strip()
                if clipped:
                    sections.append(clipped)
                    remaining_chars -= len(clipped) + 2
            result["matches"].append(
                {
                    "module_id": str(module.get("id") or module_id),
                    "label": str(module.get("label") or module_id),
                    "summary": summary,
                    "status_code": payload.get("status_code"),
                    "request_params": dict((payload.get("request") or {}).get("params") or {}),
                }
            )
            result["sources"].append(
                {
                    "source_id": f"vantage:{module.get('id') or module_id}",
                    "source_name": f"Vantage/{module.get('label') or module_id}",
                    "module": str(module.get("id") or module_id),
                    "path": str(module.get("path") or ""),
                    "status_code": payload.get("status_code"),
                }
            )
            if remaining_chars <= 0:
                break
        except Exception as exc:
            result["errors"].append(
                {
                    "module": module_id,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    result["context"] = "\n".join(section for section in sections if section).strip()
    return result
