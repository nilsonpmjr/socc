from __future__ import annotations
import asyncio
import ipaddress
import json
import os
import re
import socket
from time import perf_counter, time
from typing import Any
from pathlib import Path

from soc_copilot.config import LLM_ENABLED, OUTPUT_DIR, SOC_PORT
from socc.cli.installer import runtime_home
from socc.cli.service_manager import service_status as runtime_service_status
from socc.core import agent_loader as agent_loader_runtime
from socc.core import analysis as analysis_runtime
from socc.core import chat as chat_runtime
from socc.core import knowledge_base as knowledge_base_runtime
from socc.core.contracts import (
    AnalysisEnvelope,
    ChatResponseEnvelope,
    GatewayRequestContract,
    GatewayResponseContract,
)
from socc.core import input_adapter as input_adapter_runtime
from socc.core import parser as parser_runtime
from socc.core import storage as storage_runtime
from socc.gateway import threat_intel as ti_gateway
from socc.gateway import vantage_api as vantage_gateway
from socc.gateway.llm_gateway import (
    list_backend_models,
    benchmark_runtime,
    record_analysis_event,
    resolve_api_key,
    resolve_auth_context,
    runtime_brief,
    runtime_status,
    warmup_backend_model,
)
from socc.utils.config_loader import load_environment, update_env_assignment
from socc.utils.feature_flags import feature_flags_payload


def build_app():
    from soc_copilot.main import app

    return app


def _can_bind(host: str, port: int) -> bool:
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        try:
            probe.close()
        except Exception:
            pass


def resolve_bind_port(host: str, preferred_port: int, max_attempts: int = 20) -> tuple[int, bool]:
    target_port = max(1, int(preferred_port))
    attempts = max(1, int(max_attempts))
    if _can_bind(host, target_port):
        return target_port, False
    for offset in range(1, attempts + 1):
        candidate = target_port + offset
        if _can_bind(host, candidate):
            return candidate, True
    return target_port, False


def serve(
    host: str = "127.0.0.1",
    port: int | None = None,
    reload: bool = False,
    log_level: str = "info",
) -> None:
    import uvicorn

    bind_port, adjusted = resolve_bind_port(host, port or SOC_PORT)
    if adjusted:
        print(
            f"Porta {port or SOC_PORT} ocupada; usando {bind_port} automaticamente."
        )
    print(f"\n  SOCC runtime\n  Access: http://{host}:{bind_port}\n")
    uvicorn.run(
        "soc_copilot.main:app",
        host=host,
        port=bind_port,
        reload=reload,
        log_level=log_level,
    )


def parse_payload(payload_text: str, raw_fields: dict[str, Any] | None = None) -> dict[str, Any]:
    return parser_runtime.parse_payload(payload_text, raw_fields=raw_fields)


def prepare_payload_input(raw_input: str) -> dict[str, Any]:
    fmt, raw_fields, raw_original = input_adapter_runtime.adapt(raw_input)
    fields = parse_payload(raw_original, raw_fields=raw_fields)
    return {
        "format": fmt,
        "raw_fields": raw_fields,
        "raw_text": raw_original,
        "fields": fields,
    }


def prepare_analyze_raw_input(
    *,
    payload_raw: str = "",
    uploaded_bytes: bytes | None = None,
    max_payload_bytes: int = 512 * 1024,
) -> str:
    raw = payload_raw
    if uploaded_bytes is not None:
        raw = uploaded_bytes.decode("utf-8", errors="replace")

    if not raw.strip():
        raise ValueError("Nenhum payload fornecido.")

    if len(raw.encode("utf-8", errors="replace")) > max_payload_bytes:
        raise ValueError(f"Payload excede o limite de {max_payload_bytes // 1024} KB.")

    return raw


def prepare_draft_submission_inputs(
    *,
    campos_json: str = "{}",
    iocs_json: str = "{}",
    ti_json: str = "{}",
) -> dict[str, Any]:
    try:
        fields = json.loads(campos_json)
        ti_results = json.loads(ti_json)
        iocs = json.loads(iocs_json)
    except Exception as exc:
        raise ValueError("JSON inválido nos campos recebidos.") from exc

    if not isinstance(fields, dict):
        raise ValueError("campos_json deve representar um objeto JSON.")
    if not isinstance(ti_results, dict):
        raise ValueError("ti_json deve representar um objeto JSON.")
    if not isinstance(iocs, dict):
        raise ValueError("iocs_json deve representar um objeto JSON.")

    return {
        "fields": _normalize_draft_fields(fields, iocs if iocs else None),
        "ti_results": ti_results,
    }


def prepare_feedback_submission_inputs(body: dict[str, Any] | None) -> dict[str, Any]:
    payload = {} if body is None else body
    if not isinstance(payload, dict):
        raise ValueError("Corpo JSON inválido para feedback.")
    return {
        "feedback_type": payload.get("feedback_type", ""),
        "run_id_raw": payload.get("run_id"),
        "session_id": payload.get("session_id", ""),
        "payload_hash": payload.get("payload_hash", ""),
        "verdict": payload.get("verdict", ""),
        "comments": payload.get("comments", ""),
        "source": payload.get("source", "ui"),
    }


def prepare_export_submission_inputs(body: dict[str, Any] | None) -> dict[str, Any]:
    payload = {} if body is None else body
    if not isinstance(payload, dict):
        raise ValueError("Corpo JSON inválido para exportação.")
    legacy_payload_key = "soar" + "_payload"
    return {
        "export_format": payload.get("format", "json"),
        "run_id": payload.get("run_id"),
        "session_id": payload.get("session_id", ""),
        "fields": payload.get("fields") or {},
        "ti_results": payload.get("ti_results") or {},
        "analysis": payload.get("analysis") or {},
        "structured": payload.get("analysis_structured") or {},
        "priority": payload.get("analysis_priority") or {},
        "trace": payload.get("analysis_trace") or {},
        "operational_payload": payload.get("operational_payload") or payload.get(legacy_payload_key) or {},
        "draft": payload.get("draft", "") or "",
        "cliente": payload.get("cliente", ""),
        "regra": payload.get("regra", ""),
        "classificacao": payload.get("classificacao", ""),
        "payload_hash": payload.get("payload_hash", ""),
    }


def prepare_chat_submission_inputs(body: dict[str, Any] | None) -> dict[str, Any]:
    payload = {} if body is None else body
    if not isinstance(payload, dict):
        raise ValueError("Corpo JSON inválido para chat.")
    message = str(payload.get("message", "") or "").strip()
    if not message:
        raise ValueError("Mensagem vazia")
    response_mode = str(payload.get("response_mode", "balanced") or "balanced").strip().lower()
    if response_mode not in {"fast", "balanced", "deep"}:
        response_mode = "balanced"
    return {
        "message": message,
        "session_id": str(payload.get("session_id", "") or ""),
        "classificacao": str(payload.get("classificacao", "auto") or "auto").upper(),
        "cliente": str(payload.get("cliente", "") or ""),
        "response_mode": response_mode,
        "selected_backend": str(payload.get("selected_backend", "") or "").strip(),
        "selected_model": str(payload.get("selected_model", "") or "").strip(),
    }


def infer_rule_context(regra: str, fields: dict[str, Any], raw_text: str) -> str:
    explicit = (regra or "").strip()
    if explicit:
        return explicit

    assunto = str(fields.get("Assunto", "") or "").strip()
    if assunto and assunto != "N/A":
        return assunto

    lowered = raw_text.lower()
    if any(token in lowered for token in ("tcp_port_scan", "port scan", "portscan", "varredura de portas")):
        return "TCP Port Scan"
    if any(token in lowered for token in ("ping sweep", "host discovery")):
        return "Ping Sweep"
    if any(token in lowered for token in ("dns ptr scan", "reverse dns scan", "ptr scan")):
        return "DNS PTR Scan"

    return ""


