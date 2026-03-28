"""
Valida operacoes auxiliares extraidas da camada web para o engine.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from soc_copilot.modules import persistence
from socc.core.engine import (
    analyze_submission,
    export_analysis_submission,
    list_chat_session_messages_payload,
    list_chat_sessions_payload,
    list_history_payload,
    prepare_analyze_raw_input,
    prepare_chat_submission_inputs,
    prepare_draft_submission_inputs,
    prepare_export_submission_inputs,
    prepare_feedback_submission_inputs,
    runtime_benchmark_payload,
    runtime_status_payload,
    resolve_bind_port,
    save_feedback_submission,
    save_note_submission,
)

PASS = "PASS"
FAIL = "FAIL"
resultados: list[tuple[str, str, str]] = []


def check(nome: str, condicao: bool, detalhe: str = "") -> None:
    status = PASS if condicao else FAIL
    resultados.append((status, nome, detalhe))


tmpdir = tempfile.TemporaryDirectory()
db_path = Path(tmpdir.name) / "engine_runtime_ops.sqlite3"
notes_dir = Path(tmpdir.name) / "notes"
original_db_path = persistence.DB_PATH

try:
    raw_from_text = prepare_analyze_raw_input(payload_raw="srcip=1.1.1.1 action=allow")
    raw_from_file = prepare_analyze_raw_input(
        payload_raw="ignorado",
        uploaded_bytes="srcip=2.2.2.2 action=deny".encode("utf-8"),
    )
    check("engine_ops_prepare_analyze_text", raw_from_text == "srcip=1.1.1.1 action=allow")
    check("engine_ops_prepare_analyze_upload_priority", raw_from_file == "srcip=2.2.2.2 action=deny")

    try:
        prepare_analyze_raw_input(payload_raw="   ")
        check("engine_ops_prepare_analyze_empty", False, "expected ValueError")
    except ValueError as exc:
        check("engine_ops_prepare_analyze_empty", "Nenhum payload" in str(exc))

    prepared_draft = prepare_draft_submission_inputs(
        campos_json='{"IP_Origem":"10.0.0.5"}',
        iocs_json='{"ips_externos":["8.8.8.8"],"ips_internos":[],"urls":[],"dominios":[],"hashes":[]}',
        ti_json='{"8.8.8.8":"ok"}',
    )
    check("engine_ops_prepare_draft_fields", isinstance(prepared_draft.get("fields"), dict))
    check("engine_ops_prepare_draft_iocs", bool((prepared_draft.get("fields") or {}).get("IOCs")))
    check("engine_ops_prepare_draft_private_ip", (prepared_draft.get("fields") or {}).get("IP_Origem_Privado") is True)

    try:
        prepare_draft_submission_inputs(campos_json="[]", iocs_json="{}", ti_json="{}")
        check("engine_ops_prepare_draft_invalid_shape", False, "expected ValueError")
    except ValueError as exc:
        check("engine_ops_prepare_draft_invalid_shape", "campos_json" in str(exc))

    prepared_feedback = prepare_feedback_submission_inputs(
        {"feedback_type": "correct", "run_id": 7, "comments": "ok"}
    )
    check("engine_ops_prepare_feedback_defaults", prepared_feedback.get("source") == "ui")
    check("engine_ops_prepare_feedback_run_id", prepared_feedback.get("run_id_raw") == 7)
    try:
        prepare_feedback_submission_inputs([])
        check("engine_ops_prepare_feedback_invalid", False, "expected ValueError")
    except ValueError as exc:
        check("engine_ops_prepare_feedback_invalid", "feedback" in str(exc).lower())

    prepared_export = prepare_export_submission_inputs(
        {"format": "markdown", "fields": {"foo": "bar"}, "analysis": {"summary": "x"}, "analysis_priority": {"score": 77}}
    )
    check("engine_ops_prepare_export_format", prepared_export.get("export_format") == "markdown")
    check("engine_ops_prepare_export_fields", prepared_export.get("fields", {}).get("foo") == "bar")
    check("engine_ops_prepare_export_priority", prepared_export.get("priority", {}).get("score") == 77)
    try:
        prepare_export_submission_inputs("x")
        check("engine_ops_prepare_export_invalid", False, "expected ValueError")
    except ValueError as exc:
        check("engine_ops_prepare_export_invalid", "export" in str(exc).lower())

    prepared_chat = prepare_chat_submission_inputs(
        {"message": "  ola runtime  ", "classificacao": "auto", "cliente": "Teste"}
    )
    check("engine_ops_prepare_chat_trim", prepared_chat.get("message") == "ola runtime")
    check("engine_ops_prepare_chat_upper", prepared_chat.get("classificacao") == "AUTO")
    try:
        prepare_chat_submission_inputs({"message": "   "})
        check("engine_ops_prepare_chat_empty", False, "expected ValueError")
    except ValueError as exc:
        check("engine_ops_prepare_chat_empty", "Mensagem vazia" in str(exc))

    persistence.DB_PATH = db_path
    persistence.init_db()

    analyzed = analyze_submission(
        raw_input="srcip=10.0.0.5 dstip=192.168.1.20 action=blocked devname=FW1 logid=0001",
        ofensa_id="CASE-OPS-1",
        cliente="Teste",
        regra="Bloqueio Firewall",
        classificacao="TP",
        threat_intel_enabled=False,
        persist_run=True,
        source="test_engine_ops",
    )
    run_id = int(analyzed.get("run_id") or 0)
    check("engine_ops_seed_run", run_id > 0)
    check("engine_ops_analysis_priority_present", isinstance(analyzed.get("analysis_priority"), dict))
    check("engine_ops_analysis_priority_score", isinstance((analyzed.get("analysis_priority") or {}).get("score"), int))
    check("engine_ops_operational_payload_present", isinstance(analyzed.get("operational_payload"), dict))
    check("engine_ops_operational_payload_disposition", bool((analyzed.get("operational_payload") or {}).get("disposition")))
    check("engine_ops_operational_payload_disposition_label", bool((analyzed.get("operational_payload") or {}).get("disposition_label")))
    check("engine_ops_operational_payload_template_kind", bool((analyzed.get("operational_payload") or {}).get("template_kind")))
    check("engine_ops_vantage_artifacts_present", isinstance(analyzed.get("vantage_artifacts"), dict))

    saved_note = save_note_submission(
        conteudo="Alerta consolidado para validacao.",
        ofensa_id="CASE-OPS-1",
        classificacao="TP",
        run_id=run_id,
        output_dir=notes_dir,
    )
    note_path = Path(saved_note.get("salvo_em") or "")
    check("engine_ops_note_saved", note_path.exists())
    check("engine_ops_note_name", str(saved_note.get("nome", "")).startswith("Ofensa_CASE-OPS-1"))

    feedback = save_feedback_submission(
        feedback_type="correct",
        run_id_raw=run_id,
        payload_hash="",
        verdict="suspeito",
        comments="Ainda precisa de validacao adicional.",
        source="test-suite",
    )
    check("engine_ops_feedback_saved", bool(feedback.get("feedback_id")))
    check("engine_ops_feedback_payload_hash", bool(feedback.get("payload_hash")))

    exported = export_analysis_submission(
        export_format="json",
        run_id=run_id,
        fields=analyzed.get("campos_extraidos", {}),
        ti_results=analyzed.get("ti_results", {}),
        analysis=analyzed.get("analysis", {}),
        structured=analyzed.get("analysis_structured", {}),
        priority=analyzed.get("analysis_priority", {}),
        trace=analyzed.get("analysis_trace", {}),
        operational_payload=analyzed.get("operational_payload", {}),
        draft=analyzed.get("draft", ""),
        cliente="Teste",
        regra="Bloqueio Firewall",
        classificacao="TP",
        payload_hash=analyzed.get("payload_hash", ""),
    )
    check("engine_ops_export_json", exported.get("format") == "json" and '"summary"' in str(exported.get("content")))
    check("engine_ops_export_priority", '"analysis_priority"' in str(exported.get("content")))
    check("engine_ops_export_operational_payload", '"operational_payload"' in str(exported.get("content")))

    exported_ticket = export_analysis_submission(
        export_format="ticket",
        run_id=run_id,
        fields=analyzed.get("campos_extraidos", {}),
        ti_results=analyzed.get("ti_results", {}),
        analysis=analyzed.get("analysis", {}),
        structured=analyzed.get("analysis_structured", {}),
        priority=analyzed.get("analysis_priority", {}),
        trace=analyzed.get("analysis_trace", {}),
        operational_payload=analyzed.get("operational_payload", {}),
        draft=analyzed.get("draft", ""),
        cliente="Teste",
        regra="Bloqueio Firewall",
        classificacao="TP",
        payload_hash=analyzed.get("payload_hash", ""),
    )
    check("engine_ops_export_ticket", exported_ticket.get("format") == "ticket" and "Destino Operacional:" in str(exported_ticket.get("content")))
    check("engine_ops_export_ticket_mime", exported_ticket.get("mime_type") == "text/plain")

    history = list_history_payload(limit=10)
    check("engine_ops_history_runs", any(item.get("id") == run_id for item in history.get("runs", [])))

    persistence.ensure_chat_session("ops-session", cliente="Teste", titulo="Sessao ops")
    persistence.save_chat_message("ops-session", "user", "Mensagem", skill="triage")
    sessions = list_chat_sessions_payload(limit=10)
    messages = list_chat_session_messages_payload("ops-session", limit=10)
    check("engine_ops_chat_sessions", any(item.get("session_id") == "ops-session" for item in sessions.get("sessions", [])))
    check("engine_ops_chat_messages", len(messages.get("messages", [])) == 1)

    runtime_status = runtime_status_payload()
    runtime_benchmark = runtime_benchmark_payload(concurrency=99, hold_ms=9999, probe=False)
    check("engine_ops_runtime_status_features", isinstance(runtime_status.get("features"), dict))
    check(
        "engine_ops_runtime_benchmark_clamped",
        ((runtime_benchmark.get("concurrency_benchmark") or {}).get("requested_concurrency") == 32),
    )

    original_can_bind = getattr(__import__("socc.core.engine", fromlist=["_can_bind"]), "_can_bind")
    import socc.core.engine as engine_module
    try:
        attempts: list[int] = []
        engine_module._can_bind = lambda host, port: attempts.append(port) or port == 8082  # type: ignore[assignment]
        resolved_port, adjusted = resolve_bind_port("127.0.0.1", 8080, max_attempts=5)
        check("engine_ops_resolve_bind_port_value", resolved_port == 8082)
        check("engine_ops_resolve_bind_port_adjusted", adjusted is True)
        check("engine_ops_resolve_bind_port_attempts", attempts == [8080, 8081, 8082])
    finally:
        engine_module._can_bind = original_can_bind  # type: ignore[assignment]
except Exception as exc:
    check("engine_runtime_ops_flow", False, str(exc))
finally:
    persistence.DB_PATH = original_db_path
    tmpdir.cleanup()


print(f"\n{'='*60}")
print(f"SOCC Runtime — Engine Runtime Ops  ({len(resultados)} checks)")
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
