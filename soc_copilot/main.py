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
import json as _json
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from soc_copilot.config import OUTPUT_DIR
from soc_copilot.modules import (
    persistence, input_adapter, parser_engine,
    rule_loader, ti_adapter, draft_engine, semi_llm_adapter,
)
from soc_copilot.modules import chat_service


def _infer_regra_context(regra: str, fields: dict, raw_text: str) -> str:
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
    if "." in ioc and "[" not in ioc and all(part.isdigit() for part in ioc.split(".") if part):
        return "ip"
    if len(ioc) in (32, 40, 64) and all(ch in "0123456789abcdefABCDEF" for ch in ioc):
        return "hash"
    return "domain"


def _infer_ti_tool(ioc: str, resultado: str) -> str:
    ioc_type = _infer_ioc_type(ioc)
    if ioc_type != "ip":
        return "batch_api"

    if any(
        marcador in resultado
        for marcador in (
            "Veredito:",
            "backend TI",
            "submeter lote",
            "aguardando resposta do lote TI",
        )
    ):
        return "batch_api"

    return "threat_check"

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    persistence.init_db()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    yield

app = FastAPI(title="SOC Copilot", version="1.0.0-mvp", lifespan=lifespan)

_BASE = Path(__file__).parent
app.mount("/static", StaticFiles(directory=str(_BASE / "static")), name="static")
templates = Jinja2Templates(directory=str(_BASE / "templates"))


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


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
    # Consolida entrada: arquivo tem prioridade sobre texto colado
    raw = payload_raw
    if arquivo and arquivo.filename:
        conteudo_bytes = await arquivo.read()
        raw = conteudo_bytes.decode("utf-8", errors="replace")

    if not raw.strip():
        return JSONResponse({"erro": "Nenhum payload fornecido."}, status_code=400)

    _MAX_PAYLOAD_BYTES = 512 * 1024  # 512 KB
    if len(raw.encode("utf-8", errors="replace")) > _MAX_PAYLOAD_BYTES:
        return JSONResponse({"erro": "Payload excede o limite de 512 KB."}, status_code=413)

    # 1. Input Adapter
    fmt, campos_brutos, raw_original = input_adapter.adapt(raw)

    # 2. Parser Engine
    fields = parser_engine.parse(campos_brutos, raw_original)

    # 3. Rule Loader
    regra_context = _infer_regra_context(regra, fields, raw_original)
    pack = rule_loader.load(regra=regra_context, cliente=cliente)

    # 4. Threat Intel — dispara se houver qualquer IOC externo consultável
    _iocs = fields["IOCs"]
    ti_results: dict[str, str] = {}
    if _iocs.get("ips_externos") or _iocs.get("dominios") or _iocs.get("hashes"):
        ti_results = await asyncio.to_thread(ti_adapter.enrich, _iocs)

    # 5. Classification Helper / Semi-LLM (análise estruturada pré-draft)
    analysis = semi_llm_adapter.run(
        fields=fields,
        ti_results=ti_results,
        raw_text=raw_original,
        regra=regra_context,
        cliente=cliente,
        pack=pack,
    )
    # 6. Draft Engine
    draft_text, template_usado = draft_engine.generate(
        classificacao=classificacao,
        fields=fields,
        ti_results=ti_results,
        pack=pack,
        analysis=analysis,
    )

    # 7. Persistência
    run_id = persistence.save_run(
        ofensa_id=ofensa_id,
        cliente=cliente,
        regra=regra_context,
        raw_input=raw_original,
        classificacao=classificacao,
        template_usado=template_usado,
    )
    for ioc, resultado in ti_results.items():
        persistence.save_intel(
            run_id=run_id,
            ioc=ioc,
            tipo=_infer_ioc_type(ioc),
            ferramenta=_infer_ti_tool(ioc, resultado),
            resultado=resultado,
        )
    persistence.save_analysis(run_id=run_id, analysis=analysis)
    persistence.save_output(run_id=run_id, tipo_saida=classificacao, conteudo=draft_text)

    # Monta resumo para o frontend
    iocs_display = {
        "externos": fields["IOCs"]["ips_externos"],
        "internos": fields["IOCs"]["ips_internos"],
        "urls": fields["IOCs"]["urls"][:5],
        "dominios": fields["IOCs"].get("dominios", [])[:5],
        "hashes": fields["IOCs"].get("hashes", [])[:5],
    }

    return JSONResponse({
        "run_id": run_id,
        "formato_detectado": fmt,
        "campos_extraidos": {
            k: v for k, v in fields.items() if k != "IOCs"
        },
        "iocs": iocs_display,
        "ti_results": ti_results,
        "analysis": analysis,
        "modelo_aderente": pack.modelo_nome or None,
        "regra_contexto": regra_context or None,
        "draft": draft_text,
        "classificacao": classificacao,
        "template_usado": template_usado,
    })


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
    try:
        fields = _json.loads(campos_json)
        ti_results = _json.loads(ti_json)
        iocs = _json.loads(iocs_json)
    except Exception:
        return JSONResponse({"erro": "JSON inválido nos campos recebidos."}, status_code=400)

    # Reconstrói IOCs dentro de fields com os dados recebidos
    if iocs:
        fields["IOCs"] = iocs
    elif "IOCs" not in fields:
        fields["IOCs"] = {"ips_externos": [], "ips_internos": [], "urls": [], "dominios": [], "hashes": []}

    # Garante boolean
    if "IP_Origem_Privado" not in fields:
        ip = fields.get("IP_Origem", "")
        try:
            import ipaddress as _ip
            fields["IP_Origem_Privado"] = _ip.ip_address(ip).is_private
        except Exception:
            fields["IP_Origem_Privado"] = True

    regra_context = _infer_regra_context(regra, fields, "")
    pack = rule_loader.load(regra=regra_context, cliente=cliente)
    analysis = semi_llm_adapter.run(
        fields=fields, ti_results=ti_results,
        raw_text="", regra=regra_context, cliente=cliente, pack=pack,
    )
    draft_text, template_usado = draft_engine.generate(
        classificacao=classificacao, fields=fields,
        ti_results=ti_results, pack=pack, analysis=analysis,
    )
    if run_id:
        persistence.save_output(
            run_id=run_id,
            tipo_saida=f"{classificacao}_final",
            conteudo=draft_text,
        )

    return JSONResponse({
        "draft": draft_text,
        "template_usado": template_usado,
        "classificacao": classificacao,
    })


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
    if not conteudo.strip():
        return JSONResponse({"erro": "Conteúdo vazio."}, status_code=400)

    import re as _re
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Sanitiza entradas para evitar path traversal — mantém apenas alfanum, hífen e underscore
    ofensa_safe = _re.sub(r"[^\w\-]", "_", ofensa_id or "SEM_ID")[:40]
    cls_safe = _re.sub(r"[^\w]", "_", classificacao)[:10]
    nome = f"Ofensa_{ofensa_safe}_{cls_safe}_{ts}.txt"
    caminho = OUTPUT_DIR / nome
    # Garante que o arquivo final está dentro de OUTPUT_DIR (defesa em profundidade)
    if not str(caminho.resolve()).startswith(str(OUTPUT_DIR.resolve())):
        return JSONResponse({"erro": "Caminho de destino inválido."}, status_code=400)

    caminho.write_text(conteudo, encoding="utf-8")

    if run_id:
        persistence.save_output(
            run_id=run_id,
            tipo_saida=f"{classificacao}_salvo",
            conteudo=conteudo,
            salvo_em=str(caminho),
        )

    return JSONResponse({"salvo_em": str(caminho), "nome": nome})