def _infer_ioc_type(ioc: str) -> str:
    normalized = str(ioc or "").strip()
    try:
        ipaddress.ip_address(normalized)
        return "ip"
    except ValueError:
        pass
    if len(normalized) in (32, 40, 64) and all(ch in "0123456789abcdefABCDEF" for ch in normalized):
        return "hash"
    if normalized.startswith(("http://", "https://")):
        return "url"
    return "domain"


def _infer_ti_tool(ioc: str, resultado: str) -> str:
    ioc_type = _infer_ioc_type(ioc)
    if ioc_type != "ip":
        return "batch_api"

    if any(
        marker in resultado
        for marker in (
            "Veredito:",
            "backend TI",
            "submeter lote",
            "aguardando resposta do lote TI",
        )
    ):
        return "batch_api"

    return "threat_check"


def _has_consultable_iocs(iocs: dict[str, Any]) -> bool:
    return bool(iocs.get("ips_externos") or iocs.get("dominios") or iocs.get("hashes"))


def _display_iocs(iocs: dict[str, Any]) -> dict[str, list[Any]]:
    return {
        "externos": list(iocs.get("ips_externos", [])),
        "internos": list(iocs.get("ips_internos", [])),
        "urls": list(iocs.get("urls", []))[:5],
        "dominios": list(iocs.get("dominios", []))[:5],
        "hashes": list(iocs.get("hashes", []))[:5],
    }


def _retrieve_knowledge(
    *,
    query_text: str,
    fields: dict[str, Any],
) -> dict[str, Any]:
    retrieval = knowledge_base_runtime.search_knowledge_base(
        query_text=query_text,
        fields=fields,
    )
    kb_context = knowledge_base_runtime.format_retrieval_context(retrieval)
    vantage = vantage_gateway.retrieve_context(query_text, fields=fields)
    context_parts = [section for section in (kb_context, str(vantage.get("context") or "")) if section]
    retrieval["context"] = "\n\n".join(context_parts).strip()
    retrieval["vantage"] = vantage
    retrieval["sources"] = list(retrieval.get("sources") or []) + list(vantage.get("sources") or [])
    retrieval["matches"] = list(retrieval.get("matches") or []) + list(vantage.get("matches") or [])
    return retrieval


def _build_operational_payload(
    *,
    metadata: dict[str, Any] | None = None,
    fields: dict[str, Any],
    analysis_payload: dict[str, Any],
    structured_analysis: dict[str, Any],
    analysis_priority: dict[str, Any],
    analysis_trace: dict[str, Any],
    draft: str = "",
) -> dict[str, Any]:
    return analysis_runtime.build_operational_payload(
        metadata=metadata,
        fields=fields,
        analysis_structured=structured_analysis,
        analysis_priority=analysis_priority,
        analysis_trace=analysis_trace,
        analysis_legacy=analysis_payload,
        draft=draft,
    )


