"""
Valida o contrato inicial do cliente da API do Vantage.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from socc.gateway import vantage_api

PASS = "PASS"
FAIL = "FAIL"
resultados: list[tuple[str, str, str]] = []


def check(nome: str, condicao: bool, detalhe: str = "") -> None:
    status = PASS if condicao else FAIL
    resultados.append((status, nome, detalhe))


class FakeResponse:
    status_code = 200
    text = '{"ok":true}'

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {"ok": True, "items": []}


class FakeContextResponse:
    status_code = 200
    text = '{"items":[{"title":"CVE"}]}'

    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return dict(self._payload)


original_env = {
    key: os.environ.get(key)
    for key in (
        "SOCC_VANTAGE_ENABLED",
        "SOCC_VANTAGE_BASE_URL",
        "SOCC_VANTAGE_BEARER_TOKEN",
        "SOCC_VANTAGE_API_KEY",
        "SOCC_VANTAGE_ENABLED_MODULES",
    )
}
original_request = vantage_api.requests.request

try:
    os.environ["SOCC_VANTAGE_ENABLED"] = "true"
    os.environ["SOCC_VANTAGE_BASE_URL"] = "https://vantage.local"
    os.environ["SOCC_VANTAGE_BEARER_TOKEN"] = "secret-token"
    os.environ["SOCC_VANTAGE_ENABLED_MODULES"] = "feed,hunting,watchlist"

    status = vantage_api.status_payload()
    check("vantage_status_enabled", status.get("enabled") is True)
    check("vantage_status_auth_mode", status.get("auth_mode") == "bearer")
    check(
        "vantage_status_selected_modules",
        set(status.get("selected_modules") or []) == {"feed", "hunting", "watchlist"},
        str(status.get("selected_modules")),
    )

    headers = vantage_api.build_headers()
    check("vantage_headers_auth", headers.get("Authorization") == "Bearer secret-token", str(headers))

    module = vantage_api.resolve_module("feed")
    check("vantage_resolve_feed", module.get("path") == "/api/feed", str(module))

    def fake_request(method: str, url: str, params=None, headers=None, timeout=None, verify=None):
        check("vantage_query_method", method == "GET", method)
        check("vantage_query_url", url == "https://vantage.local/api/feed", url)
        check("vantage_query_params", params == {"q": "cve"}, str(params))
        check("vantage_query_auth", (headers or {}).get("Authorization") == "Bearer secret-token", str(headers))
        check("vantage_query_timeout", float(timeout or 0) >= 1.0, str(timeout))
        check("vantage_query_verify_tls", verify is True, str(verify))
        return FakeResponse()

    vantage_api.requests.request = fake_request
    result = vantage_api.query_module("feed", params={"q": "cve"})
    check("vantage_query_status_code", result.get("status_code") == 200, str(result))
    check("vantage_query_response_json", isinstance(result.get("response"), dict), str(result.get("response")))

    requests_seen: list[str] = []

    def fake_context_request(method: str, url: str, params=None, headers=None, timeout=None, verify=None):
        requests_seen.append(url)
        if url.endswith("/api/feed"):
            return FakeContextResponse({"items": [{"title": "CVE-2025-1234 em feed"}]})
        if url.endswith("/api/exposure"):
            return FakeContextResponse({"items": [{"asset": "srv-app-01", "risk": "high"}]})
        return FakeContextResponse({"items": [{"note": "generic"}]})

    vantage_api.requests.request = fake_context_request
    context = vantage_api.retrieve_context("preciso investigar a CVE-2025-1234 neste host 10.0.0.5")
    check("vantage_context_query_contains_cve", "CVE-2025-1234" in str(context.get("query_text") or ""), str(context))
    check("vantage_context_has_modules", len(context.get("modules") or []) >= 1, str(context))
    check("vantage_context_has_sources", len(context.get("sources") or []) >= 1, str(context))
    check("vantage_context_has_text", len(str(context.get("context") or "").strip()) >= 1, str(context))
    check("vantage_context_calls_some_module", len(requests_seen) >= 1, str(requests_seen))
    check("vantage_context_has_artifacts", "CVE-2025-1234" in (context.get("artifacts") or {}).get("cves", []), str(context.get("artifacts")))
    request_params = ((context.get("matches") or [{}])[0]).get("request_params") or {}
    check("vantage_context_request_params_include_cve", request_params.get("cve") == "CVE-2025-1234", str(request_params))
except Exception as exc:
    check("vantage_gateway_flow", False, str(exc))
finally:
    vantage_api.requests.request = original_request
    for key, value in original_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


print(f"\n{'='*60}")
print(f"SOCC Runtime — Vantage Gateway  ({len(resultados)} checks)")
print("=" * 60)
falhas = [(n, d) for s, n, d in resultados if s == FAIL]
aprovados = len(resultados) - len(falhas)
print(f"  Aprovados : {aprovados}/{len(resultados)}")
print(f"  Falhas    : {len(falhas)}/{len(resultados)}")
print()
for nome, detalhe in falhas:
    extra = f" — {detalhe}" if detalhe else ""
    print(f"  FALHA: {nome}{extra}")
if not falhas:
    print("  Todos os checks passaram.")
print()

sys.exit(1 if falhas else 0)
