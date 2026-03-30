"""
main.py
FastAPI — SOC Copilot
Rotas:
  GET  /           -> UI principal
  POST /api/analyze -> análise completa
  POST /api/save   -> salva nota em Notas_Geradas/
  GET  /api/history -> últimas execuções
"""
from __future__ import annotations
import asyncio
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime
import time as _time

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from socc.core.engine import (
    analyze_submission,
    chat_submission,
    control_center_summary_payload,
    export_analysis_submission,
    generate_draft_submission,
    list_chat_session_messages_payload,
    list_chat_sessions_payload,
    list_history_payload,
    prepare_analyze_raw_input,
    prepare_chat_submission_inputs,
    prepare_draft_submission_inputs,
    prepare_export_submission_inputs,
    prepare_feedback_submission_inputs,
    oauth_login_provider_payload,
    oauth_logout_provider_payload,
    oauth_provider_status_payload,
    runtime_benchmark_payload,
    runtime_status_payload,
    select_active_agent_payload,
    select_runtime_model_payload,
    select_vantage_modules_payload,
    save_feedback_submission,
    save_note_submission,
    stream_chat_submission_events,
    warmup_runtime_model_payload,
)
from socc.core import storage as storage_runtime
from socc.gateway.llm_gateway import record_analysis_event
from socc.utils.feature_flags import resolve_feature_flags
from socc.utils.http_api import feature_disabled_payload, sse_event
from soc_copilot.modules import persistence as _persistence

# ---------------------------------------------------------------------------
# Event Log (ring buffer em memória)
# ---------------------------------------------------------------------------
_event_log: deque = deque(maxlen=50)


def log_event(event: str, payload: dict | None = None) -> None:
    _event_log.appendleft({
        "ts": datetime.now().isoformat(timespec="seconds"),
        "event": event,
        "payload": payload or {},
    })


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    storage_runtime.init_db()
    yield

app = FastAPI(title="SOC Copilot", version="1.0.0-mvp", lifespan=lifespan)

_BASE = Path(__file__).parent
_STATIC_DIR = _BASE / "static"
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(_BASE / "templates"))


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return RedirectResponse(url="/chat", status_code=307)


@app.get("/legacy", response_class=HTMLResponse)
async def legacy_index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"request": request})


# ---------------------------------------------------------------------------
# Análise
# ---------------------------------------------------------------------------
@app.post("/api/analyze")
async def analyze(
    ofensa_id: str = Form(""),
    cliente: str = Form(""),
    regra: str = Form(""),
    classificacao: str = Form("TP"),
    payload_raw: str = Form(""),
    arquivo: UploadFile | None = File(default=None),
):
    flags = resolve_feature_flags()
    if not flags.analyze_api:
        return JSONResponse(feature_disabled_payload("analyze_api"), status_code=503)

    uploaded_bytes: bytes | None = None
    if arquivo and arquivo.filename:
        uploaded_bytes = await arquivo.read()
    try:
        raw = prepare_analyze_raw_input(
            payload_raw=payload_raw,
            uploaded_bytes=uploaded_bytes,
        )
    except ValueError as exc:
        status_code = 413 if "excede o limite" in str(exc) else 400
        return JSONResponse({"erro": str(exc)}, status_code=status_code)

    try:
        response_payload = await asyncio.to_thread(
            analyze_submission,
            raw_input=raw,
            ofensa_id=ofensa_id,
            cliente=cliente,
            regra=regra,
            classificacao=classificacao,
            threat_intel_enabled=flags.threat_intel,
            persist_run=True,
            source="api_analyze",
        )
        return JSONResponse(response_payload)
    except Exception as exc:
        record_analysis_event(
            source="api_analyze",
            latency_ms=0,
            success=False,
            schema_valid=False,
            threat_intel_used=False,
            payload_hash=storage_runtime.hash_input(raw),
            error=str(exc),
        )
        return JSONResponse({"erro": f"Falha na analise: {exc}"}, status_code=500)


# ---------------------------------------------------------------------------
# Gerar draft com classificação final + campos manuais
# ---------------------------------------------------------------------------
@app.post("/api/draft")
async def gerar_draft(
    run_id: int = Form(0),
    classificacao: str = Form("TP"),
    campos_json: str = Form("{}"),   # campos extraídos com overrides manuais
    iocs_json: str = Form("{}"),     # iocs (do analyze original)
    ti_json: str = Form("{}"),       # ti_results (do analyze original)
    regra: str = Form(""),
    cliente: str = Form(""),
):
    flags = resolve_feature_flags()
    if not flags.draft_api:
        return JSONResponse(feature_disabled_payload("draft_api"), status_code=503)

    try:
        prepared = prepare_draft_submission_inputs(
            campos_json=campos_json,
            iocs_json=iocs_json,
            ti_json=ti_json,
        )
    except ValueError as exc:
        return JSONResponse({"erro": str(exc)}, status_code=400)

    response_payload = await asyncio.to_thread(
        generate_draft_submission,
        fields=prepared["fields"],
        ti_results=prepared["ti_results"],
        classificacao=classificacao,
        regra=regra,
        cliente=cliente,
        run_id=run_id,
        persist_output=True,
        source="api_draft",
    )
    return JSONResponse(response_payload)


