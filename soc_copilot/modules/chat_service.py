from __future__ import annotations

import json
import logging
from time import perf_counter
from typing import Iterator, List

import requests

from soc_copilot import config as cfg
from soc_copilot.modules import persistence
from soc_copilot.modules.soc_copilot_loader import build_prompt_context, choose_skill
from socc.core import knowledge_base as knowledge_base_runtime
from socc.gateway.llm_gateway import (
    inference_guard,
    record_prompt_audit,
    record_inference_event,
    resolve_runtime,
    runtime_brief,
)

_logger = logging.getLogger(__name__)
_MAX_HISTORY_MESSAGES = 8
_STREAM_CHUNK_SIZE = 120


def _detect_artifact_type(message: str) -> str | None:
    text = (message or "").lower()
    if any(token in text for token in ("subject:", "from:", "reply-to", "attachment", "email")):
        return "email"
    if "http://" in text or "https://" in text or "www." in text:
        return "url"
    if any(token in text for token in ("powershell", "cmd.exe", "rundll32", "schtasks", "registry")):
        return "malware"
    return None


def select_skill(message: str, artifact_type: str | None = None) -> str:
    return choose_skill(message, artifact_type=artifact_type or _detect_artifact_type(message))


def _format_history(session_id: str) -> str:
    history = persistence.list_chat_messages(session_id, limit=_MAX_HISTORY_MESSAGES)
    if not history:
        return ""
    lines: List[str] = []
    for item in history:
        role = "usuario" if item.get("role") == "user" else "assistente"
        content = item.get("content", "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines[-_MAX_HISTORY_MESSAGES:])


def _build_system_prompt(context: dict[str, str]) -> str:
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
        (
            "Regras de saida: responda em PT-BR, seja tecnico e objetivo, "
            "nao invente fatos, diferencie observacao de inferencia, e use markdown simples quando ajudar."
        ),
    ]
    return "\n\n".join(section for section in sections if section)


def _build_user_prompt(message: str, cliente: str, context: dict[str, str]) -> str:
    parts = []
    if cliente:
        parts.append(f"Cliente: {cliente}")
    if context.get("session_context"):
        parts.append("Contexto recente da sessao:")
        parts.append(context["session_context"])
    if context.get("knowledge_context"):
        parts.append("Contexto recuperado da base local:")
        parts.append(context["knowledge_context"])
    parts.append("Pedido atual do usuario:")
    parts.append(message.strip())
    parts.append(
        "Se a entrada nao trouxer evidencia suficiente, explicite as limitacoes e proponha proximos passos seguros."
    )
    return "\n\n".join(part for part in parts if part)


def _fallback_response(message: str, skill_name: str) -> str:
    return (
        f"Recebi sua mensagem e selecionei a skill `{skill_name}` para este contexto. "
        "A conversa geral com a LLM local ainda depende de `LLM_ENABLED=true`, mas a camada do SOC Copilot "
        "ja esta pronta para orientar o comportamento do chat. "
        "Se voce colar um payload, o pipeline analitico atual continua funcionando normalmente.\n\n"
        f"Resumo do pedido: {message.strip()[:400]}"
    )


def _prepare_chat_context(
    message: str,
    session_id: str = "",
    cliente: str = "",
) -> tuple[str, str, dict[str, str], list[dict[str, str]], dict[str, object]]:
    effective_session = session_id or "default"
    skill_name = select_skill(message)
    persistence.ensure_chat_session(
        session_id=effective_session,
        cliente=cliente,
        titulo=message.strip()[:80],
    )
    session_context = _format_history(effective_session)
    retrieval = knowledge_base_runtime.search_knowledge_base(query_text=message)
    knowledge_context = knowledge_base_runtime.format_retrieval_context(retrieval)
    source_labels = ", ".join(
        str(item.get("source_name") or item.get("source_id") or "")
        for item in (retrieval.get("sources") or [])
        if str(item.get("source_name") or item.get("source_id") or "")
    )
    context = build_prompt_context(
        user_input=message,
        artifact_type=_detect_artifact_type(message),
        session_context=session_context,
        selected_skill=skill_name,
        knowledge_context=knowledge_context,
        knowledge_sources=source_labels,
    )
    history_messages = [
        {"role": item.get("role", "user"), "content": item.get("content", "")}
        for item in persistence.list_chat_messages(
            effective_session, limit=_MAX_HISTORY_MESSAGES
        )
    ]
    return effective_session, skill_name, context, history_messages, retrieval


