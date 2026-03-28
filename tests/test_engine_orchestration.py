"""
Valida a orquestracao de analise e re-draft centralizada no engine.
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from soc_copilot.modules import persistence
from socc.core import engine as engine_module
from socc.core.engine import (
    analyze_submission,
    build_chat_payload_response,
    chat_submission,
    ensure_session_id,
    generate_draft_submission,
    looks_like_payload,
    stream_chat_submission_events,
    stream_chat_payload_events,
)

PASS = "PASS"
FAIL = "FAIL"
resultados: list[tuple[str, str, str]] = []


def check(nome: str, condicao: bool, detalhe: str = "") -> None:
    status = PASS if condicao else FAIL
    resultados.append((status, nome, detalhe))


async def _collect_stream(payload: str, session_id: str, classificacao: str, cliente: str):
    events = []
    async for event in stream_chat_payload_events(
        message=payload,
        session_id=session_id,
        classificacao=classificacao,
        cliente=cliente,
        threat_intel_enabled=False,
        source="test_stream_chat_payload",
    ):
        events.append(event)
    return events


async def _collect_submission_stream(payload: str, session_id: str, classificacao: str, cliente: str):
    events = []
    async for event in stream_chat_submission_events(
        message=payload,
        session_id=session_id,
        classificacao=classificacao,
        cliente=cliente,
        threat_intel_enabled=False,
        source="test_stream_chat_submission",
    ):
        events.append(event)
    return events


tmpdir = tempfile.TemporaryDirectory()
db_path = Path(tmpdir.name) / "engine_orchestration.sqlite3"
original_db_path = persistence.DB_PATH

try:
    persistence.DB_PATH = db_path
    persistence.init_db()
    original_search_knowledge = engine_module.knowledge_base_runtime.search_knowledge_base
    original_format_knowledge = engine_module.knowledge_base_runtime.format_retrieval_context
    engine_module.knowledge_base_runtime.search_knowledge_base = lambda **kwargs: {
        "query_terms": ["firewall", "blocked", "10.0.0.5"],
        "sources": [
            {
                "source_id": "runbooks",
                "source_name": "Runbooks Internos",
                "title": "Firewall Block Playbook",
                "path": "/tmp/runbooks/firewall.md",
                "score": 8,
            }
        ],
        "matches": [
            {
                "source_id": "runbooks",
                "source_name": "Runbooks Internos",
                "title": "Firewall Block Playbook",
                "path": "/tmp/runbooks/firewall.md",
                "chunk_hash": "chunk-1",
                "chunk_index": 0,
                "score": 8,
                "matched_terms": ["firewall", "blocked"],
                "text": "Quando houver bloqueio em firewall com IP externo, validar regra, ativo afetado e necessidade de isolamento.",
            }
        ],
    }
    engine_module.knowledge_base_runtime.format_retrieval_context = lambda retrieval, **kwargs: (
        "1. Fonte: Runbooks Internos | Documento: Firewall Block Playbook\n"
        "Trecho: Quando houver bloqueio em firewall com IP externo, validar regra, ativo afetado e necessidade de isolamento."
    )

    payload = "srcip=10.0.0.5 dstip=192.168.1.20 action=blocked devname=FW1 logid=0001"
    response = analyze_submission(
        raw_input=payload,
        ofensa_id="CASE-ENG-1",
        cliente="Teste",
        regra="Bloqueio Firewall",
        classificacao="TP",
        threat_intel_enabled=False,
        persist_run=True,
        source="test_engine",
    )
    run = persistence.get_run(int(response.get("run_id") or 0))
    check("engine_orchestration_run_id", int(response.get("run_id") or 0) > 0)
    check("engine_orchestration_format", response.get("formato_detectado") in {"text", "json", "csv", "fortigate"})
    check("engine_orchestration_has_draft", bool(response.get("draft")))
    check("engine_orchestration_schema_valid", response.get("analysis_schema_valid") is True)
    check("engine_orchestration_persisted", bool(run) and run.get("ofensa_id") == "CASE-ENG-1")
    check("engine_orchestration_priority", isinstance(response.get("analysis_priority"), dict))
    check("engine_orchestration_knowledge_sources", bool(response.get("knowledge_sources")))
    check("engine_orchestration_knowledge_match", bool(response.get("knowledge_matches")))
    check("engine_orchestration_structured_sources", "knowledge_base" in (response.get("analysis_structured", {}).get("sources") or []))

    fields = dict(response.get("campos_extraidos") or {})
    fields["IOCs"] = {
        "ips_externos": ["10.0.0.5"],
        "ips_internos": [],
        "urls": [],
        "dominios": [],
        "hashes": [],
    }
    redraft = generate_draft_submission(
        fields=fields,
        ti_results={},
        classificacao="TP",
        regra="Bloqueio Firewall",
        cliente="Teste",
        run_id=int(response.get("run_id") or 0),
        persist_output=True,
        source="test_engine_draft",
    )
    check("engine_redraft_has_draft", bool(redraft.get("draft")))
    check("engine_redraft_has_trace", isinstance(redraft.get("analysis_trace"), dict))
    check("engine_redraft_template", bool(redraft.get("template_usado")))
    check("engine_redraft_priority", isinstance(redraft.get("analysis_priority"), dict))

    chat_payload = build_chat_payload_response(
        message=payload,
        session_id="chat-engine-1",
        skill="payload-triage",
        classificacao="AUTO",
        cliente="Teste",
        threat_intel_enabled=False,
        source="test_chat_payload",
    )
    chat_messages = persistence.list_chat_messages("chat-engine-1", limit=10)
    check("engine_chat_payload_type", chat_payload.get("type") == "analysis")
    check("engine_chat_payload_skill", chat_payload.get("skill") == "payload-triage")
    check("engine_chat_payload_draft", bool(chat_payload.get("draft")))
    check("engine_chat_payload_persisted", len(chat_messages) == 2)
    check("engine_chat_payload_priority", isinstance(chat_payload.get("analysis_priority"), dict))
    check("engine_chat_payload_knowledge", bool(chat_payload.get("knowledge_sources")))
    check("engine_looks_like_payload", looks_like_payload(payload) is True and looks_like_payload("olá") is False)
    check("engine_ensure_session_id", bool(ensure_session_id("")) and ensure_session_id("sessao-fixa") == "sessao-fixa")

    payload_submission = chat_submission(
        message=payload,
        session_id="chat-submission-payload",
        classificacao="AUTO",
        cliente="Teste",
        threat_intel_enabled=False,
        source="test_chat_submission_payload",
    )
    check("engine_chat_submission_payload", payload_submission.get("type") == "analysis")

    original_chat_reply = engine_module.chat_reply
    original_stream_chat_events = engine_module.stream_chat_events
    try:
        engine_module.chat_reply = lambda message, session_id="", cliente="": {
            "type": "message",
            "session_id": session_id or "msg-session",
            "skill": "triage",
            "content": f"eco: {message}",
        }
        engine_module.stream_chat_events = lambda message, session_id="", cliente="": iter(
            [
                {"event": "meta", "session_id": session_id or "stream-session", "skill": "triage"},
                {"event": "delta", "delta": "eco"},
                {"event": "final", "data": {"type": "message", "content": f"eco: {message}", "session_id": session_id or "stream-session"}},
            ]
        )
        message_submission = chat_submission(
            message="olá runtime",
            session_id="chat-submission-message",
            cliente="Teste",
        )
        check("engine_chat_submission_message", message_submission.get("content") == "eco: olá runtime")
        generic_stream = asyncio.run(
            _collect_submission_stream(
                "olá runtime",
                "chat-submission-stream",
                "AUTO",
                "Teste",
            )
        )
    finally:
        engine_module.chat_reply = original_chat_reply
        engine_module.stream_chat_events = original_stream_chat_events

    check("engine_chat_submission_stream_meta", generic_stream[0].get("event") == "meta")
    check("engine_chat_submission_stream_final", (generic_stream[-1].get("payload") or {}).get("content") == "eco: olá runtime")

    streamed = asyncio.run(
        _collect_stream(
            payload,
            "chat-engine-stream",
            "AUTO",
            "Teste",
        )
    )
    phase_events = [item for item in streamed if item.get("event") == "phase"]
    final_event = next((item for item in streamed if item.get("event") == "final"), {})
    check("engine_chat_stream_has_phases", len(phase_events) == 5)
    check("engine_chat_stream_final_type", (final_event.get("payload") or {}).get("type") == "analysis")

    submission_streamed = asyncio.run(
        _collect_submission_stream(
            payload,
            "chat-engine-stream-submission",
            "AUTO",
            "Teste",
        )
    )
    check("engine_submission_stream_payload_final", (submission_streamed[-1].get("payload") or {}).get("type") == "analysis")
except Exception as exc:
    check("engine_orchestration_flow", False, str(exc))
finally:
    try:
        engine_module.knowledge_base_runtime.search_knowledge_base = original_search_knowledge
        engine_module.knowledge_base_runtime.format_retrieval_context = original_format_knowledge
    except Exception:
        pass
    persistence.DB_PATH = original_db_path
    tmpdir.cleanup()


print(f"\n{'='*60}")
print(f"SOCC Runtime — Engine Orchestration  ({len(resultados)} checks)")
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