# ---------------------------------------------------------------------------
# Salvar nota em disco
# ---------------------------------------------------------------------------
@app.post("/api/save")
async def save_note(
    run_id: int = Form(0),
    ofensa_id: str = Form(""),
    classificacao: str = Form(""),
    conteudo: str = Form(""),
):
    try:
        payload = await asyncio.to_thread(
            save_note_submission,
            conteudo=conteudo,
            ofensa_id=ofensa_id,
            classificacao=classificacao,
            run_id=run_id,
        )
    except ValueError as exc:
        return JSONResponse({"erro": str(exc)}, status_code=400)
    return JSONResponse(payload)


# ---------------------------------------------------------------------------
# Histórico
# ---------------------------------------------------------------------------
@app.get("/api/history")
async def history(limit: int = 50):
    return JSONResponse(list_history_payload(limit=limit))


@app.get("/api/runtime/status")
async def api_runtime_status():
    flags = resolve_feature_flags()
    if not flags.runtime_api:
        return JSONResponse(feature_disabled_payload("runtime_api"), status_code=503)
    return JSONResponse(runtime_status_payload())


@app.get("/api/runtime/benchmark")
async def api_runtime_benchmark(
    concurrency: int = 4,
    hold_ms: int = 150,
    probe: bool = True,
):
    flags = resolve_feature_flags()
    if not flags.runtime_api:
        return JSONResponse(feature_disabled_payload("runtime_api"), status_code=503)
    return JSONResponse(
        runtime_benchmark_payload(
            concurrency=concurrency,
            hold_ms=hold_ms,
            probe=probe,
        )
    )


@app.get("/api/control-center")
async def api_control_center(limit_sessions: int = 12):
    flags = resolve_feature_flags()
    if not flags.runtime_api:
        return JSONResponse(feature_disabled_payload("runtime_api"), status_code=503)
    return JSONResponse(control_center_summary_payload(limit_sessions=limit_sessions))


@app.post("/api/control-center/agent/select")
async def api_control_center_select_agent(request: Request):
    flags = resolve_feature_flags()
    if not flags.runtime_api:
        return JSONResponse(feature_disabled_payload("runtime_api"), status_code=503)
    try:
        body = await request.json()
        agent_id = str((body or {}).get("agent_id") or "")
        payload = await asyncio.to_thread(select_active_agent_payload, agent_id)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except LookupError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return JSONResponse(payload)


