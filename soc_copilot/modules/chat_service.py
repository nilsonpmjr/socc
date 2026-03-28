from __future__ import annotations

import json
import logging
import os
from time import perf_counter
from typing import Iterator, List

import requests

from soc_copilot import config as cfg
from soc_copilot.modules import persistence
from soc_copilot.modules.soc_copilot_loader import build_prompt_context, choose_skill
from socc.core import knowledge_base as knowledge_base_runtime
from socc.gateway import vantage_api as vantage_gateway
from socc.gateway.llm_gateway import (
    inference_guard,
    record_prompt_audit,
    record_inference_event,
    resolve_runtime,
    runtime_brief,
)

_logger = logging.getLogger(__name__)
_STREAM_CHUNK_SIZE = 120
_DEFAULT_RESPONSE_MODE = "balanced"
_REFERENTIAL_MARKERS = (
    "esse payload",
    "este payload",
    "esse evento",
    "este evento",
    "esse alerta",
    "este alerta",
    "isso",
    "isso é",
    "isso e",
    "esse json",
    "este json",
)
_REPEATED_GREETING_PATTERNS = (
    "olá!",
    "olá.",
    "olá,",
    "ola!",
    "ola.",
    "ola,",
    "oi!",
    "oi.",
    "oi,",
    "e aí,",
    "e ai,",
)
_RESPONSE_MODE_PROFILES = {
    "fast": {
        "label": "Fast",
        "history_limit": 2,
        "kb_limit": 1,
        "kb_chars": 520,
        "chunk_size": 160,
        "temperature": 0.1,
        "num_ctx": 3072,
        "instruction": (
            "Modo FAST: responda com máxima objetividade, priorize conclusão, "
            "evidências essenciais e próximos passos imediatos em formato curto. "
            "Encerre a resposta completamente, sem começar listas longas, preferindo até 8 linhas curtas."
        ),
    },
    "balanced": {
        "label": "Balanced",
        "history_limit": 5,
        "kb_limit": 3,
        "kb_chars": 1100,
        "chunk_size": 120,
        "temperature": 0.15,
        "num_ctx": 6144,
        "instruction": (
            "Modo BALANCED: mantenha objetividade, mas preserve contexto "
            "suficiente para análise SOC explicável e útil."
        ),
    },
    "deep": {
        "label": "Deep",
        "history_limit": 8,
        "kb_limit": 4,
        "kb_chars": 2200,
        "chunk_size": 100,
        "temperature": 0.2,
        "num_ctx": 8192,
        "instruction": (
            "Modo DEEP: aprofunde a análise, explicite hipóteses, limitações, "
            "impacto e próximos passos com mais detalhe."
        ),
    },
}


def normalize_response_mode(value: str = "") -> str:
    mode = str(value or "").strip().lower()
    if mode in _RESPONSE_MODE_PROFILES:
        return mode
    return _DEFAULT_RESPONSE_MODE


def response_mode_profile(value: str = "") -> dict[str, object]:
    return dict(_RESPONSE_MODE_PROFILES[normalize_response_mode(value)])


def resolve_ollama_model_for_mode(response_mode: str = _DEFAULT_RESPONSE_MODE) -> str:
    mode = normalize_response_mode(response_mode)
    primary = getattr(cfg, "OLLAMA_MODEL", "qwen3.5:9b")
    fast_model = os.getenv("SOCC_OLLAMA_FAST_MODEL", "llama3.2:3b").strip() or primary
    balanced_model = os.getenv("SOCC_OLLAMA_BALANCED_MODEL", primary).strip() or primary
    deep_model = os.getenv("SOCC_OLLAMA_DEEP_MODEL", primary).strip() or primary
    mapping = {
        "fast": fast_model,
        "balanced": balanced_model,
        "deep": deep_model,
    }
    return mapping.get(mode, primary) or primary


def _detect_artifact_type(message: str) -> str | None:
    text = (message or "").lower()
    if any(token in text for token in ("subject:", "from:", "reply-to", "attachment", "email")):
        return "email"
    if "http://" in text or "https://" in text or "www." in text:
        return "url"
    if any(token in text for token in ("powershell", "cmd.exe", "rundll32", "schtasks", "registry")):
        return "malware"
    return None