def _normalize_draft_fields(fields: dict[str, Any], iocs: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized = dict(fields)
    if iocs:
        normalized["IOCs"] = iocs
    elif "IOCs" not in normalized:
        normalized["IOCs"] = {
            "ips_externos": [],
            "ips_internos": [],
            "urls": [],
            "dominios": [],
            "hashes": [],
        }

    if "IP_Origem_Privado" not in normalized:
        ip = str(normalized.get("IP_Origem", "") or "").strip()
        try:
            normalized["IP_Origem_Privado"] = ipaddress.ip_address(ip).is_private
        except Exception:
            normalized["IP_Origem_Privado"] = True
    return normalized


def normalize_classification_choice(classificacao: str, analysis: dict[str, Any]) -> str:
    normalized = classificacao if classificacao != "AUTO" else (
        str(
            ((analysis.get("classificacao_sugerida") or {}).get("tipo") or "TP")
        )
        .replace("True Positive", "TP")
        .replace("Benign True Positive", "BTP")
        .replace("False Positive", "FP")
        .replace("True Negative", "TN")
        .replace("Log Transmission Failure", "LTF")
    )
    if normalized not in {"TP", "BTP", "FP", "TN", "LTF"}:
        return "TP"
    return normalized


def _analysis_gateway_contract(*, payload_text: str, cliente: str, regra: str) -> dict[str, Any]:
    runtime = runtime_brief()
    return GatewayRequestContract(
        provider=str(runtime.get("provider", "")),
        model=str(runtime.get("model", "")),
        messages=[
            {
                "role": "user",
                "content": payload_text[:400],
            }
        ],
        stream=False,
        tools=[],
        metadata={
            "entrypoint": "analyze_payload",
            "cliente": cliente,
            "regra": regra,
        },
    ).to_dict()


def _chat_gateway_contract(
    *,
    stream: bool,
    success: bool,
    error: str = "",
    runtime_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    runtime = runtime_override if isinstance(runtime_override, dict) else runtime_brief()
    return GatewayResponseContract(
        provider=str(runtime.get("provider", "")),
        model=str(runtime.get("model", "")),
        requested_device=str(runtime.get("device", "")),
        effective_device=str(runtime.get("device", "")),
        success=success,
        fallback_used=not bool(LLM_ENABLED),
        error=error,
        metadata={
            "entrypoint": "chat_reply",
            "stream": stream,
        },
    ).to_dict()


def analyze_payload(
    payload_text: str,
    raw_fields: dict[str, Any] | None = None,
    cliente: str = "",
    regra: str = "",
    classificacao: str = "TP",
    ti_results: dict[str, str] | None = None,
    analysis: dict[str, Any] | None = None,
    include_draft: bool = True,
    record_event: bool = True,
) -> dict[str, Any]:
    started = perf_counter()
    effective_raw_fields = raw_fields
    effective_payload_text = payload_text
    if raw_fields is None:
        prepared = prepare_payload_input(payload_text)
        effective_raw_fields = dict(prepared.get("raw_fields") or {})
        effective_payload_text = str(prepared.get("raw_text") or payload_text)
        fields = dict(prepared.get("fields") or {})
    else:
        fields = parse_payload(payload_text, raw_fields)
    knowledge = _retrieve_knowledge(
        query_text=effective_payload_text,
        fields=fields,
    )
    regra_contexto = regra or fields.get("Assunto", "")
    pack = analysis_runtime.load_rule_pack(regra_contexto, cliente)
    analysis_payload = analysis or analysis_runtime.run_analysis(
        fields=fields,
        ti_results=ti_results or {},
        raw_text=effective_payload_text,
        regra=regra_contexto,
        cliente=cliente,
        pack=pack,
        knowledge_context=str(knowledge.get("context") or ""),
        knowledge_sources=", ".join(
            str(item.get("source_name") or item.get("source_id") or "")
            for item in (knowledge.get("sources") or [])
            if str(item.get("source_name") or item.get("source_id") or "")
        ),
    )
    if isinstance(analysis_payload, dict):
        analysis_payload["knowledge_matches"] = list(knowledge.get("matches") or [])
        analysis_payload["knowledge_sources"] = list(knowledge.get("sources") or [])
        analysis_payload["knowledge_query_terms"] = list(knowledge.get("query_terms") or [])
    analysis_payload = analysis_runtime.enrich_analysis_with_contexts(
        analysis=analysis_payload,
        fields=fields,
        ti_results=ti_results or {},
        raw_text=effective_payload_text,
    )
    structured_analysis = analysis_runtime.build_structured_analysis(
        analysis=analysis_payload,
        fields=fields,
        ti_results=ti_results or {},
    )
    analysis_priority = analysis_runtime.build_analysis_priority(
        analysis=analysis_payload,
        fields=fields,
        ti_results=ti_results or {},
    )
    analysis_trace = analysis_runtime.build_analysis_trace(
        fields=fields,
        analysis=analysis_payload,
        ti_results=ti_results or {},
    )
    result_metadata = {
        "cliente": cliente,
        "regra": regra_contexto,
        "classificacao": classificacao,
    }

    result = AnalysisEnvelope(
        fields=fields,
        analysis=analysis_payload,
        analysis_structured=structured_analysis,
        analysis_priority=analysis_priority,
        analysis_trace=analysis_trace,
        analysis_schema_valid=not analysis_runtime.validate_structured_analysis(structured_analysis),
        runtime=runtime_brief(),
        rule_pack={
            "modelo_aderente": pack.modelo_aderente,
            "modelo_nome": pack.modelo_nome,
            "is_icatu": pack.is_icatu,
        },
        gateway=_analysis_gateway_contract(
            payload_text=effective_payload_text,
            cliente=cliente,
            regra=regra_contexto,
        ),
        tool_results=[],
    ).to_dict()
    if record_event:
        record_analysis_event(
            source="core_engine",
            latency_ms=(perf_counter() - started) * 1000,
            success=True,
            schema_valid=result["analysis_schema_valid"],
            threat_intel_used=bool(ti_results),
        )

    if include_draft:
        draft_text, template_used = analysis_runtime.generate_draft(
            classificacao,
            fields,
            ti_results or {},
            pack,
            analysis_payload,
        )
        result["draft"] = draft_text
        result["template_used"] = template_used

    result["operational_payload"] = _build_operational_payload(
        metadata=result_metadata,
        fields=fields,
        analysis_payload=analysis_payload,
        structured_analysis=structured_analysis,
        analysis_priority=analysis_priority,
        analysis_trace=analysis_trace,
        draft=str(result.get("draft") or ""),
    )

    result["knowledge_matches"] = list(knowledge.get("matches") or [])
    result["knowledge_sources"] = list(knowledge.get("sources") or [])
    result["knowledge_query_terms"] = list(knowledge.get("query_terms") or [])
    result["vantage_context"] = str((knowledge.get("vantage") or {}).get("context") or "")
    result["vantage_sources"] = list((knowledge.get("vantage") or {}).get("sources") or [])
    result["vantage_modules"] = list((knowledge.get("vantage") or {}).get("modules") or [])
    result["vantage_artifacts"] = dict((knowledge.get("vantage") or {}).get("artifacts") or {})

    return result


def analyze_submission(
    *,
    raw_input: str,
    ofensa_id: str = "",
    cliente: str = "",
    regra: str = "",
    classificacao: str = "TP",
    threat_intel_enabled: bool = True,
    persist_run: bool = True,
    source: str = "api_analyze",
) -> dict[str, Any]:
    started = perf_counter()
    prepared = prepare_payload_input(raw_input)
    fmt = str(prepared["format"])
    raw_original = str(prepared["raw_text"])
    raw_fields = dict(prepared["raw_fields"])
    fields = dict(prepared["fields"])
    regra_contexto = infer_rule_context(regra, fields, raw_original)
    iocs = fields.get("IOCs", {})
    ti_results: dict[str, str] = {}
    if threat_intel_enabled and isinstance(iocs, dict) and _has_consultable_iocs(iocs):
        ti_results = ti_gateway.enrich_iocs(iocs)

    result = analyze_payload(
        payload_text=raw_original,
        raw_fields=raw_fields,
        cliente=cliente,
        regra=regra_contexto,
        classificacao=classificacao,
        ti_results=ti_results,
        include_draft=True,
        record_event=False,
    )
    analysis_schema_errors = analysis_runtime.validate_structured_analysis(
        result.get("analysis_structured", {})
    )
    payload_hash = storage_runtime.hash_input(raw_original)

    run_id = 0
    if persist_run:
        run_id = storage_runtime.save_run(
            ofensa_id=ofensa_id,
            cliente=cliente,
            regra=regra_contexto,
            raw_input=raw_original,
            classificacao=classificacao,
            template_usado=str(result.get("template_used") or ""),
        )
        for ioc, resultado in ti_results.items():
            storage_runtime.save_intel(
                run_id=run_id,
                ioc=ioc,
                tipo=_infer_ioc_type(ioc),
                ferramenta=_infer_ti_tool(ioc, resultado),
                resultado=resultado,
            )
        storage_runtime.save_analysis(
            run_id=run_id,
            analysis=result.get("analysis", {}),
            structured_analysis=result.get("analysis_structured", {}),
        )
        storage_runtime.save_output(
            run_id=run_id,
            tipo_saida=classificacao,
            conteudo=str(result.get("draft") or ""),
        )

    record_analysis_event(
        source=source,
        latency_ms=(perf_counter() - started) * 1000,
        success=True,
        schema_valid=not analysis_schema_errors,
        threat_intel_used=bool(ti_results),
        payload_hash=payload_hash,
    )

    return {
        "run_id": run_id,
        "formato_detectado": fmt,
        "campos_extraidos": {
            key: value for key, value in result.get("fields", {}).items() if key != "IOCs"
        },
        "iocs": _display_iocs(result.get("fields", {}).get("IOCs", {})),
        "ti_results": ti_results,
        "analysis": result.get("analysis", {}),
        "analysis_structured": result.get("analysis_structured", {}),
        "analysis_priority": result.get("analysis_priority", {}),
        "analysis_trace": result.get("analysis_trace", {}),
        "operational_payload": result.get("operational_payload", {}),
        "analysis_schema_valid": not analysis_schema_errors,
        "analysis_schema_errors": analysis_schema_errors,
        "knowledge_matches": result.get("knowledge_matches", []),
        "knowledge_sources": result.get("knowledge_sources", []),
        "knowledge_query_terms": result.get("knowledge_query_terms", []),
        "runtime": result.get("runtime", runtime_brief()),
        "modelo_aderente": (result.get("rule_pack") or {}).get("modelo_nome") or None,
        "regra_contexto": regra_contexto or None,
        "draft": result.get("draft", ""),
        "classificacao": classificacao,
        "template_usado": result.get("template_used"),
        "payload_hash": payload_hash,
        "vantage_context": result.get("vantage_context", ""),
        "vantage_sources": result.get("vantage_sources", []),
        "vantage_modules": result.get("vantage_modules", []),
        "vantage_artifacts": result.get("vantage_artifacts", {}),
    }


def generate_draft_submission(
    *,
    fields: dict[str, Any],
    ti_results: dict[str, str] | None = None,
    classificacao: str = "TP",
    regra: str = "",
    cliente: str = "",
    run_id: int = 0,
    persist_output: bool = True,
    source: str = "api_draft",
) -> dict[str, Any]:
    started = perf_counter()
    normalized_fields = _normalize_draft_fields(fields)
    effective_ti_results = ti_results or {}
    regra_contexto = infer_rule_context(regra, normalized_fields, "")
    pack = analysis_runtime.load_rule_pack(regra=regra_contexto, cliente=cliente)
    analysis = analysis_runtime.run_analysis(
        fields=normalized_fields,
        ti_results=effective_ti_results,
        raw_text="",
        regra=regra_contexto,
        cliente=cliente,
        pack=pack,
    )
    analysis = analysis_runtime.enrich_analysis_with_contexts(
        analysis=analysis,
        fields=normalized_fields,
        ti_results=effective_ti_results,
        raw_text="",
    )
    analysis_structured = analysis_runtime.build_structured_analysis(
        analysis=analysis,
        fields=normalized_fields,
        ti_results=effective_ti_results,
    )
    analysis_priority = analysis_runtime.build_analysis_priority(
        analysis=analysis,
        fields=normalized_fields,
        ti_results=effective_ti_results,
    )
    analysis_trace = analysis_runtime.build_analysis_trace(
        fields=normalized_fields,
        analysis=analysis,
        ti_results=effective_ti_results,
    )
    draft_text, template_usado = analysis_runtime.generate_draft(
        classificacao=classificacao,
        fields=normalized_fields,
        ti_results=effective_ti_results,
        pack=pack,
        analysis=analysis,
    )
    if run_id and persist_output:
        storage_runtime.save_output(
            run_id=run_id,
            tipo_saida=f"{classificacao}_final",
            conteudo=draft_text,
        )
    operational_payload = _build_operational_payload(
        metadata={
            "cliente": cliente,
            "regra": regra_contexto,
            "classificacao": classificacao,
            "run_id": run_id,
        },
        fields=normalized_fields,
        analysis_payload=analysis,
        structured_analysis=analysis_structured,
        analysis_priority=analysis_priority,
        analysis_trace=analysis_trace,
        draft=draft_text,
    )
    record_analysis_event(
        source=source,
        latency_ms=(perf_counter() - started) * 1000,
        success=True,
        schema_valid=not analysis_runtime.validate_structured_analysis(analysis_structured),
        threat_intel_used=bool(effective_ti_results),
        payload_hash="",
    )
    return {
        "draft": draft_text,
        "template_usado": template_usado,
        "classificacao": classificacao,
        "analysis_structured": analysis_structured,
        "analysis_priority": analysis_priority,
        "analysis_trace": analysis_trace,
        "operational_payload": operational_payload,
        "runtime": runtime_brief(),
    }


def build_chat_payload_response(
    *,
    message: str,
    session_id: str,
    skill: str,
    classificacao: str = "AUTO",
    cliente: str = "",
    response_mode: str = "balanced",
    threat_intel_enabled: bool = True,
    source: str = "chat_payload",
) -> dict[str, Any]:
    started = perf_counter()
    storage_runtime.ensure_chat_session(
        session_id=session_id,
        cliente=cliente,
        titulo=message[:80],
    )

    prepared = prepare_payload_input(message)
    raw_text = str(prepared["raw_text"])
    fields = dict(prepared["fields"])
    regra_contexto = infer_rule_context("", fields, raw_text)
    iocs = fields.get("IOCs", {})
    ti_results: dict[str, str] = {}
    if threat_intel_enabled and isinstance(iocs, dict) and _has_consultable_iocs(iocs):
        ti_results = ti_gateway.enrich_iocs(iocs)

    analysis_result = analyze_payload(
        payload_text=raw_text,
        raw_fields=dict(prepared["raw_fields"]),
        cliente=cliente,
        regra=regra_contexto,
        classificacao="TP",
        ti_results=ti_results,
        include_draft=False,
        record_event=False,
    )
    analysis = analysis_result.get("analysis", {})
    cls = normalize_classification_choice(classificacao, analysis)
    pack = analysis_runtime.load_rule_pack(regra=regra_contexto, cliente=cliente)
    draft, template = analysis_runtime.generate_draft(
        cls,
        dict(analysis_result.get("fields", {})),
        ti_results,
        pack,
        analysis,
    )

    response_payload = {
        "type": "analysis",
        "session_id": session_id,
        "skill": skill,
        "classificacao": cls,
        "confianca": ((analysis.get("classificacao_sugerida") or {}).get("confianca", 0)),
        "campos": {
            key: value for key, value in (analysis_result.get("fields", {}) or {}).items() if key != "IOCs"
        },
        "iocs": {
            "externos": list((iocs or {}).get("ips_externos", [])),
            "internos": list((iocs or {}).get("ips_internos", [])),
            "dominios": list((iocs or {}).get("dominios", [])),
            "hashes": list((iocs or {}).get("hashes", [])),
        },
        "ti_results": ti_results,
        "mitre": analysis.get("mitre_candidato", {}),
        "analise_tecnica": ((analysis.get("resumo_factual") or {}).get("o_que", "")),
        "hipoteses": analysis.get("hipoteses", []),
        "lacunas": analysis.get("lacunas", []),
        "analysis_legacy": analysis,
        "analysis_structured": analysis_result.get("analysis_structured", {}),
        "analysis_priority": analysis_result.get("analysis_priority", {}),
        "analysis_trace": analysis_result.get("analysis_trace", {}),
        "operational_payload": _build_operational_payload(
            metadata={
                "cliente": cliente,
                "regra": regra_contexto,
                "classificacao": cls,
                "session_id": session_id,
            },
            fields=dict(analysis_result.get("fields", {}) or {}),
            analysis_payload=analysis,
            structured_analysis=dict(analysis_result.get("analysis_structured", {}) or {}),
            analysis_priority=dict(analysis_result.get("analysis_priority", {}) or {}),
            analysis_trace=dict(analysis_result.get("analysis_trace", {}) or {}),
            draft=draft,
        ),
        "knowledge_matches": analysis_result.get("knowledge_matches", []),
        "knowledge_sources": analysis_result.get("knowledge_sources", []),
        "knowledge_query_terms": analysis_result.get("knowledge_query_terms", []),
        "vantage_context": analysis_result.get("vantage_context", ""),
        "vantage_sources": analysis_result.get("vantage_sources", []),
        "vantage_modules": analysis_result.get("vantage_modules", []),
        "vantage_artifacts": analysis_result.get("vantage_artifacts", {}),
        "draft": draft,
        "template": template,
        "runtime": analysis_result.get("runtime", runtime_brief()),
        "modelo_aderente": ((analysis_result.get("rule_pack") or {}).get("modelo_nome") or ""),
        "regra_contexto": regra_contexto,
        "formato_detectado": str(prepared["format"]),
        "payload_hash": storage_runtime.hash_input(raw_text),
        "response_mode": response_mode,
    }
    storage_runtime.save_chat_message(
        session_id=session_id,
        role="user",
        content=message,
        skill=skill,
        metadata={"type": "message"},
    )
    storage_runtime.save_chat_message(
        session_id=session_id,
        role="assistant",
        content=draft,
        skill=skill,
        metadata=response_payload,
    )
    record_analysis_event(
        source=source,
        latency_ms=(perf_counter() - started) * 1000,
        success=True,
        schema_valid=bool(analysis_result.get("analysis_schema_valid")),
        threat_intel_used=bool(ti_results),
        payload_hash=str(response_payload.get("payload_hash") or ""),
    )
    return response_payload


def ensure_session_id(session_id: str = "") -> str:
    return str(session_id or int(time() * 1000))


def _merge_chat_metadata(
    response_metadata: dict[str, Any] | None = None,
    *,
    cliente: str = "",
    response_mode: str = "",
    selected_backend: str = "",
    selected_model: str = "",
) -> dict[str, Any]:
    metadata = dict(response_metadata or {})
    if cliente:
        metadata.setdefault("cliente", cliente)
    if response_mode:
        metadata.setdefault("response_mode", response_mode)
    if selected_backend:
        metadata.setdefault("selected_backend", selected_backend)
    if selected_model:
        metadata.setdefault("selected_model", selected_model)
    return metadata


def chat_submission(
    *,
    message: str,
    session_id: str = "",
    classificacao: str = "AUTO",
    cliente: str = "",
    response_mode: str = "balanced",
    selected_backend: str = "",
    selected_model: str = "",
    threat_intel_enabled: bool = True,
    source: str = "chat_payload",
) -> dict[str, Any]:
    effective_session = ensure_session_id(session_id)
    if looks_like_payload(message):
        return build_chat_payload_response(
            message=message,
            session_id=effective_session,
            skill=chat_runtime.select_skill(message),
            classificacao=classificacao,
            cliente=cliente,
            response_mode=response_mode,
            threat_intel_enabled=threat_intel_enabled,
            source=source,
        )
    return chat_reply(
        message=message,
        session_id=effective_session,
        cliente=cliente,
        response_mode=response_mode,
        selected_backend=selected_backend,
        selected_model=selected_model,
    )


def looks_like_payload(text: str) -> bool:
    import re as regex

    sample = (text or "")[:1000]
    return bool(
        regex.search(r'(\w+=(?:"[^"]*"|[^\s]+)\s+){3,}', sample)
        or regex.search(r'<\d{3}>', sample)
        or regex.search(r'srcip=|dstip=|action=|devname=|logid=', sample)
        or regex.search(r'SubjectUserName|EventRecordID|TargetUserName', sample)
        or regex.search(r'"type"\s*:\s*"(?:alert|event|log|security)"', sample)
        or (len(sample) > 300 and sample.count('=') > 5)
    )


async def stream_chat_payload_events(
    *,
    message: str,
    session_id: str,
    classificacao: str,
    cliente: str,
    response_mode: str = "balanced",
    selected_backend: str = "",
    selected_model: str = "",
    threat_intel_enabled: bool = True,
    source: str = "chat_payload",
):
    selected_skill = chat_runtime.select_skill(message)
    yield {
        "event": "meta",
        "payload": {
            "session_id": session_id,
            "skill": selected_skill,
            "runtime": runtime_brief(),
            "response_mode": response_mode,
            "selected_backend": selected_backend,
            "selected_model": selected_model,
        },
    }
    for step, phase, label in (
        (0, "detect", "Detectando formato..."),
        (1, "parse", "Extraindo campos..."),
        (2, "ti", "Consultando TI..."),
        (3, "analysis", "Classificando..."),
        (4, "draft", "Gerando draft..."),
    ):
        yield {
            "event": "phase",
            "payload": {"step": step, "phase": phase, "label": label},
        }
    response_payload = await asyncio.to_thread(
        build_chat_payload_response,
        message=message,
        session_id=session_id,
        skill=selected_skill,
        classificacao=classificacao,
        cliente=cliente,
        response_mode=response_mode,
        threat_intel_enabled=threat_intel_enabled,
        source=source,
    )
    yield {"event": "final", "payload": response_payload}


async def stream_chat_submission_events(
    *,
    message: str,
    session_id: str = "",
    classificacao: str = "AUTO",
    cliente: str = "",
    response_mode: str = "balanced",
    selected_backend: str = "",
    selected_model: str = "",
    threat_intel_enabled: bool = True,
    source: str = "chat_payload",
):
    effective_session = ensure_session_id(session_id)
    if looks_like_payload(message):
        async for event in stream_chat_payload_events(
            message=message,
            session_id=effective_session,
            classificacao=classificacao,
            cliente=cliente,
            response_mode=response_mode,
            selected_backend=selected_backend,
            selected_model=selected_model,
            threat_intel_enabled=threat_intel_enabled,
            source=source,
        ):
            yield event
        return

    for event in stream_chat_events(
        message=message,
        session_id=effective_session,
        cliente=cliente,
        response_mode=response_mode,
        selected_backend=selected_backend,
        selected_model=selected_model,
    ):
        event_name = str(event.get("event") or "message")
        if event_name == "final":
            data = event.get("data")
            payload = dict(data) if isinstance(data, dict) else {}
        else:
            payload = {key: value for key, value in event.items() if key != "event"}
        yield {"event": event_name, "payload": payload}


def save_note_submission(
    *,
    conteudo: str,
    ofensa_id: str = "",
    classificacao: str = "",
    run_id: int = 0,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    if not (conteudo or "").strip():
        raise ValueError("Conteúdo vazio.")

    base_dir = (output_dir or OUTPUT_DIR).resolve()
    base_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time_filename()
    ofensa_safe = re.sub(r"[^\w\-]", "_", ofensa_id or "SEM_ID")[:40]
    cls_safe = re.sub(r"[^\w]", "_", classificacao)[:10]
    filename = f"Ofensa_{ofensa_safe}_{cls_safe}_{timestamp}.txt"
    target_path = base_dir / filename
    if not str(target_path.resolve()).startswith(str(base_dir)):
        raise ValueError("Caminho de destino inválido.")

    target_path.write_text(conteudo, encoding="utf-8")
    if run_id:
        storage_runtime.save_output(
            run_id=run_id,
            tipo_saida=f"{classificacao}_salvo",
            conteudo=conteudo,
            salvo_em=str(target_path),
        )
    return {"salvo_em": str(target_path), "nome": filename}


def list_history_payload(limit: int = 50) -> dict[str, Any]:
    return {"runs": storage_runtime.list_runs(limit=max(1, min(limit, 200)))}


def save_feedback_submission(
    *,
    feedback_type: str,
    run_id_raw: Any = None,
    session_id: str = "",
    payload_hash: str = "",
    verdict: str = "",
    comments: str = "",
    source: str = "ui",
) -> dict[str, Any]:
    feedback_type_norm = str(feedback_type or "").strip().lower()
    session_id_norm = str(session_id or "").strip()
    payload_hash_norm = str(payload_hash or "").strip()
    verdict_norm = str(verdict or "").strip().lower()
    comments_norm = str(comments or "").strip()
    source_norm = str(source or "ui").strip() or "ui"

    allowed_feedback = {"approve", "correct", "reject"}
    allowed_verdicts = {"", "benigno", "suspeito", "malicioso", "inconclusivo"}
    if feedback_type_norm not in allowed_feedback:
        raise ValueError("feedback_type inválido.")
    if verdict_norm not in allowed_verdicts:
        raise ValueError("verdict inválido.")

    run_id: int | None = None
    if run_id_raw not in (None, "", 0, "0"):
        try:
            run_id = int(run_id_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("run_id inválido.") from exc

    if not run_id and not session_id_norm:
        raise ValueError("run_id ou session_id é obrigatório para vincular o feedback.")

    if run_id and not payload_hash_norm:
        run = storage_runtime.get_run(run_id)
        if not run:
            raise LookupError("run_id não encontrado.")
        payload_hash_norm = str(run.get("input_hash") or "")

    feedback_id = storage_runtime.save_feedback(
        feedback_type=feedback_type_norm,
        run_id=run_id,
        session_id=session_id_norm,
        payload_hash=payload_hash_norm,
        verdict_correction=verdict_norm,
        comments=comments_norm,
        source=source_norm,
    )
    return {
        "feedback_id": feedback_id,
        "status": "saved",
        "feedback_type": feedback_type_norm,
        "run_id": run_id,
        "session_id": session_id_norm or None,
        "payload_hash": payload_hash_norm or None,
        "verdict": verdict_norm or None,
    }


def export_analysis_submission(
    *,
    export_format: str,
    run_id: Any = None,
    session_id: str = "",
    fields: dict[str, Any] | None = None,
    ti_results: dict[str, str] | None = None,
    analysis: dict[str, Any] | None = None,
    structured: dict[str, Any] | None = None,
    priority: dict[str, Any] | None = None,
    trace: dict[str, Any] | None = None,
    operational_payload: dict[str, Any] | None = None,
    draft: str = "",
    cliente: str = "",
    regra: str = "",
    classificacao: str = "",
    payload_hash: str = "",
) -> dict[str, Any]:
    export_format_norm = str(export_format or "json").strip().lower()
    if export_format_norm not in {"json", "markdown", "md", "ticket"}:
        raise ValueError("format inválido.")

    fields_payload = fields or {}
    ti_payload = ti_results or {}
    analysis_payload = analysis or {}
    structured_payload = structured or {}
    priority_payload = priority or {}
    trace_payload = trace or {}
    operational_payload_data = operational_payload or {}
    if not structured_payload and analysis_payload:
        structured_payload = analysis_runtime.build_structured_analysis(
            analysis=analysis_payload,
            fields=fields_payload,
            ti_results=ti_payload,
        )
    if not priority_payload and analysis_payload:
        priority_payload = analysis_runtime.build_analysis_priority(
            analysis=analysis_payload,
            fields=fields_payload,
            ti_results=ti_payload,
        )
    if not trace_payload and analysis_payload:
        trace_payload = analysis_runtime.build_analysis_trace(
            fields=fields_payload,
            analysis=analysis_payload,
            ti_results=ti_payload,
        )
    if not operational_payload_data and (analysis_payload or structured_payload):
        operational_payload_data = _build_operational_payload(
            metadata={
                "run_id": run_id,
                "session_id": str(session_id or "").strip(),
                "cliente": cliente,
                "regra": regra,
                "classificacao": classificacao,
                "payload_hash": payload_hash,
            },
            fields=fields_payload,
            analysis_payload=analysis_payload,
            structured_analysis=structured_payload,
            analysis_priority=priority_payload,
            analysis_trace=trace_payload,
            draft=str(draft or ""),
        )

    bundle = analysis_runtime.build_export_bundle(
        metadata={
            "run_id": run_id,
            "session_id": str(session_id or "").strip(),
            "cliente": cliente,
            "regra": regra,
            "classificacao": classificacao,
            "payload_hash": payload_hash,
        },
        fields=fields_payload,
        ti_results=ti_payload,
        analysis_structured=structured_payload,
        analysis_priority=priority_payload,
        analysis_trace=trace_payload,
        operational_payload=operational_payload_data,
        draft=str(draft or ""),
        analysis_legacy=analysis_payload,
    )
    content, mime_type = analysis_runtime.serialize_export(bundle, export_format_norm)
    filename = analysis_runtime.export_filename(
        export_format_norm,
        run_id=run_id,
        session_id=session_id,
    )
    if run_id not in (None, "", 0, "0"):
        try:
            storage_runtime.save_output(
                run_id=int(run_id),
                tipo_saida=f"analysis_export_{'json' if export_format_norm == 'json' else 'md' if export_format_norm in {'markdown', 'md'} else 'ticket'}",
                conteudo=content,
            )
        except (TypeError, ValueError):
            pass
    return {
        "filename": filename,
        "mime_type": mime_type,
        "format": "json" if export_format_norm == "json" else "markdown" if export_format_norm in {"markdown", "md"} else "ticket",
        "content": content,
    }


def list_chat_sessions_payload(limit: int = 50) -> dict[str, Any]:
    try:
        sessions = storage_runtime.list_chat_sessions(limit=limit)
        return {"sessions": sessions, "error": ""}
    except Exception as exc:
        return {"sessions": [], "error": str(exc)}


def list_chat_session_messages_payload(session_id: str, limit: int = 100) -> dict[str, Any]:
    capped = max(1, min(limit, 200))
    try:
        messages = storage_runtime.list_chat_messages(session_id=session_id, limit=capped)
        return {
            "session_id": session_id,
            "messages": messages,
            "error": "",
        }
    except Exception as exc:
        return {
            "session_id": session_id,
            "messages": [],
            "error": str(exc),
        }


def _runtime_model_profiles() -> dict[str, str]:
    default_model = os.getenv("OLLAMA_MODEL", "").strip()
    return {
        "fast": os.getenv("SOCC_OLLAMA_FAST_MODEL", "llama3.2:3b").strip(),
        "balanced": os.getenv("SOCC_OLLAMA_BALANCED_MODEL", default_model).strip() or default_model,
        "deep": os.getenv("SOCC_OLLAMA_DEEP_MODEL", default_model).strip() or default_model,
        "default": default_model,
    }


def _runtime_model_options(
    catalog: dict[str, Any] | None = None,
    *,
    runtime_payload: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    profiles = _runtime_model_profiles()
    current_runtime = ((runtime_payload or {}).get("runtime") or {}) if isinstance(runtime_payload, dict) else {}
    current_backend = str(current_runtime.get("backend") or current_runtime.get("provider") or "ollama").strip()
    current_model = str(current_runtime.get("model") or "").strip()

    model_modes: dict[str, list[str]] = {}
    for mode in ("fast", "balanced", "deep"):
        model_name = str(profiles.get(mode) or "").strip()
        if not model_name:
            continue
        bucket = model_modes.setdefault(model_name, [])
        if mode not in bucket:
            bucket.append(mode)

    available: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in list((catalog or {}).get("models") or []):
        model_name = str((item or {}).get("name") or "").strip()
        if not model_name:
            continue
        option_id = f"ollama::{model_name}"
        if option_id in seen_ids:
            continue
        seen_ids.add(option_id)
        mapped_modes = model_modes.get(model_name, [])
        preferred_mode = mapped_modes[0] if mapped_modes else "balanced"
        summary = "Local"
        if mapped_modes:
            summary = f"Local · {' / '.join(mode.title() for mode in mapped_modes)}"
        available.append(
            {
                "id": option_id,
                "label": model_name,
                "model": model_name,
                "backend": "ollama",
                "provider": "ollama",
                "response_mode": preferred_mode,
                "cloud": False,
                "configured": True,
                "disabled_reason": "",
                "summary": summary,
                "selected": current_backend == "ollama" and current_model == model_name,
            }
        )

    anthropic_auth = resolve_auth_context("anthropic")
    anthropic_ready = bool(anthropic_auth.get("credential"))
    anthropic_auth_label = "OAuth" if anthropic_auth.get("method") == "oauth" else "API key"
    for label, model_name, mode in (
        ("Claude Haiku 4.5", "claude-haiku-4-5-20251001", "fast"),
        ("Claude Sonnet 4", "claude-sonnet-4-20250514", "balanced"),
        ("Claude Opus 4", "claude-opus-4-20250514", "deep"),
    ):
        available.append(
            {
                "id": f"anthropic::{model_name}",
                "label": label,
                "model": model_name,
                "backend": "anthropic",
                "provider": "anthropic",
                "response_mode": mode,
                "cloud": True,
                "configured": anthropic_ready,
                "disabled_reason": "" if anthropic_ready else "Faça login Claude via OAuth no onboarding ou informe uma API key.",
                "summary": f"Cloud · Claude · {mode.title()} · {anthropic_auth_label if anthropic_ready else 'login pendente'}",
                "selected": current_backend == "anthropic" and current_model == model_name,
            }
        )

    openai_auth = resolve_auth_context("openai-compatible")
    openai_endpoint = os.getenv("SOCC_OPENAI_COMPAT_URL", "").strip() or ("https://api.openai.com/v1" if openai_auth.get("credential") else "")
    openai_model = os.getenv("SOCC_OPENAI_COMPAT_MODEL", "").strip() or ("gpt-5-codex" if openai_auth.get("credential") else "")
    openai_ready = bool(openai_model and openai_endpoint and openai_auth.get("credential"))
    openai_auth_label = "OAuth" if openai_auth.get("method") == "oauth" else "API key"
    available.append(
        {
            "id": f"openai-compatible::{openai_model or 'codex'}",
            "label": "Codex",
            "model": openai_model,
            "backend": "openai-compatible",
            "provider": "openai-compatible",
            "response_mode": "deep",
            "cloud": True,
            "configured": openai_ready,
            "disabled_reason": "" if openai_ready else "Faça login Codex/OpenAI via OAuth no onboarding ou configure gateway + modelo.",
            "summary": (
                f"Cloud · Codex · {openai_model} · {openai_auth_label}"
                if openai_ready and openai_model
                else "Cloud · Codex · login/configuração pendente"
            ),
            "selected": current_backend == "openai-compatible" and current_model == openai_model,
        }
    )
    return available


def _active_agent_payload() -> dict[str, Any]:
    available = agent_loader_runtime.list_available_agents()
    selected = next((item for item in available if item.get("selected")), None)
    if not selected and available:
        selected = available[0]

    payload: dict[str, Any] = {
        "selected": selected or {},
        "available": available,
    }
    if not isinstance(selected, dict) or not selected.get("path"):
        return payload

    try:
        config = agent_loader_runtime.load_agent_config(Path(str(selected["path"])))
        payload["selected"] = {
            **selected,
            "schema_path": str(config.schema_path),
            "skills": sorted(config.skills.keys()),
            "references": sorted(config.references.keys()),
        }
    except Exception as exc:
        payload["selected"] = {
            **selected,
            "error": str(exc),
        }
    return payload


def control_center_summary_payload(limit_sessions: int = 12) -> dict[str, Any]:
    home = runtime_home()
    env_paths = load_environment()
    intel = knowledge_base_runtime.inspect_index(home)
    runtime_payload = runtime_status_payload()
    available_models = list_backend_models()
    agent_payload = _active_agent_payload()
    service_payload = runtime_service_status(home)
    vantage_payload = vantage_status_payload()
    sessions_error = ""
    try:
        recent_sessions = storage_runtime.list_chat_sessions(limit=max(1, min(limit_sessions, 30)))
    except Exception as exc:
        recent_sessions = []
        sessions_error = str(exc)
    checks = {
        "runtime_home_exists": home.exists(),
        "env_file_exists": (home / ".env").exists(),
        "manifest_exists": (home / "socc.json").exists(),
        "agent_selected_exists": Path(str((agent_payload.get("selected") or {}).get("path") or "")).exists(),
        "intel_registry_exists": Path(str((intel.get("paths") or {}).get("registry") or "")).exists(),
        "intel_index_exists": Path(str((intel.get("paths") or {}).get("index") or "")).exists(),
    }
    return {
        "runtime": runtime_payload,
        "runtime_models": {
            "catalog": available_models,
            "profiles": _runtime_model_profiles(),
            "available": _runtime_model_options(available_models, runtime_payload=runtime_payload),
            "keep_alive": os.getenv("SOCC_OLLAMA_KEEP_ALIVE", "15m"),
        },
        "service": service_payload,
        "vantage": vantage_payload,
        "agents": agent_payload,
        "knowledge_base": {
            "manifest": intel.get("manifest", {}),
            "sources": intel.get("sources", []),
            "paths": intel.get("paths", {}),
        },
        "sessions": {
            "count": len(recent_sessions),
            "items": recent_sessions,
            "error": sessions_error,
        },
        "diagnostics": {
            "paths": {
                "runtime_home": str(home),
                "runtime_env_loaded_from": env_paths.get("runtime_env"),
                "repo_env_loaded_from": env_paths.get("repo_env"),
            },
            "checks": checks,
            "feature_flags": feature_flags_payload(),
            "chat_storage_error": sessions_error,
        },
    }


def select_runtime_model_payload(
    *,
    response_mode: str,
    model: str,
    backend: str = "ollama",
    home: Path | None = None,
) -> dict[str, Any]:
    mode = str(response_mode or "").strip().lower()
    if mode not in {"fast", "balanced", "deep"}:
        raise ValueError("response_mode inválido. Use fast, balanced ou deep.")

    normalized_model = str(model or "").strip()
    normalized_backend = str(backend or "ollama").strip().lower()
    if normalized_backend not in {"ollama", "anthropic", "openai-compatible"}:
        raise ValueError("backend inválido. Use ollama, anthropic ou openai-compatible.")
    if normalized_backend == "openai-compatible" and not normalized_model:
        normalized_model = "gpt-5-codex"
    if normalized_backend != "openai-compatible" and not normalized_model:
        raise ValueError("model é obrigatório.")

    env_file = runtime_home(home) / ".env"
    if normalized_backend == "ollama":
        env_key = {
            "fast": "SOCC_OLLAMA_FAST_MODEL",
            "balanced": "SOCC_OLLAMA_BALANCED_MODEL",
            "deep": "SOCC_OLLAMA_DEEP_MODEL",
        }[mode]
        update_env_assignment(env_file, env_key, normalized_model)
        os.environ[env_key] = normalized_model
        if mode == "balanced":
            update_env_assignment(env_file, "OLLAMA_MODEL", normalized_model)
            os.environ["OLLAMA_MODEL"] = normalized_model
    elif normalized_backend == "anthropic":
        update_env_assignment(env_file, "LLM_PROVIDER", "anthropic")
        update_env_assignment(env_file, "SOCC_INFERENCE_BACKEND", "anthropic")
        update_env_assignment(env_file, "LLM_MODEL", normalized_model)
        os.environ["LLM_PROVIDER"] = "anthropic"
        os.environ["SOCC_INFERENCE_BACKEND"] = "anthropic"
        os.environ["LLM_MODEL"] = normalized_model
    else:
        update_env_assignment(env_file, "LLM_PROVIDER", "openai-compatible")
        update_env_assignment(env_file, "SOCC_INFERENCE_BACKEND", "openai-compatible")
        if normalized_model:
            update_env_assignment(env_file, "SOCC_OPENAI_COMPAT_MODEL", normalized_model)
            os.environ["SOCC_OPENAI_COMPAT_MODEL"] = normalized_model
        os.environ["LLM_PROVIDER"] = "openai-compatible"
        os.environ["SOCC_INFERENCE_BACKEND"] = "openai-compatible"

    return {
        "response_mode": mode,
        "backend": normalized_backend,
        "model": normalized_model,
        "persisted_env_file": str(env_file),
        "control_center": control_center_summary_payload(),
    }


def warmup_runtime_model_payload(
    *,
    response_mode: str = "balanced",
) -> dict[str, Any]:
    mode = str(response_mode or "balanced").strip().lower()
    if mode not in {"fast", "balanced", "deep"}:
        raise ValueError("response_mode inválido. Use fast, balanced ou deep.")

    model = {
        "fast": os.getenv("SOCC_OLLAMA_FAST_MODEL", "llama3.2:3b"),
        "balanced": os.getenv("SOCC_OLLAMA_BALANCED_MODEL", os.getenv("OLLAMA_MODEL", "")),
        "deep": os.getenv("SOCC_OLLAMA_DEEP_MODEL", os.getenv("OLLAMA_MODEL", "")),
    }[mode]
    result = warmup_backend_model(
        model=model,
        keep_alive=os.getenv("SOCC_OLLAMA_KEEP_ALIVE", "15m"),
    )
    return {
        "response_mode": mode,
        "result": result,
        "control_center": control_center_summary_payload(),
    }


def select_active_agent_payload(agent_id: str, *, home: Path | None = None) -> dict[str, Any]:
    target = str(agent_id or "").strip()
    if not target:
        raise ValueError("agent_id é obrigatório.")

    available = agent_loader_runtime.list_available_agents()
    selected = next(
        (
            item
            for item in available
            if str(item.get("id") or "") == target or str(item.get("path") or "") == target
        ),
        None,
    )
    if not isinstance(selected, dict):
        raise LookupError("Agente solicitado não foi encontrado.")

    agent_path = Path(str(selected.get("path") or "")).expanduser()
    if not agent_path.exists():
        raise LookupError("Caminho do agente não existe mais.")

    os.environ["SOCC_AGENT_HOME"] = str(agent_path)
    env_file = runtime_home(home) / ".env"
    update_env_assignment(env_file, "SOCC_AGENT_HOME", str(agent_path))

    return {
        "selected_agent": {
            "id": str(selected.get("id") or ""),
            "label": str(selected.get("label") or ""),
            "path": str(agent_path),
        },
        "persisted_env_file": str(env_file),
        "control_center": control_center_summary_payload(),
    }


def select_vantage_modules_payload(
    *,
    module_ids: list[str] | tuple[str, ...],
    enabled: bool | None = None,
    home: Path | None = None,
) -> dict[str, Any]:
    catalog = vantage_gateway.module_catalog()
    valid_ids = {str(item.get("id") or "").strip().lower() for item in catalog if item.get("id")}
    selected: list[str] = []
    for item in module_ids:
        module_id = str(item or "").strip().lower()
        if module_id and module_id in valid_ids and module_id not in selected:
            selected.append(module_id)

    env_file = runtime_home(home) / ".env"
    selected_value = ",".join(selected)
    update_env_assignment(env_file, "SOCC_VANTAGE_ENABLED_MODULES", selected_value)
    os.environ["SOCC_VANTAGE_ENABLED_MODULES"] = selected_value

    enabled_value = bool(selected) if enabled is None else bool(enabled)
    enabled_text = "true" if enabled_value else "false"
    update_env_assignment(env_file, "SOCC_VANTAGE_ENABLED", enabled_text)
    os.environ["SOCC_VANTAGE_ENABLED"] = enabled_text

    return {
        "enabled": enabled_value,
        "selected_modules": selected,
        "persisted_env_file": str(env_file),
        "control_center": control_center_summary_payload(),
    }


def runtime_status_payload() -> dict[str, Any]:
    payload = runtime_status()
    payload["features"] = feature_flags_payload()
    available_models = list_backend_models()
    payload["runtime_models"] = {
        "catalog": available_models,
        "profiles": _runtime_model_profiles(),
        "available": _runtime_model_options(available_models, runtime_payload=payload),
        "keep_alive": os.getenv("SOCC_OLLAMA_KEEP_ALIVE", "15m"),
    }
    return payload


def vantage_status_payload() -> dict[str, Any]:
    return vantage_gateway.status_payload()


def vantage_modules_payload() -> dict[str, Any]:
    status = vantage_gateway.status_payload()
    return {
        "enabled": bool(status.get("enabled")),
        "base_url": str(status.get("base_url") or ""),
        "auth_mode": str(status.get("auth_mode") or "none"),
        "modules": list(status.get("modules") or []),
        "selected_modules": list(status.get("selected_modules") or []),
        "future_rss_via_api": bool(status.get("future_rss_via_api")),
    }


def vantage_probe_payload(module_id: str) -> dict[str, Any]:
    module = str(module_id or "").strip().lower()
    if not module:
        raise ValueError("module é obrigatório.")
    return vantage_gateway.probe_module(module)


def runtime_benchmark_payload(
    *,
    concurrency: int = 4,
    hold_ms: int = 150,
    probe: bool = True,
) -> dict[str, Any]:
    payload = benchmark_runtime(
        concurrency=max(1, min(concurrency, 32)),
        hold_ms=max(0, min(hold_ms, 5000)),
        include_probe=probe,
    )
    payload["features"] = feature_flags_payload()
    return payload


def time_filename() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y%m%d_%H%M%S")


def chat_reply(
    message: str,
    session_id: str = "",
    cliente: str = "",
    response_mode: str = "balanced",
    selected_backend: str = "",
    selected_model: str = "",
) -> dict[str, Any]:
    storage_runtime.init_db()
    response = chat_runtime.generate_chat_reply(
        message=message,
        session_id=session_id,
        cliente=cliente,
        response_mode=response_mode,
        selected_backend=selected_backend,
        selected_model=selected_model,
    )
    response_type = str(response.get("type") or "message")
    content = str(response.get("content") or "")
    error_message = str(response.get("message") or "")
    skill = str(response.get("skill") or "")
    effective_session = str(response.get("session_id") or session_id or "default")
    runtime = response.get("runtime")
    if not isinstance(runtime, dict):
        runtime = runtime_brief()
    return ChatResponseEnvelope(
        response_type=response_type,
        session_id=effective_session,
        skill=skill,
        runtime=runtime,
        gateway=_chat_gateway_contract(
            stream=False,
            success=response_type != "error",
            error=error_message if response_type == "error" else "",
            runtime_override=runtime,
        ),
        content=content,
        message=error_message if response_type == "error" else "",
        metadata=_merge_chat_metadata(
            response.get("metadata") if isinstance(response.get("metadata"), dict) else None,
            cliente=cliente,
            response_mode=response_mode,
            selected_backend=selected_backend,
            selected_model=selected_model,
        ),
    ).to_dict()


def stream_chat_events(
    message: str,
    session_id: str = "",
    cliente: str = "",
    response_mode: str = "balanced",
    selected_backend: str = "",
    selected_model: str = "",
):
    storage_runtime.init_db()
    for event in chat_runtime.stream_chat_reply_events(
        message=message,
        session_id=session_id,
        cliente=cliente,
        response_mode=response_mode,
        selected_backend=selected_backend,
        selected_model=selected_model,
    ):
        if event.get("event") != "final":
            yield event
            continue

        data = event.get("data")
        if not isinstance(data, dict):
            yield event
            continue

        response_type = str(data.get("type") or "message")
        content = str(data.get("content") or "")
        error_message = str(data.get("message") or "")
        runtime = data.get("runtime")
        if not isinstance(runtime, dict):
            runtime = runtime_brief()
        yield {
            "event": "final",
            "data": ChatResponseEnvelope(
                response_type=response_type,
                session_id=str(data.get("session_id") or session_id or "default"),
                skill=str(data.get("skill") or ""),
                runtime=runtime,
                gateway=_chat_gateway_contract(
                    stream=True,
                    success=response_type != "error",
                    error=error_message if response_type == "error" else "",
                    runtime_override=runtime,
                ),
                content=content,
                message=error_message if response_type == "error" else "",
                metadata=_merge_chat_metadata(
                    data.get("metadata") if isinstance(data.get("metadata"), dict) else None,
                    cliente=cliente,
                    response_mode=response_mode,
                    selected_backend=selected_backend,
                    selected_model=selected_model,
                ),
            ).to_dict(),
        }