@app.post("/api/control-center/runtime/model/select")
async def api_control_center_select_runtime_model(request: Request):
    flags = resolve_feature_flags()
    if not flags.runtime_api:
        return JSONResponse(feature_disabled_payload("runtime_api"), status_code=503)
    try:
        body = await request.json()
        mode = str((body or {}).get("response_mode") or "")
        model = str((body or {}).get("model") or "")
        backend = str((body or {}).get("backend") or "ollama")
        payload = await asyncio.to_thread(
            select_runtime_model_payload,
            response_mode=mode,
            model=model,
            backend=backend,
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(payload)


@app.post("/api/control-center/runtime/warmup")
async def api_control_center_runtime_warmup(request: Request):
    flags = resolve_feature_flags()
    if not flags.runtime_api:
        return JSONResponse(feature_disabled_payload("runtime_api"), status_code=503)
    try:
        body = await request.json()
        mode = str((body or {}).get("response_mode") or "balanced")
        payload = await asyncio.to_thread(
            warmup_runtime_model_payload,
            response_mode=mode,
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    status_code = 200 if ((payload.get("result") or {}).get("warmed") is True) else 502
    return JSONResponse(payload, status_code=status_code)


@app.get("/api/control-center/runtime/oauth/{provider_name}")
async def api_control_center_runtime_oauth_status(provider_name: str):
    flags = resolve_feature_flags()
    if not flags.runtime_api:
        return JSONResponse(feature_disabled_payload("runtime_api"), status_code=503)
    try:
        payload = await asyncio.to_thread(oauth_provider_status_payload, provider_name)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(payload)


@app.post("/api/control-center/runtime/oauth/{provider_name}/login")
async def api_control_center_runtime_oauth_login(provider_name: str):
    flags = resolve_feature_flags()
    if not flags.runtime_api:
        return JSONResponse(feature_disabled_payload("runtime_api"), status_code=503)
    try:
        payload = await asyncio.to_thread(oauth_login_provider_payload, provider_name)
        log_event("oauth.token.refresh", {"provider": provider_name})
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(payload)


@app.post("/api/control-center/runtime/oauth/{provider_name}/logout")
async def api_control_center_runtime_oauth_logout(provider_name: str):
    flags = resolve_feature_flags()
    if not flags.runtime_api:
        return JSONResponse(feature_disabled_payload("runtime_api"), status_code=503)
    try:
        payload = await asyncio.to_thread(oauth_logout_provider_payload, provider_name)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(payload)


@app.post("/api/control-center/vantage/modules")
async def api_control_center_select_vantage_modules(request: Request):
    flags = resolve_feature_flags()
    if not flags.runtime_api:
        return JSONResponse(feature_disabled_payload("runtime_api"), status_code=503)
    try:
        body = await request.json()
        payload = await asyncio.to_thread(
            select_vantage_modules_payload,
            module_ids=list((body or {}).get("module_ids") or []),
            enabled=(body or {}).get("enabled"),
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(payload)


@app.post("/api/feedback")
async def save_feedback(request: Request):
    flags = resolve_feature_flags()
    if not flags.feedback_api:
        return JSONResponse(feature_disabled_payload("feedback_api"), status_code=503)

    try:
        prepared = prepare_feedback_submission_inputs(await request.json())
        payload = await asyncio.to_thread(
            save_feedback_submission,
            **prepared,
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except LookupError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return JSONResponse(payload)


@app.post("/api/export-analysis")
async def export_analysis(request: Request):
    flags = resolve_feature_flags()
    if not flags.export_api:
        return JSONResponse(feature_disabled_payload("export_api"), status_code=503)

    try:
        prepared = prepare_export_submission_inputs(await request.json())
        payload = await asyncio.to_thread(
            export_analysis_submission,
            **prepared,
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(payload)


@app.get("/api/chat/sessions")
async def chat_sessions(limit: int = 50):
    return JSONResponse(list_chat_sessions_payload(limit=limit))


@app.get("/api/chat/sessions/{session_id}")
async def chat_session_messages(session_id: str, limit: int = 100):
    return JSONResponse(list_chat_session_messages_payload(session_id=session_id, limit=limit))


@app.get("/api/chat/sessions/{session_id}/usage")
async def chat_session_usage(session_id: str):
    try:
        return JSONResponse(_persistence.get_session_usage(session_id))
    except Exception as exc:
        return JSONResponse({"tokens_in": 0, "tokens_out": 0, "messages": 0, "error": str(exc)})


@app.get("/api/usage/summary")
async def usage_summary(limit: int = 30):
    try:
        return JSONResponse(_persistence.list_usage_summary(limit=limit))
    except Exception as exc:
        return JSONResponse({"sessions": [], "totals": {"tokens_in": 0, "tokens_out": 0}, "error": str(exc)})


@app.get("/api/health/attention")
async def health_attention():
    items: list[dict] = []
    try:
        import os as _os
        import urllib.request as _ureq
        # Verifica LLM habilitado
        llm_enabled = str(_os.getenv("LLM_ENABLED", "")).strip().lower() in {"1", "true", "yes", "on"}
        if not llm_enabled:
            items.append({
                "severity": "warning",
                "icon": "⚠️",
                "title": "LLM desabilitado",
                "description": "LLM_ENABLED não está ativo. Respostas usam fallback.",
            })
        # Verifica OAuth Anthropic
        try:
            oauth_payload = await asyncio.to_thread(oauth_provider_status_payload, "anthropic")
            providers = (oauth_payload.get("oauth") or {}).get("providers") or []
            for prov in providers:
                if str(prov.get("provider") or "").lower() == "anthropic":
                    expires_at = str(prov.get("expires_at") or "")
                    if expires_at:
                        try:
                            from datetime import datetime as _dt, timezone as _tz
                            exp_dt = _dt.fromisoformat(expires_at.replace("Z", "+00:00"))
                            now_dt = _dt.now(_tz.utc)
                            diff_secs = (exp_dt - now_dt).total_seconds()
                            if diff_secs < 0:
                                items.append({"severity": "error", "icon": "❌", "title": "Token Anthropic expirado", "description": f"O token OAuth Anthropic expirou em {expires_at}."})
                            elif diff_secs < 3600:
                                items.append({"severity": "warning", "icon": "⚠️", "title": "Token Anthropic expirando", "description": f"O token OAuth Anthropic expira em menos de 1h ({expires_at})."})
                        except Exception:
                            pass
        except Exception:
            pass
        # Verifica Ollama offline
        try:
            ollama_url = _os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
            req = _ureq.Request(f"{ollama_url}/api/tags", method="GET")
            with _ureq.urlopen(req, timeout=2):
                pass
        except Exception:
            items.append({
                "severity": "warning",
                "icon": "⚠️",
                "title": "Ollama offline",
                "description": "Não foi possível conectar ao Ollama local. Backend local indisponível.",
            })
        # Verifica KB vazia
        try:
            from socc.core import knowledge_base as _kb
            doc_count = _kb.count_documents()
            if doc_count == 0:
                items.append({
                    "severity": "info",
                    "icon": "ℹ️",
                    "title": "Base de conhecimento vazia",
                    "description": "Nenhum documento indexado na KB local.",
                })
        except Exception:
            pass
    except Exception as exc:
        items.append({"severity": "info", "icon": "ℹ️", "title": "Verificação parcial", "description": str(exc)})
    return JSONResponse({"items": items})


@app.get("/api/events")
async def get_events():
    return JSONResponse({"events": list(_event_log)})


# ---------------------------------------------------------------------------
# Chat UI — nova interface estilo OpenWebUI
# ---------------------------------------------------------------------------
@app.get("/chat", response_class=HTMLResponse)
async def chat_ui(request: Request):
    chat_html = (_BASE / "templates" / "chat.html").read_text(encoding="utf-8")
    return HTMLResponse(content=chat_html)


# ---------------------------------------------------------------------------
# Endpoint de chat — recebe mensagens da nova UI
# ---------------------------------------------------------------------------
@app.post("/api/chat")
async def chat_endpoint(request: Request):
    flags = resolve_feature_flags()
    if not flags.chat_api:
        return JSONResponse(feature_disabled_payload("chat_api"), status_code=503)

    try:
        prepared = prepare_chat_submission_inputs(await request.json())
        response = await asyncio.to_thread(
            chat_submission,
            **prepared,
            threat_intel_enabled=flags.threat_intel,
            source="chat_payload",
        )
        return JSONResponse(response)
    except Exception as exc:
        message = ""
        if "prepared" in locals():
            message = str(prepared.get("message", "") or "")
        if isinstance(exc, ValueError):
            return JSONResponse({"error": str(exc)}, status_code=400)
        record_analysis_event(
            source="chat_payload",
            latency_ms=0,
            success=False,
            schema_valid=False,
            threat_intel_used=False,
            payload_hash=storage_runtime.hash_input(message),
            error=str(exc),
        )
        return JSONResponse({"type": "error", "message": str(exc)}, status_code=500)


@app.post("/api/chat/stream")
async def chat_stream_endpoint(request: Request):
    flags = resolve_feature_flags()
    if not flags.chat_api:
        return JSONResponse(feature_disabled_payload("chat_api"), status_code=503)
    if not flags.chat_streaming:
        return JSONResponse(feature_disabled_payload("chat_streaming"), status_code=503)

    try:
        prepared = prepare_chat_submission_inputs(await request.json())
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    message = str(prepared["message"])
    session_id = str(prepared["session_id"])

    async def event_stream():
        _started = _time.perf_counter()
        _meta: dict = {}
        try:
            async for event in stream_chat_submission_events(
                **prepared,
                threat_intel_enabled=flags.threat_intel,
                source="chat_payload",
            ):
                ev_name = event["event"]
                ev_payload = event["payload"]
                if ev_name == "meta" and not _meta:
                    _meta = ev_payload or {}
                    log_event("chat.inference.start", {
                        "backend": _meta.get("selected_backend") or _meta.get("backend") or "unknown",
                        "model": _meta.get("model") or "",
                        "session_id": _meta.get("session_id") or session_id,
                    })
                elif ev_name == "final":
                    _dur = int((_time.perf_counter() - _started) * 1000)
                    _fmeta = (ev_payload or {}).get("metadata") or {}
                    log_event("chat.inference.done", {
                        "tokens_out": int(_fmeta.get("tokens_out") or 0),
                        "duration_ms": _dur,
                        "session_id": (ev_payload or {}).get("session_id") or session_id,
                    })
                yield sse_event(ev_name, ev_payload)
        except Exception as exc:
            effective_session = session_id or str(int(datetime.now().timestamp() * 1000))
            log_event("chat.inference.error", {"error": str(exc), "session_id": effective_session})
            record_analysis_event(
                source="chat_payload_stream",
                latency_ms=0,
                success=False,
                schema_valid=False,
                threat_intel_used=False,
                payload_hash=storage_runtime.hash_input(message),
                error=str(exc),
            )
            yield sse_event("error", {"message": str(exc), "session_id": effective_session})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