def _looks_like_structured_artifact(text: str) -> bool:
    content = str(text or "").strip()
    if not content:
        return False
    if content.startswith("{") and content.endswith("}"):
        return True
    structured_hits = 0
    for marker in (
        "creationtime",
        "operation",
        "recordtype",
        "resultstatus",
        "srcip=",
        "dstip=",
        "action=",
        "logid=",
        "devname=",
        "\"reason\"",
    ):
        if marker in content.lower():
            structured_hits += 1
    return structured_hits >= 2


def _mentions_recent_artifact(message: str) -> bool:
    lowered = str(message or "").strip().lower()
    return any(marker in lowered for marker in _REFERENTIAL_MARKERS)


def _artifact_excerpt(text: str, limit: int = 1200) -> str:
    cleaned = " ".join(str(text or "").split())
    return cleaned[:limit].strip()


def _find_recent_artifact_context(session_id: str, message: str, *, scan_limit: int = 12) -> str:
    if not session_id or not _mentions_recent_artifact(message):
        return ""
    history = persistence.list_chat_messages(session_id, limit=max(4, scan_limit))
    for item in reversed(history):
        if item.get("role") != "user":
            continue
        content = str(item.get("content") or "").strip()
        if content and _looks_like_structured_artifact(content):
            return _artifact_excerpt(content)
    return ""


