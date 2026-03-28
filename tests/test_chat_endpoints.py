"""
Valida integracao basica das rotas web do chat no nivel de endpoint/ASGI.
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

from starlette.requests import Request

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import soc_copilot.main as main_module

PASS = "PASS"
FAIL = "FAIL"
resultados: list[tuple[str, str, str]] = []


def check(nome: str, condicao: bool, detalhe: str = "") -> None:
    status = PASS if condicao else FAIL
    resultados.append((status, nome, detalhe))


def _http_request(path: str) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 1234),
        "server": ("127.0.0.1", 8081),
        "scheme": "http",
        "root_path": "",
        "http_version": "1.1",
    }
    return Request(scope)


class JsonRequest:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    async def json(self) -> dict[str, object]:
        return dict(self._payload)


async def _collect_streaming_body(response) -> str:
    chunks: list[str] = []
    async for chunk in response.body_iterator:
        if isinstance(chunk, bytes):
            chunks.append(chunk.decode("utf-8", errors="replace"))
        else:
            chunks.append(str(chunk))
    return "".join(chunks)


tmpdir = tempfile.TemporaryDirectory()
original_socc_home = os.environ.get("SOCC_HOME")
os.environ["SOCC_HOME"] = str(Path(tmpdir.name) / ".socc-chat-http")

original_chat_submission = main_module.chat_submission
original_stream_chat_submission_events = main_module.stream_chat_submission_events
original_list_chat_sessions_payload = main_module.list_chat_sessions_payload
original_list_chat_session_messages_payload = main_module.list_chat_session_messages_payload
original_runtime_status_payload = main_module.runtime_status_payload
original_control_center_summary_payload = main_module.control_center_summary_payload
original_select_active_agent_payload = main_module.select_active_agent_payload
original_select_runtime_model_payload = main_module.select_runtime_model_payload
original_select_vantage_modules_payload = main_module.select_vantage_modules_payload
original_warmup_runtime_model_payload = main_module.warmup_runtime_model_payload
original_asyncio_to_thread = main_module.asyncio.to_thread


async def _fake_stream_chat_submission_events(**kwargs):
    yield {
        "event": "meta",
        "payload": {
            "session_id": "sessao-http",
            "skill": "triage",
            "runtime": {"provider": "stub"},
        },
    }
    yield {
        "event": "delta",
        "payload": {
            "delta": "resposta parcial",
            "session_id": "sessao-http",
        },
    }
    yield {
        "event": "final",
        "payload": {
            "type": "message",
            "content": "resposta final",
            "session_id": "sessao-http",
            "skill": "triage",
            "runtime": {"provider": "stub"},
        },
    }


async def _direct_to_thread(fn, *args, **kwargs):
    return fn(*args, **kwargs)


try:
    main_module.chat_submission = lambda **kwargs: {
        "type": "message",
        "content": f"eco: {kwargs.get('message', '')}",
        "session_id": kwargs.get("session_id") or "sessao-http",
        "skill": "triage",
        "runtime": {"provider": "stub"},
        "gateway": {"provider": "stub"},
    }
    main_module.stream_chat_submission_events = _fake_stream_chat_submission_events
    main_module.list_chat_sessions_payload = lambda limit=50: {
        "sessions": [{"session_id": "sessao-http", "preview": "Teste de sessao"}]
    }
    main_module.list_chat_session_messages_payload = lambda session_id, limit=100: {
        "messages": [
            {
                "role": "assistant",
                "content": "resposta final",
                "session_id": session_id,
                "metadata": {
                    "type": "message",
                    "content": "resposta final",
                    "session_id": session_id,
                    "metadata": {
                        "vantage_modules": ["feed", "hunting"],
                        "vantage_sources": [{"source_name": "Vantage/Feed"}],
                        "vantage_context": "Feed: 1 item relevante.",
                    },
                },
            }
        ]
    }
    main_module.runtime_status_payload = lambda: {
        "runtime": {"provider": "stub", "model": "stub-model"},
        "features": {"chat_api": True, "chat_streaming": True},
    }
    main_module.control_center_summary_payload = lambda limit_sessions=12: {
        "runtime": {
            "runtime": {"provider": "stub", "backend": "ollama", "model": "stub-model"},
            "features": {"chat_api": True, "chat_streaming": True},
            "backends": {"supported": [{"key": "ollama", "selected": True}]},
        },
        "runtime_models": {
            "catalog": {"reachable": True, "models": [{"name": "llama3.2:3b"}, {"name": "qwen3.5:9b"}]},
            "profiles": {"fast": "llama3.2:3b", "balanced": "qwen3.5:9b", "deep": "qwen3.5:9b"},
        },
        "agents": {
            "selected": {"id": "soc-copilot", "path": "/tmp/agent"},
            "available": [{"id": "soc-copilot", "path": "/tmp/agent", "selected": True}],
        },
        "knowledge_base": {"manifest": {"indexed_documents": 1, "indexed_chunks": 3}, "sources": []},
        "vantage": {
            "enabled": True,
            "base_url": "https://vantage.local",
            "auth_mode": "bearer",
            "selected_modules": ["feed", "hunting"],
            "modules": [
                {"id": "feed", "label": "Feed", "path": "/api/feed", "selected": True},
                {"id": "hunting", "label": "Hunting", "path": "/api/hunting", "selected": True},
            ],
        },
        "sessions": {"count": 1, "items": [{"session_id": "sessao-http", "title": "Sessão"}]},
        "diagnostics": {"checks": {"runtime_home_exists": True}},
        "service": {"running": False},
    }
    main_module.select_active_agent_payload = lambda agent_id: {
        "selected_agent": {"id": agent_id, "label": agent_id, "path": f"/tmp/{agent_id}"},
        "control_center": main_module.control_center_summary_payload(),
    }
    main_module.select_runtime_model_payload = lambda response_mode, model: {
        "response_mode": response_mode,
        "model": model,
        "control_center": main_module.control_center_summary_payload(),
    }
    main_module.select_vantage_modules_payload = lambda module_ids, enabled=None: {
        "selected_modules": list(module_ids),
        "enabled": bool(enabled),
        "control_center": main_module.control_center_summary_payload(),
    }
    main_module.warmup_runtime_model_payload = lambda response_mode="balanced": {
        "response_mode": response_mode,
        "result": {"model": "llama3.2:3b", "warmed": True},
        "control_center": main_module.control_center_summary_payload(),
    }
    main_module.asyncio.to_thread = _direct_to_thread

    async def _exercise_endpoints() -> None:
        root_response = await main_module.index(_http_request("/"))
        check("chat_http_root_redirect", root_response.status_code == 307)
        check("chat_http_root_redirect_target", root_response.headers.get("location") == "/chat")

        chat_page = await main_module.chat_ui(_http_request("/chat"))
        chat_body = chat_page.body.decode("utf-8", errors="replace")
        check("chat_http_chat_page_status", chat_page.status_code == 200)
        check("chat_http_chat_page_body", "SOC Copilot" in chat_body and "Chat" in chat_body)

        legacy_page = await main_module.legacy_index(_http_request("/legacy"))
        legacy_body = legacy_page.body.decode("utf-8", errors="replace")
        check("chat_http_legacy_page_status", legacy_page.status_code == 200)
        check("chat_http_legacy_page_body", "Threat Intelligence" in legacy_body or "Analise" in legacy_body)

        runtime_status = await main_module.api_runtime_status()
        runtime_payload = getattr(runtime_status, "body", b"").decode("utf-8", errors="replace")
        check("chat_http_runtime_status_code", runtime_status.status_code == 200)
        check("chat_http_runtime_status_provider", "stub-model" in runtime_payload)

        control_center = await main_module.api_control_center()
        control_body = getattr(control_center, "body", b"").decode("utf-8", errors="replace")
        check("chat_http_control_center_status", control_center.status_code == 200)
        check("chat_http_control_center_payload", "soc-copilot" in control_body and "indexed_documents" in control_body)

        select_agent = await main_module.api_control_center_select_agent(JsonRequest({"agent_id": "soc-copilot"}))
        select_agent_body = getattr(select_agent, "body", b"").decode("utf-8", errors="replace")
        check("chat_http_select_agent_status", select_agent.status_code == 200)
        check("chat_http_select_agent_payload", "/tmp/soc-copilot" in select_agent_body)

        select_model = await main_module.api_control_center_select_runtime_model(
            JsonRequest({"response_mode": "fast", "model": "llama3.2:3b"})
        )
        select_model_body = getattr(select_model, "body", b"").decode("utf-8", errors="replace")
        check("chat_http_select_model_status", select_model.status_code == 200)
        check("chat_http_select_model_payload", "llama3.2:3b" in select_model_body)

        select_vantage = await main_module.api_control_center_select_vantage_modules(
            JsonRequest({"module_ids": ["feed", "watchlist"], "enabled": True})
        )
        select_vantage_body = getattr(select_vantage, "body", b"").decode("utf-8", errors="replace")
        check("chat_http_select_vantage_status", select_vantage.status_code == 200)
        check("chat_http_select_vantage_payload", "watchlist" in select_vantage_body)

        warmup_model = await main_module.api_control_center_runtime_warmup(
            JsonRequest({"response_mode": "fast"})
        )
        warmup_model_body = getattr(warmup_model, "body", b"").decode("utf-8", errors="replace")
        check("chat_http_warmup_model_status", warmup_model.status_code == 200)
        check("chat_http_warmup_model_payload", "\"warmed\":true" in warmup_model_body.replace(" ", ""))

        sync_response = await main_module.chat_endpoint(JsonRequest({"message": "teste endpoint", "session_id": "sessao-http"}))
        sync_body = getattr(sync_response, "body", b"").decode("utf-8", errors="replace")
        check("chat_http_sync_status", sync_response.status_code == 200)
        check("chat_http_sync_payload", "eco: teste endpoint" in sync_body)

        export_response = await main_module.export_analysis(
            JsonRequest(
                {
                    "format": "ticket",
                    "session_id": "sessao-http",
                    "cliente": "Teste",
                    "classificacao": "TP",
                    "fields": {"Assunto": "Bloqueio de IOC"},
                    "analysis": {"contextos_investigativos": []},
                    "analysis_structured": {
                        "summary": "IOC externo bloqueado com sucesso.",
                        "verdict": "suspeito",
                        "recommended_actions": ["Validar recorrência do IOC."],
                        "risk_reasons": ["Origem externa bloqueada."],
                        "iocs": [{"type": "ip", "value": "198.51.100.9"}],
                    },
                    "analysis_priority": {"level": "Alta", "score": 82},
                    "analysis_trace": {"observed_facts": [], "inferences": [], "limitations": []},
                    "operational_payload": {
                        "title": "Bloqueio de IOC",
                        "classification": "TP",
                        "disposition": "alerta",
                        "disposition_label": "Abertura de alerta",
                        "verdict": "suspeito",
                        "priority": {"level": "Alta", "score": 82},
                        "recommended_actions": ["Validar recorrência do IOC."],
                        "iocs": [{"type": "ip", "value": "198.51.100.9"}],
                        "evidence": [{"label": "IP Origem", "value": "198.51.100.9", "source": "payload"}],
                    },
                    "draft": "Rascunho operacional.",
                }
            )
        )
        export_body = getattr(export_response, "body", b"").decode("utf-8", errors="replace")
        check("chat_http_export_ticket_status", export_response.status_code == 200)
        check("chat_http_export_ticket_payload", "\"format\":\"ticket\"" in export_body.replace(" ", ""))

        invalid_response = await main_module.chat_endpoint(JsonRequest({"message": "   "}))
        check("chat_http_sync_invalid_status", invalid_response.status_code == 400)

        stream_response = await main_module.chat_stream_endpoint(JsonRequest({"message": "teste stream", "session_id": "sessao-http"}))
        stream_body = await _collect_streaming_body(stream_response)
        check("chat_http_stream_status", stream_response.status_code == 200)
        check("chat_http_stream_meta", "event: meta" in stream_body)
        check("chat_http_stream_final", "event: final" in stream_body and "resposta final" in stream_body)

        sessions_response = await main_module.chat_sessions()
        sessions_body = getattr(sessions_response, "body", b"").decode("utf-8", errors="replace")
        check("chat_http_sessions_status", sessions_response.status_code == 200)
        check("chat_http_sessions_payload", "sessao-http" in sessions_body)

        messages_response = await main_module.chat_session_messages("sessao-http")
        messages_body = getattr(messages_response, "body", b"").decode("utf-8", errors="replace")
        check("chat_http_messages_status", messages_response.status_code == 200)
        check("chat_http_messages_payload", "resposta final" in messages_body)

    asyncio.run(_exercise_endpoints())
except Exception as exc:
    check("chat_http_endpoints_flow", False, str(exc))
finally:
    main_module.chat_submission = original_chat_submission
    main_module.stream_chat_submission_events = original_stream_chat_submission_events
    main_module.list_chat_sessions_payload = original_list_chat_sessions_payload
    main_module.list_chat_session_messages_payload = original_list_chat_session_messages_payload
    main_module.runtime_status_payload = original_runtime_status_payload
    main_module.control_center_summary_payload = original_control_center_summary_payload
    main_module.select_active_agent_payload = original_select_active_agent_payload
    main_module.select_runtime_model_payload = original_select_runtime_model_payload
    main_module.select_vantage_modules_payload = original_select_vantage_modules_payload
    main_module.warmup_runtime_model_payload = original_warmup_runtime_model_payload
    main_module.asyncio.to_thread = original_asyncio_to_thread
    if original_socc_home is None:
        os.environ.pop("SOCC_HOME", None)
    else:
        os.environ["SOCC_HOME"] = original_socc_home
    tmpdir.cleanup()


print(f"\n{'='*60}")
print(f"SOC Copilot — Chat HTTP  ({len(resultados)} checks)")
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