# ---------------------------------------------------------------------------
# Histórico
# ---------------------------------------------------------------------------
@app.get("/api/history")
async def history(limit: int = 50):
    limit = max(1, min(limit, 200))  # cap: 1..200
    runs = persistence.list_runs(limit=limit)
    return JSONResponse({"runs": runs})


@app.get("/api/chat/sessions")
async def chat_sessions(limit: int = 50):
    sessions = persistence.list_chat_sessions(limit=limit)
    return JSONResponse({"sessions": sessions})


@app.get("/api/chat/sessions/{session_id}")
async def chat_session_messages(session_id: str, limit: int = 100):
    messages = persistence.list_chat_messages(session_id=session_id, limit=max(1, min(limit, 200)))
    return JSONResponse({"session_id": session_id, "messages": messages})


# ---------------------------------------------------------------------------
# Chat UI — nova interface estilo OpenWebUI
# ---------------------------------------------------------------------------
@app.get("/chat", response_class=HTMLResponse)
async def chat_ui(request: Request):
    chat_html = (_BASE / "templates" / "chat.html").read_text(encoding="utf-8")
    return HTMLResponse(content=chat_html)


# ---------------------------------------------------------------------------
# Helper de detecção de payload (usado pelo endpoint /api/chat)
# ---------------------------------------------------------------------------
def _looks_like_payload(text: str) -> bool:
    import re
    t = text[:1000]
    return bool(
        re.search(r'(\w+=(?:"[^"]*"|[^\s]+)\s+){3,}', t) or
        re.search(r'<\d{3}>', t) or
        re.search(r'srcip=|dstip=|action=|devname=|logid=', t) or
        re.search(r'SubjectUserName|EventRecordID|TargetUserName', t) or
        re.search(r'"type"\s*:\s*"(?:alert|event|log|security)"', t) or
        (len(t) > 300 and t.count('=') > 5)
    )


