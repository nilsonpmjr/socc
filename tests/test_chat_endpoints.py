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
        "messages": [{"role": "assistant", "content": "resposta final", "session_id": session_id}]
    }
    main_module.runtime_status_payload = lambda: {
        "runtime": {"provider": "stub", "model": "stub-model"},
        "features": {"chat_api": True, "chat_streaming": True},
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

        sync_response = await main_module.chat_endpoint(JsonRequest({"message": "teste endpoint", "session_id": "sessao-http"}))
        sync_body = getattr(sync_response, "body", b"").decode("utf-8", errors="replace")
        check("chat_http_sync_status", sync_response.status_code == 200)
        check("chat_http_sync_payload", "eco: teste endpoint" in sync_body)

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
