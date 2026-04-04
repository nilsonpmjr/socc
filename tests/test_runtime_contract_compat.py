from __future__ import annotations

import importlib


def test_legacy_tool_wrapper_normalizes_missing_tool_error():
    from socc.core.tools import invoke_tool

    payload = invoke_tool("missing_tool_xyz", {})

    assert payload["ok"] is False
    assert payload["error"] == "tool_not_found"
    assert "error_detail" in (payload.get("metadata") or {})


def test_resolve_api_key_prefers_env_over_oauth_store(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key-123")
    monkeypatch.setenv("SOCC_AUTH_METHOD_ANTHROPIC", "oauth")

    import socc.gateway.llm_gateway as llm_gateway

    monkeypatch.setattr(
        llm_gateway,
        "_resolve_oauth_token",
        lambda provider_name: "oauth-token-456",
    )
    importlib.reload(llm_gateway)
    monkeypatch.setattr(
        llm_gateway,
        "_resolve_oauth_token",
        lambda provider_name: "oauth-token-456",
    )

    assert llm_gateway.resolve_api_key("anthropic") == "env-key-123"
    context = llm_gateway.resolve_auth_context("anthropic")
    assert context["credential"] == "env-key-123"
    assert context["source"] == "env"