# ---------------------------------------------------------------------------
# Endpoint de chat — recebe mensagens da nova UI
# ---------------------------------------------------------------------------
@app.post("/api/chat")
async def chat_endpoint(request: Request):
    body = await request.json()
    message = body.get("message", "").strip()
    session_id = body.get("session_id", "")
    effective_session = session_id or str(int(datetime.now().timestamp() * 1000))
    classificacao = body.get("classificacao", "auto").upper()
    cliente = body.get("cliente", "")

    if not message:
        return JSONResponse({"error": "Mensagem vazia"}, status_code=400)

    # Detecta se é payload de log
    is_payload = _looks_like_payload(message)

    if is_payload:
        # Roda pipeline SOCC
        try:
            selected_skill = chat_service.select_skill(message)
            persistence.ensure_chat_session(
                session_id=effective_session,
                cliente=cliente,
                titulo=message[:80],
            )
            fmt, campos, raw = input_adapter.adapt(message)
            fields = parser_engine.parse(campos, raw)
            ti_results = await asyncio.to_thread(ti_adapter.enrich, fields.get("IOCs", {}))

            regra_context = _infer_regra_context("", fields, raw)
            pack = rule_loader.load(regra=regra_context, cliente=cliente)
            analysis = semi_llm_adapter.run(fields, ti_results, raw, regra_context, cliente, pack)

            cls = classificacao if classificacao != "AUTO" else (
                analysis.get("classificacao_sugerida", {}).get("tipo", "TP")
                .replace("True Positive", "TP")
                .replace("Benign True Positive", "BTP")
                .replace("False Positive", "FP")
                .replace("True Negative", "TN")
                .replace("Log Transmission Failure", "LTF")
            )
            if cls not in {"TP", "BTP", "FP", "TN", "LTF"}:
                cls = "TP"

            draft, template = draft_engine.generate(cls, fields, ti_results, pack, analysis)

            iocs = fields.get("IOCs", {})
            response_payload = {
                "type": "analysis",
                "session_id": effective_session,
                "skill": selected_skill,
                "classificacao": cls,
                "confianca": analysis.get("classificacao_sugerida", {}).get("confianca", 0),
                "campos": {k: v for k, v in fields.items() if k != "IOCs"},
                "iocs": {
                    "externos": iocs.get("ips_externos", []),
                    "internos": iocs.get("ips_internos", []),
                    "dominios": iocs.get("dominios", []),
                    "hashes": iocs.get("hashes", []),
                },
                "mitre": analysis.get("mitre_candidato", {}),
                "analise_tecnica": analysis.get("resumo_factual", {}).get("o_que", ""),
                "hipoteses": analysis.get("hipoteses", []),
                "lacunas": analysis.get("lacunas", []),
                "draft": draft,
                "template": template,
                "modelo_aderente": pack.modelo_nome or "",
                "regra_contexto": regra_context,
                "formato_detectado": fmt,
            }
            persistence.save_chat_message(
                session_id=effective_session,
                role="user",
                content=message,
                skill=selected_skill,
                metadata={"type": "message"},
            )
            persistence.save_chat_message(
                session_id=effective_session,
                role="assistant",
                content=draft,
                skill=selected_skill,
                metadata=response_payload,
            )
            return JSONResponse(response_payload)
        except Exception as e:
            return JSONResponse({"type": "error", "message": str(e)}, status_code=500)
    else:
        response = await asyncio.to_thread(
            chat_service.generate_chat_reply,
            message,
            effective_session,
            cliente,
        )
        return JSONResponse(response)