def _persist_chat_exchange(
    *,
    session_id: str,
    message: str,
    skill_name: str,
    content: str,
) -> None:
    persistence.save_chat_message(
        session_id=session_id,
        role="user",
        content=message,
        skill=skill_name,
        metadata={"type": "message"},
    )
    persistence.save_chat_message(
        session_id=session_id,
        role="assistant",
        content=content,
        skill=skill_name,
        metadata={"type": "message"},
    )


def _chunk_text(text: str, chunk_size: int = _STREAM_CHUNK_SIZE) -> Iterator[str]:
    content = (text or "").strip()
    if not content:
        return
    for index in range(0, len(content), max(1, chunk_size)):
        yield content[index : index + max(1, chunk_size)]


def _stream_ollama(messages: list[dict[str, str]]) -> Iterator[str]:
    runtime = resolve_runtime()
    base_url = getattr(cfg, "OLLAMA_URL", "http://localhost:11434").rstrip("/")
    model = getattr(cfg, "OLLAMA_MODEL", "qwen2.5:3b")
    timeout = float(getattr(cfg, "LLM_TIMEOUT", 60))

    body = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {"temperature": 0.2},
    }
    started = perf_counter()
    resp = None
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
            delta = (payload.get("message") or {}).get("content") or ""
            if delta:
                yield delta
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


def _call_ollama(messages: list[dict[str, str]]) -> str:
    prompt_blob = "\n\n".join(
        f"{item.get('role', 'user')}: {item.get('content', '')}"
        for item in messages
    )
    record_prompt_audit(
        source="chat_service",
        provider="ollama",
        model=getattr(cfg, "OLLAMA_MODEL", "qwen2.5:3b"),
        prompt_text=prompt_blob,
    )
    return "".join(_stream_ollama(messages)).strip()


def stream_chat_reply_events(
    message: str,
    session_id: str = "",
    cliente: str = "",
) -> Iterator[dict[str, object]]:
    effective_session, skill_name, context, history_messages, retrieval = _prepare_chat_context(
        message,
        session_id=session_id,
        cliente=cliente,
    )
    runtime = runtime_brief()
    yield {
        "event": "meta",
        "session_id": effective_session,
        "skill": skill_name,
        "runtime": runtime,
    }

    content = ""
    if not getattr(cfg, "LLM_ENABLED", False):
        content = _fallback_response(message, skill_name)
        for delta in _chunk_text(content):
            yield {"event": "delta", "delta": delta, "skill": skill_name}
    else:
        messages = [{"role": "system", "content": _build_system_prompt(context)}]
        messages.extend(history_messages)
        messages.append(
            {"role": "user", "content": _build_user_prompt(message, cliente, context)}
        )
        try:
            if getattr(cfg, "LLM_PROVIDER", "ollama").lower() != "ollama":
                content = _fallback_response(message, skill_name)
                for delta in _chunk_text(content):
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
                        for delta in _chunk_text(content):
                            yield {"event": "delta", "delta": delta, "skill": skill_name}
                    else:
                        parts: list[str] = []
                        for delta in _stream_ollama(messages):
                            parts.append(delta)
                            yield {"event": "delta", "delta": delta, "skill": skill_name}
                        content = "".join(parts).strip()
        except Exception as exc:
            _logger.exception("Falha ao consultar a LLM local no chat do SOC Copilot.")
            content = (
                f"Falha ao consultar a LLM local: {exc}. "
                f"Skill selecionada: `{skill_name}`."
            )
            for delta in _chunk_text(content):
                yield {"event": "delta", "delta": delta, "skill": skill_name}

    _persist_chat_exchange(
        session_id=effective_session,
        message=message,
        skill_name=skill_name,
        content=content,
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
                "knowledge_sources": list(retrieval.get("sources") or []),
                "knowledge_query_terms": list(retrieval.get("query_terms") or []),
            },
        },
    }


def generate_chat_reply(
    message: str,
    session_id: str = "",
    cliente: str = "",
) -> dict[str, str]:
    final_response: dict[str, str] | None = None
    for event in stream_chat_reply_events(
        message,
        session_id=session_id,
        cliente=cliente,
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