def _parse_semicolon_map(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in str(text or "").split(";"):
        chunk = part.strip()
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        key_norm = key.strip()
        value_norm = value.strip()
        if key_norm and value_norm:
            result[key_norm] = value_norm
    return result


def _m365_hygiene_hint(text: str) -> str:
    lowered = str(text or "").lower()
    if "hygienetenantevents" not in lowered:
        return ""
    try:
        payload = json.loads(text)
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    reason_map = _parse_semicolon_map(str(payload.get("Reason") or ""))
    event_value = str(payload.get("EventValue") or payload.get("UserId") or "").strip()
    result_status = str(payload.get("ResultStatus") or "").strip()
    event_name = str(payload.get("Event") or "").strip()
    audit = str(payload.get("Audit") or "").strip()
    workload = str(payload.get("Workload") or "").strip()
    recipient_count = reason_map.get("RecipientCountLast24Hours", "")
    recipient_limit = reason_map.get("RcptRateLimit", "")

    if "RecipientRateLimitExceeded" not in str(payload.get("Reason") or ""):
        return ""

    lines = [
        "Leitura determinística do evento:",
        (
            "Este evento não indica, por si só, limpeza de tenant nem malware. "
            "Ele sugere atuação do mecanismo de higiene/proteção do Microsoft 365 sobre envio de e-mail."
        ),
        (
            f"A combinação `Operation=HygieneTenantEvents`, `Event={event_name or '-'}`, "
            f"`ResultStatus={result_status or '-'}` e `Workload={workload or '-'}` aponta para evento administrativo/automatizado de proteção."
        ),
    ]
    if event_value:
        lines.append(f"O principal identificador observado é `{event_value}`.")
    if recipient_count and recipient_limit:
        lines.append(
            f"O motivo registrado é excesso de destinatários: `{recipient_count}` no período, acima do limite `{recipient_limit}`."
        )
    if audit:
        lines.append(
            "O campo `Audit` indica geração por serviço interno de reputação/proteção (`OBP2SenderRepService`), "
            "o que reforça leitura de controle anti-abuso/outbound spam."
        )
    lines.append(
        "Conclusão inicial: isso é mais compatível com limitação/listagem automática por volume de envio ou reputação do remetente "
        "do que com um incidente confirmado."
    )
    lines.append(
        "O que validar a seguir: se a conta/remetente realmente enviou alto volume, se houve comprometimento de caixa postal, "
        "se existe campanha legítima disparando o limite e se o MessageTrace confirma o comportamento do período."
    )
    return "\n".join(lines)


def select_skill(message: str, artifact_type: str | None = None) -> str:
    return choose_skill(message, artifact_type=artifact_type or _detect_artifact_type(message))


def _format_history(session_id: str, *, limit: int) -> str:
    history = persistence.list_chat_messages(session_id, limit=max(1, limit))
    if not history:
        return ""
    lines: List[str] = []
    for item in history:
        role = "usuario" if item.get("role") == "user" else "assistente"
        content = item.get("content", "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines[-max(1, limit):])


def _build_system_prompt(context: dict[str, str], *, response_mode: str = _DEFAULT_RESPONSE_MODE) -> str:
    profile = response_mode_profile(response_mode)
    sections = [
        context.get("identity", ""),
        "Siga a persona e regras abaixo.",
        context.get("soul", ""),
        context.get("user", ""),
        context.get("agents", ""),
        context.get("memory", ""),
        context.get("tools", ""),
        "Referencias operacionais compartilhadas:",
        context.get("evidence_rules", ""),
        context.get("ioc_extraction", ""),
        context.get("security_json_patterns", ""),
        context.get("telemetry_investigation_patterns", ""),
        context.get("mitre_guidance", ""),
        context.get("output_contract", ""),
        "Skill selecionada:",
        context.get("selected_skill", ""),
        context.get("skill_content", ""),
        str(profile.get("instruction") or ""),
        (
            "Regras de saida: responda em PT-BR, seja tecnico e objetivo, "
            "nao invente fatos, diferencie observacao de inferencia, e use markdown simples quando ajudar."
        ),
        (
            "Nem toda conversa exige verdict, classificacao binaria ou estrutura de triagem. "
            "Quando a pergunta for exploratoria, consultiva ou investigativa, responda como parceiro tecnico do SOC: "
            "explique o significado, apresente hipoteses razoaveis, diga o que validar e sugira proximos passos."
        ),
        (
            "So entre em modo de triagem estruturada quando houver payload, alerta, log ou artefato suficiente "
            "para sustentar evidencias observaveis."
        ),
        (
            "Se a sessao ja estiver em andamento, continue a conversa diretamente. "
            "Evite reabrir a resposta com saudacoes como 'Olá', 'Oi' ou equivalentes, "
            "a menos que o usuario esteja claramente iniciando uma nova conversa."
        ),
    ]
    return "\n\n".join(section for section in sections if section)


def _build_user_prompt(
    message: str,
    cliente: str,
    context: dict[str, str],
    *,
    response_mode: str = _DEFAULT_RESPONSE_MODE,
) -> str:
    mode = normalize_response_mode(response_mode)
    selected_skill = str(context.get("selected_skill") or "").strip()
    parts = []
    if cliente:
        parts.append(f"Cliente: {cliente}")
    parts.append(f"Modo de resposta: {mode}")
    if selected_skill:
        parts.append(f"Skill ativa: {selected_skill}")
    if context.get("session_context"):
        parts.append("Contexto recente da sessao:")
        parts.append(context["session_context"])
    if context.get("knowledge_context"):
        parts.append("Contexto recuperado da base local:")
        parts.append(context["knowledge_context"])
    if context.get("vantage_context"):
        parts.append("Contexto operacional recuperado do Vantage:")
        parts.append(context["vantage_context"])
    if context.get("artifact_context"):
        parts.append("Artefato recente citado nesta sessão:")
        parts.append(context["artifact_context"])
    if context.get("artifact_hint"):
        parts.append("Leitura inicial determinística do artefato recente:")
        parts.append(context["artifact_hint"])
    parts.append("Pedido atual do usuario:")
    parts.append(message.strip())
    if selected_skill == "soc-generalist":
        parts.append(
            "Trate o pedido como conversa operacional do dia a dia do SOC. "
            "Nao force verdict. Se houver pouca evidência, explique limites e oriente a investigação."
        )
    else:
        parts.append(
            "Se a entrada nao trouxer evidencia suficiente, explicite as limitacoes e proponha proximos passos seguros."
        )
    return "\n\n".join(part for part in parts if part)


def _fallback_response(message: str, skill_name: str) -> str:
    if skill_name == "soc-generalist":
        return (
            "Recebi sua pergunta em modo consultivo de SOC. "
            "A camada da conversa natural ja esta preparada, mas a resposta livre completa ainda depende de `LLM_ENABLED=true`.\n\n"
            "Enquanto isso, eu preservo o contexto da conversa e continuo apto a analisar payloads, IOCs e artefatos quando voce trouxer mais dados.\n\n"
            f"Pergunta registrada: {message.strip()[:400]}"
        )
    return (
        f"Recebi sua mensagem e selecionei a skill `{skill_name}` para este contexto. "
        "A conversa geral com a LLM local ainda depende de `LLM_ENABLED=true`, mas a camada do SOC Copilot "
        "ja esta pronta para orientar o comportamento do chat. "
        "Se voce colar um payload, o pipeline analitico atual continua funcionando normalmente.\n\n"
        f"Resumo do pedido: {message.strip()[:400]}"
    )


def _strip_repeated_greeting(text: str, *, has_session_history: bool) -> str:
    content = str(text or "").strip()
    if not content or not has_session_history:
        return content

    lowered = content.lower()
    for greeting in _REPEATED_GREETING_PATTERNS:
        if lowered.startswith(greeting):
            stripped = content[len(greeting):].lstrip(" \n-–—")
            return stripped or content

    first_paragraph, separator, remainder = content.partition("\n\n")
    if first_paragraph.strip().lower() in {"olá", "ola", "oi"} and remainder.strip():
        return remainder.strip()

    return content


def _deterministic_consultive_reply(
    *,
    message: str,
    skill_name: str,
    artifact_context: str,
) -> str:
    if skill_name != "soc-generalist":
        return ""
    hint = _m365_hygiene_hint(artifact_context)
    if not hint:
        return ""
    if "hygienetenantevents" not in str(message or "").lower() and "recipientratelimitexceeded" not in artifact_context.lower():
        return ""
    return "\n\n".join(
        [
            "Leitura inicial",
            hint,
            "Como eu trataria",
            (
                "Eu não trataria isso de saída como incidente confirmado. "
                "Parece muito mais um evento de proteção ou enforcement por volume/reputação de envio."
            ),
            "O que validar agora",
            (
                "1. Confirmar se a conta/remetente enviou volume elevado de mensagens.\n"
                "2. Verificar MessageTrace e histórico do remetente no período.\n"
                "3. Validar se a conta foi comprometida ou se houve campanha legítima.\n"
                "4. Correlacionar com outros eventos do mesmo usuário/remetente no tenant."
            ),
        ]
    )


def _prepare_chat_context(
    message: str,
    session_id: str = "",
    cliente: str = "",
    response_mode: str = _DEFAULT_RESPONSE_MODE,
) -> tuple[str, str, dict[str, str], list[dict[str, str]], dict[str, object]]:
    effective_session = session_id or "default"
    profile = response_mode_profile(response_mode)
    history_limit = int(profile.get("history_limit") or 5)
    kb_limit = int(profile.get("kb_limit") or 3)
    kb_chars = int(profile.get("kb_chars") or 1100)
    skill_name = select_skill(message)
    persistence.ensure_chat_session(
        session_id=effective_session,
        cliente=cliente,
        titulo=message.strip()[:80],
    )
    session_context = _format_history(effective_session, limit=history_limit)
    artifact_context = _find_recent_artifact_context(effective_session, message)
    retrieval = knowledge_base_runtime.search_knowledge_base(query_text=message, limit=kb_limit)
    knowledge_context = knowledge_base_runtime.format_retrieval_context(retrieval, max_chars=kb_chars)
    vantage = vantage_gateway.retrieve_context(message)
    combined_knowledge_context = "\n\n".join(
        section
        for section in (
            knowledge_context,
            str(vantage.get("context") or "").strip(),
        )
        if section
    ).strip()
    source_labels = ", ".join(
        str(item.get("source_name") or item.get("source_id") or "")
        for item in (list(retrieval.get("sources") or []) + list(vantage.get("sources") or []))
        if str(item.get("source_name") or item.get("source_id") or "")
    )
    context = build_prompt_context(
        user_input=message,
        artifact_type=_detect_artifact_type(message),
        session_context=session_context,
        selected_skill=skill_name,
        knowledge_context=combined_knowledge_context,
        knowledge_sources=source_labels,
    )
    context["artifact_context"] = artifact_context
    context["artifact_hint"] = _m365_hygiene_hint(artifact_context)
    context["vantage_context"] = str(vantage.get("context") or "").strip()
    context["vantage_sources"] = ", ".join(
        str(item.get("source_name") or item.get("source_id") or "")
        for item in (vantage.get("sources") or [])
        if str(item.get("source_name") or item.get("source_id") or "")
    )
    history_messages = [
        {"role": item.get("role", "user"), "content": item.get("content", "")}
        for item in persistence.list_chat_messages(
            effective_session, limit=history_limit
        )
    ]
    if artifact_context and not any(item.get("content") == artifact_context for item in history_messages):
        history_messages.insert(0, {"role": "user", "content": artifact_context})
    retrieval["vantage"] = vantage
    retrieval["sources"] = list(retrieval.get("sources") or []) + list(vantage.get("sources") or [])
    retrieval["matches"] = list(retrieval.get("matches") or []) + list(vantage.get("matches") or [])
    return effective_session, skill_name, context, history_messages, retrieval


def _persist_chat_exchange(
    *,
    session_id: str,
    message: str,
    skill_name: str,
    content: str,
    assistant_payload: dict[str, object] | None = None,
) -> None:
    persistence.save_chat_message(
        session_id=session_id,
        role="user",
        content=message,
        skill=skill_name,
        metadata={
            "type": "message",
            "content": message,
            "skill": skill_name,
            "session_id": session_id,
        },
    )
    payload = dict(assistant_payload or {})
    payload.setdefault("type", "message")
    payload.setdefault("content", content)
    payload.setdefault("skill", skill_name)
    payload.setdefault("session_id", session_id)
    persistence.save_chat_message(
        session_id=session_id,
        role="assistant",
        content=content,
        skill=skill_name,
        metadata=payload,
    )


def _chunk_text(text: str, chunk_size: int = _STREAM_CHUNK_SIZE) -> Iterator[str]:
    content = (text or "").strip()
    if not content:
        return
    for index in range(0, len(content), max(1, chunk_size)):
        yield content[index : index + max(1, chunk_size)]


def _stream_ollama_events(
    messages: list[dict[str, str]],
    *,
    response_mode: str = _DEFAULT_RESPONSE_MODE,
    num_predict_override: int | None = None,
) -> Iterator[dict[str, object]]:
    runtime = resolve_runtime()
    base_url = getattr(cfg, "OLLAMA_URL", "http://localhost:11434").rstrip("/")
    model = resolve_ollama_model_for_mode(response_mode)
    timeout = float(getattr(cfg, "LLM_TIMEOUT", 60))
    profile = response_mode_profile(response_mode)
    body = {
        "model": model,
        "messages": messages,
        "stream": True,
        "keep_alive": os.getenv("SOCC_OLLAMA_KEEP_ALIVE", "15m"),
        "options": {
            "temperature": float(profile.get("temperature") or 0.15),
            "num_ctx": int(profile.get("num_ctx") or 6144),
        },
    }
    if num_predict_override is not None:
        body["options"]["num_predict"] = int(num_predict_override)
    started = perf_counter()
    resp = None
    final_payload: dict[str, object] = {}
    try:
        resp = requests.post(
            f"{base_url}/api/chat",
            json=body,
            timeout=timeout,
            stream=True,
        )
        resp.raise_for_status()
        for raw_line in resp.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            payload = json.loads(raw_line)
            if isinstance(payload, dict):
                final_payload = payload
            delta = (payload.get("message") or {}).get("content") or ""
            if delta:
                yield {"kind": "delta", "delta": delta}
        done_reason = str(final_payload.get("done_reason") or ("stop" if final_payload.get("done") else "unknown"))
        yield {
            "kind": "meta",
            "done_reason": done_reason,
            "truncated": done_reason in {"length", "max_tokens"} or bool(final_payload.get("truncated")),
            "eval_count": int(final_payload.get("eval_count") or 0),
            "prompt_eval_count": int(final_payload.get("prompt_eval_count") or 0),
            "num_predict": int(num_predict_override) if num_predict_override is not None else None,
        }
        record_inference_event(
            source="chat_service",
            provider="ollama",
            model=model,
            requested_device=runtime.device,
            effective_device=runtime.device,
            latency_ms=(perf_counter() - started) * 1000,
            success=True,
            fallback_used=False,
        )
    except Exception as exc:
        record_inference_event(
            source="chat_service",
            provider="ollama",
            model=model,
            requested_device=runtime.device,
            effective_device=runtime.device,
            latency_ms=(perf_counter() - started) * 1000,
            success=False,
            fallback_used=False,
            error=str(exc),
        )
        raise
    finally:
        try:
            resp.close()
        except Exception:
            pass


def _stream_ollama(
    messages: list[dict[str, str]],
    *,
    response_mode: str = _DEFAULT_RESPONSE_MODE,
    num_predict_override: int | None = None,
) -> Iterator[str]:
    for item in _stream_ollama_events(
        messages,
        response_mode=response_mode,
        num_predict_override=num_predict_override,
    ):
        if item.get("kind") == "delta":
            yield str(item.get("delta") or "")


def _call_ollama(
    messages: list[dict[str, str]],
    *,
    response_mode: str = _DEFAULT_RESPONSE_MODE,
) -> str:
    prompt_blob = "\n\n".join(
        f"{item.get('role', 'user')}: {item.get('content', '')}"
        for item in messages
    )
    record_prompt_audit(
        source="chat_service",
        provider="ollama",
        model=resolve_ollama_model_for_mode(response_mode),
        prompt_text=prompt_blob,
    )
    return "".join(_stream_ollama(messages, response_mode=response_mode)).strip()


def stream_chat_reply_events(
    message: str,
    session_id: str = "",
    cliente: str = "",
    response_mode: str = _DEFAULT_RESPONSE_MODE,
) -> Iterator[dict[str, object]]:
    mode = normalize_response_mode(response_mode)
    profile = response_mode_profile(mode)
    effective_model = resolve_ollama_model_for_mode(mode)
    effective_session, skill_name, context, history_messages, retrieval = _prepare_chat_context(
        message,
        session_id=session_id,
        cliente=cliente,
        response_mode=mode,
    )
    runtime = runtime_brief()
    has_session_history = bool(history_messages)
    yield {
        "event": "meta",
        "session_id": effective_session,
        "skill": skill_name,
        "runtime": runtime,
        "response_mode": mode,
        "model": effective_model,
    }

    content = ""
    completion_meta: dict[str, object] = {
        "done_reason": "",
        "truncated": False,
        "continuation_used": False,
        "continuation_done_reason": "",
    }
    deterministic_reply = _deterministic_consultive_reply(
        message=message,
        skill_name=skill_name,
        artifact_context=str(context.get("artifact_context") or ""),
    )
    if deterministic_reply:
        content = _strip_repeated_greeting(deterministic_reply, has_session_history=has_session_history)
        completion_meta["done_reason"] = "deterministic"
        for delta in _chunk_text(content, chunk_size=int(profile.get("chunk_size") or _STREAM_CHUNK_SIZE)):
            yield {"event": "delta", "delta": delta, "skill": skill_name}
    elif not getattr(cfg, "LLM_ENABLED", False):
        content = _strip_repeated_greeting(
            _fallback_response(message, skill_name),
            has_session_history=has_session_history,
        )
        for delta in _chunk_text(content, chunk_size=int(profile.get("chunk_size") or _STREAM_CHUNK_SIZE)):
            yield {"event": "delta", "delta": delta, "skill": skill_name}
    elif not content:
        messages = [{"role": "system", "content": _build_system_prompt(context, response_mode=mode)}]
        messages.extend(history_messages)
        messages.append(
            {"role": "user", "content": _build_user_prompt(message, cliente, context, response_mode=mode)}
        )
        try:
            if getattr(cfg, "LLM_PROVIDER", "ollama").lower() != "ollama":
                content = _fallback_response(message, skill_name)
                for delta in _chunk_text(content, chunk_size=int(profile.get("chunk_size") or _STREAM_CHUNK_SIZE)):
                    yield {"event": "delta", "delta": delta, "skill": skill_name}
            else:
                runtime_cfg = resolve_runtime()
                with inference_guard(runtime_cfg) as (allowed, reason):
                    if not allowed:
                        record_inference_event(
                            source="chat_service",
                            provider=runtime_cfg.provider,
                            model=runtime_cfg.model,
                            requested_device=runtime_cfg.device,
                            effective_device=runtime_cfg.device,
                            latency_ms=0,
                            success=False,
                            fallback_used=True,
                            error=reason,
                        )
                        content = (
                            _fallback_response(message, skill_name)
                            + "\n\nObservabilidade: inferencia local temporariamente contida pelo runtime "
                            f"({reason})."
                        )
                        for delta in _chunk_text(content, chunk_size=int(profile.get("chunk_size") or _STREAM_CHUNK_SIZE)):
                            yield {"event": "delta", "delta": delta, "skill": skill_name}
                    else:
                        parts: list[str] = []
                        for item in _stream_ollama_events(messages, response_mode=mode):
                            if item.get("kind") == "delta":
                                delta = str(item.get("delta") or "")
                                parts.append(delta)
                                yield {"event": "delta", "delta": delta, "skill": skill_name}
                            else:
                                completion_meta.update(dict(item))
                        content = _strip_repeated_greeting(
                            "".join(parts).strip(),
                            has_session_history=has_session_history,
                        )
                        if bool(completion_meta.get("truncated")):
                            completion_meta["continuation_used"] = True
                            continuation_messages = list(messages)
                            continuation_messages.append({"role": "assistant", "content": content})
                            continuation_messages.append(
                                {
                                    "role": "user",
                                    "content": (
                                        "Continue exatamente de onde voce parou, sem repetir o texto anterior. "
                                        "Conclua a resposta em no maximo 3 linhas curtas."
                                    ),
                                }
                            )
                            continuation_parts: list[str] = []
                            continuation_meta: dict[str, object] = {}
                            for item in _stream_ollama_events(
                                continuation_messages,
                                response_mode=mode,
                            ):
                                if item.get("kind") == "delta":
                                    delta = str(item.get("delta") or "")
                                    continuation_parts.append(delta)
                                    yield {"event": "delta", "delta": delta, "skill": skill_name}
                                else:
                                    continuation_meta.update(dict(item))
                            completion_meta["continuation_done_reason"] = str(
                                continuation_meta.get("done_reason") or ""
                            )
                            completion_meta["truncated"] = bool(continuation_meta.get("truncated"))
                            content = _strip_repeated_greeting(
                                f"{content}{''.join(continuation_parts)}".strip(),
                                has_session_history=has_session_history,
                            )
        except Exception as exc:
            _logger.exception("Falha ao consultar a LLM local no chat do SOC Copilot.")
            content = _strip_repeated_greeting(
                (
                    f"Falha ao consultar a LLM local: {exc}. "
                    f"Skill selecionada: `{skill_name}`."
                ),
                has_session_history=has_session_history,
            )
            for delta in _chunk_text(content, chunk_size=int(profile.get("chunk_size") or _STREAM_CHUNK_SIZE)):
                yield {"event": "delta", "delta": delta, "skill": skill_name}

    _persist_chat_exchange(
        session_id=effective_session,
        message=message,
        skill_name=skill_name,
        content=content,
        assistant_payload={
            "type": "message",
            "content": content,
            "skill": skill_name,
            "session_id": effective_session,
            "runtime": runtime,
            "metadata": {
                "response_mode": mode,
                "model": effective_model,
                "done_reason": str(completion_meta.get("done_reason") or ""),
                "truncated": bool(completion_meta.get("truncated")),
                "continuation_used": bool(completion_meta.get("continuation_used")),
                "continuation_done_reason": str(completion_meta.get("continuation_done_reason") or ""),
                "knowledge_sources": list(retrieval.get("sources") or []),
                "knowledge_query_terms": list(retrieval.get("query_terms") or []),
                "vantage_context": str((retrieval.get("vantage") or {}).get("context") or ""),
                "vantage_sources": list((retrieval.get("vantage") or {}).get("sources") or []),
                "vantage_modules": list((retrieval.get("vantage") or {}).get("modules") or []),
            },
        },
    )

    yield {
        "event": "final",
        "data": {
            "type": "message",
            "content": content,
            "skill": skill_name,
            "session_id": effective_session,
            "runtime": runtime,
            "metadata": {
                "response_mode": mode,
                "model": effective_model,
                "done_reason": str(completion_meta.get("done_reason") or ""),
                "truncated": bool(completion_meta.get("truncated")),
                "continuation_used": bool(completion_meta.get("continuation_used")),
                "continuation_done_reason": str(completion_meta.get("continuation_done_reason") or ""),
                "knowledge_sources": list(retrieval.get("sources") or []),
                "knowledge_query_terms": list(retrieval.get("query_terms") or []),
                "vantage_context": str((retrieval.get("vantage") or {}).get("context") or ""),
                "vantage_sources": list((retrieval.get("vantage") or {}).get("sources") or []),
                "vantage_modules": list((retrieval.get("vantage") or {}).get("modules") or []),
            },
        },
    }


def generate_chat_reply(
    message: str,
    session_id: str = "",
    cliente: str = "",
    response_mode: str = _DEFAULT_RESPONSE_MODE,
) -> dict[str, str]:
    final_response: dict[str, str] | None = None
    for event in stream_chat_reply_events(
        message,
        session_id=session_id,
        cliente=cliente,
        response_mode=response_mode,
    ):
        if event.get("event") == "final":
            data = event.get("data")
            if isinstance(data, dict):
                final_response = data  # type: ignore[assignment]

    return final_response or {
        "type": "error",
        "message": "Falha ao consolidar a resposta do chat.",
        "session_id": session_id or "default",
    }
