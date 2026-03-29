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
    resolve_api_key,
    resolve_auth_context,
    resolve_runtime,
    runtime_brief,
    supported_backend_specs,
)

_logger = logging.getLogger(__name__)
_STREAM_CHUNK_SIZE = 120
_DEFAULT_RESPONSE_MODE = "balanced"
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


def _normalize_backend_selection(value: str = "") -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "anthropic": "anthropic",
        "claude": "anthropic",
        "ollama": "ollama",
        "openai": "openai-compatible",
        "openai-compatible": "openai-compatible",
        "codex": "openai-compatible",
        "lmstudio": "openai-compatible",
        "vllm": "openai-compatible",
    }
    return aliases.get(raw, raw)


def _chat_max_tokens(response_mode: str = _DEFAULT_RESPONSE_MODE) -> int:
    mode = normalize_response_mode(response_mode)
    return {
        "fast": 220,
        "balanced": 520,
        "deep": 900,
    }.get(mode, 520)


def _serialize_messages(messages: list[dict[str, str]]) -> str:
    return "\n\n".join(
        f"{item.get('role', 'user')}: {item.get('content', '')}"
        for item in messages
    )


def _resolve_chat_target(
    *,
    response_mode: str = _DEFAULT_RESPONSE_MODE,
    selected_backend: str = "",
    selected_model: str = "",
) -> dict[str, str]:
    runtime_cfg = resolve_runtime()
    backend = _normalize_backend_selection(selected_backend) or runtime_cfg.backend or "ollama"
    if backend not in {"ollama", "anthropic", "openai-compatible"}:
        backend = "ollama"

    model = str(selected_model or "").strip()
    endpoint = ""
    provider = backend
    device = runtime_cfg.device if backend == "ollama" else "remote"

    if backend == "ollama":
        provider = "ollama"
        endpoint = getattr(cfg, "OLLAMA_URL", "http://localhost:11434").rstrip("/")
        model = model or resolve_ollama_model_for_mode(response_mode)
    elif backend == "anthropic":
        provider = "anthropic"
        endpoint = "https://api.anthropic.com/v1/messages"
        model = model or os.getenv("LLM_MODEL", getattr(cfg, "LLM_MODEL", "claude-haiku-4-5-20251001"))
    else:
        provider = "openai-compatible"
        endpoint = os.getenv("SOCC_OPENAI_COMPAT_URL", "").strip().rstrip("/") or "https://api.openai.com/v1"
        model = model or os.getenv("SOCC_OPENAI_COMPAT_MODEL", "").strip() or "gpt-5-codex"

    return {
        "backend": backend,
        "provider": provider,
        "endpoint": endpoint,
        "model": model,
        "device": device,
    }


def _build_selected_runtime(target: dict[str, str]) -> dict[str, object]:
    spec = supported_backend_specs().get(str(target.get("backend") or "").strip().lower())
    runtime = dict(runtime_brief())
    if not spec:
        runtime.update(
            {
                "backend": str(target.get("backend") or runtime.get("backend") or "ollama"),
                "provider": str(target.get("provider") or runtime.get("provider") or "ollama"),
                "model": str(target.get("model") or runtime.get("model") or ""),
                "device": str(target.get("device") or runtime.get("device") or "cpu"),
            }
        )
        return runtime

    runtime.update(
        {
            "backend": spec.key,
            "backend_label": spec.label,
            "backend_family": spec.family,
            "provider": str(target.get("provider") or spec.provider),
            "model": str(target.get("model") or runtime.get("model") or ""),
            "device": str(target.get("device") or runtime.get("device") or "cpu"),
            "backend_local": bool(spec.local),
            "backend_gpu_supported": bool(spec.gpu_supported),
            "backend_streaming_supported": bool(spec.streaming_supported),
            "backend_embeddings_supported": bool(spec.embeddings_supported),
        }
    )
    return runtime


def _detect_artifact_type(message: str) -> str | None:
    text = (message or "").lower()
    if any(token in text for token in ("subject:", "from:", "reply-to", "attachment", "email")):
        return "email"
    if "http://" in text or "https://" in text or "www." in text:
        return "url"
    if any(token in text for token in ("powershell", "cmd.exe", "rundll32", "schtasks", "registry")):
        return "malware"
    return None


def _is_lightweight_chat(message: str) -> bool:
    text = str(message or "").strip().lower()
    if not text:
        return False
    if _detect_artifact_type(text):
        return False
    if "http://" in text or "https://" in text or "\n" in text:
        return False
    tokens = [token for token in text.replace("?", " ").replace("!", " ").split() if token]
    if len(tokens) > 8:
        return False
    lightweight_phrases = {
        "oi",
        "ola",
        "olá",
        "bom dia",
        "boa tarde",
        "boa noite",
        "tudo bem",
        "pode seguir",
        "proximo passo",
        "próximo passo",
        "continue",
        "seguir",
        "hello",
        "hi",
    }
    if text in lightweight_phrases:
        return True
    return len(tokens) <= 3


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


def _prepare_chat_context(
    message: str,
    session_id: str = "",
    cliente: str = "",
    response_mode: str = _DEFAULT_RESPONSE_MODE,
) -> tuple[str, str, dict[str, str], list[dict[str, str]], dict[str, object]]:
    effective_session = session_id or "default"
    profile = response_mode_profile(response_mode)
    lightweight = _is_lightweight_chat(message)
    history_limit = 1 if lightweight else int(profile.get("history_limit") or 5)
    kb_limit = 0 if lightweight else int(profile.get("kb_limit") or 3)
    kb_chars = 0 if lightweight else int(profile.get("kb_chars") or 1100)
    skill_name = select_skill(message)
    persistence.ensure_chat_session(
        session_id=effective_session,
        cliente=cliente,
        titulo=message.strip()[:80],
    )
    session_context = "" if lightweight else _format_history(effective_session, limit=history_limit)
    retrieval = (
        {"sources": [], "matches": [], "query_terms": []}
        if lightweight
        else knowledge_base_runtime.search_knowledge_base(query_text=message, limit=kb_limit)
    )
    knowledge_context = (
        ""
        if lightweight
        else knowledge_base_runtime.format_retrieval_context(retrieval, max_chars=kb_chars)
    )
    vantage = (
        {"context": "", "sources": [], "matches": [], "modules": []}
        if lightweight
        else vantage_gateway.retrieve_context(message)
    )
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
    retrieval["vantage"] = vantage
    retrieval["sources"] = list(retrieval.get("sources") or []) + list(vantage.get("sources") or [])
    retrieval["matches"] = list(retrieval.get("matches") or []) + list(vantage.get("matches") or [])
    retrieval["lightweight"] = lightweight
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
    model_override: str = "",
    num_predict_override: int | None = None,
) -> Iterator[dict[str, object]]:
    runtime = resolve_runtime()
    base_url = getattr(cfg, "OLLAMA_URL", "http://localhost:11434").rstrip("/")
    model = str(model_override or "").strip() or resolve_ollama_model_for_mode(response_mode)
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
    model_override: str = "",
    num_predict_override: int | None = None,
) -> Iterator[str]:
    for item in _stream_ollama_events(
        messages,
        response_mode=response_mode,
        model_override=model_override,
        num_predict_override=num_predict_override,
    ):
        if item.get("kind") == "delta":
            yield str(item.get("delta") or "")


def _call_ollama(
    messages: list[dict[str, str]],
    *,
    response_mode: str = _DEFAULT_RESPONSE_MODE,
    model_override: str = "",
) -> str:
    prompt_blob = _serialize_messages(messages)
    record_prompt_audit(
        source="chat_service",
        provider="ollama",
        model=str(model_override or "").strip() or resolve_ollama_model_for_mode(response_mode),
        prompt_text=prompt_blob,
    )
    return "".join(
        _stream_ollama(messages, response_mode=response_mode, model_override=model_override)
    ).strip()


def _extract_openai_content(payload: dict[str, object]) -> str:
    choices = list(payload.get("choices") or []) if isinstance(payload, dict) else []
    if not choices:
        return ""
    message = dict((choices[0] or {}).get("message") or {})
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if text:
                parts.append(text)
        return "".join(parts).strip()
    return ""


def _call_anthropic(
    messages: list[dict[str, str]],
    *,
    response_mode: str = _DEFAULT_RESPONSE_MODE,
    model: str,
) -> str:
    auth = resolve_auth_context("anthropic")
    credential = str(auth.get("credential") or "")
    auth_method = str(auth.get("method") or "none")
    if not credential:
        raise RuntimeError("Credencial Anthropic não configurada.")

    system_prompt = ""
    request_messages: list[dict[str, str]] = []
    for item in messages:
        role = str(item.get("role") or "user").strip().lower()
        content = str(item.get("content") or "")
        if role == "system":
            system_prompt = f"{system_prompt}\n\n{content}".strip() if system_prompt else content
            continue
        request_messages.append({"role": "assistant" if role == "assistant" else "user", "content": content})

    timeout = float(getattr(cfg, "LLM_TIMEOUT", 60))
    profile = response_mode_profile(response_mode)
    prompt_blob = _serialize_messages(messages)
    record_prompt_audit(
        source="chat_service",
        provider="anthropic",
        model=model,
        prompt_text=prompt_blob,
    )
    started = perf_counter()
    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                **(
                    {"Authorization": f"Bearer {credential}"}
                    if auth_method == "oauth"
                    else {"x-api-key": credential}
                ),
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "system": system_prompt,
                "messages": request_messages,
                "max_tokens": _chat_max_tokens(response_mode),
                "temperature": float(profile.get("temperature") or 0.15),
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        content = "".join(
            str(item.get("text") or "")
            for item in list(payload.get("content") or [])
            if isinstance(item, dict) and str(item.get("type") or "") == "text"
        ).strip()
        record_inference_event(
            source="chat_service",
            provider="anthropic",
            model=model,
            requested_device="remote",
            effective_device="remote",
            latency_ms=(perf_counter() - started) * 1000,
            success=True,
            fallback_used=False,
        )
        return content
    except Exception as exc:
        record_inference_event(
            source="chat_service",
            provider="anthropic",
            model=model,
            requested_device="remote",
            effective_device="remote",
            latency_ms=(perf_counter() - started) * 1000,
            success=False,
            fallback_used=False,
            error=str(exc),
        )
        raise


def _call_openai_compatible(
    messages: list[dict[str, str]],
    *,
    response_mode: str = _DEFAULT_RESPONSE_MODE,
    model: str,
    endpoint: str,
) -> str:
    if not endpoint:
        raise RuntimeError("SOCC_OPENAI_COMPAT_URL não configurada.")
    if not model:
        raise RuntimeError("SOCC_OPENAI_COMPAT_MODEL não configurado.")

    auth = resolve_auth_context("openai-compatible")
    api_key = str(auth.get("credential") or "")
    headers = {"content-type": "application/json"}
    if api_key:
        headers["authorization"] = f"Bearer {api_key}"

    timeout = float(getattr(cfg, "LLM_TIMEOUT", 60))
    profile = response_mode_profile(response_mode)
    prompt_blob = _serialize_messages(messages)
    record_prompt_audit(
        source="chat_service",
        provider="openai-compatible",
        model=model,
        prompt_text=prompt_blob,
    )
    started = perf_counter()
    try:
        response = requests.post(
            f"{endpoint.rstrip('/')}/chat/completions",
            headers=headers,
            json={
                "model": model,
                "messages": messages,
                "temperature": float(profile.get("temperature") or 0.15),
                "max_tokens": _chat_max_tokens(response_mode),
                "stream": False,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        content = _extract_openai_content(payload)
        record_inference_event(
            source="chat_service",
            provider="openai-compatible",
            model=model,
            requested_device="remote",
            effective_device="remote",
            latency_ms=(perf_counter() - started) * 1000,
            success=True,
            fallback_used=False,
        )
        return content
    except Exception as exc:
        record_inference_event(
            source="chat_service",
            provider="openai-compatible",
            model=model,
            requested_device="remote",
            effective_device="remote",
            latency_ms=(perf_counter() - started) * 1000,
            success=False,
            fallback_used=False,
            error=str(exc),
        )
        raise


def stream_chat_reply_events(
    message: str,
    session_id: str = "",
    cliente: str = "",
    response_mode: str = _DEFAULT_RESPONSE_MODE,
    selected_backend: str = "",
    selected_model: str = "",
) -> Iterator[dict[str, object]]:
    mode = normalize_response_mode(response_mode)
    profile = response_mode_profile(mode)
    selected_target = _resolve_chat_target(
        response_mode=mode,
        selected_backend=selected_backend,
        selected_model=selected_model,
    )
    effective_model = str(selected_target.get("model") or "")
    effective_session, skill_name, context, history_messages, retrieval = _prepare_chat_context(
        message,
        session_id=session_id,
        cliente=cliente,
        response_mode=mode,
    )
    runtime = _build_selected_runtime(
        {
            **selected_target,
            "model": effective_model,
        }
    )
    yield {
        "event": "meta",
        "session_id": effective_session,
        "skill": skill_name,
        "runtime": runtime,
        "response_mode": mode,
        "model": effective_model,
        "selected_backend": str(selected_target.get("backend") or ""),
    }

    content = ""
    lightweight = bool(retrieval.get("lightweight"))
    completion_meta: dict[str, object] = {
        "done_reason": "",
        "truncated": False,
        "continuation_used": False,
        "continuation_done_reason": "",
    }
    if not getattr(cfg, "LLM_ENABLED", False):
        content = _fallback_response(message, skill_name)
        for delta in _chunk_text(content, chunk_size=int(profile.get("chunk_size") or _STREAM_CHUNK_SIZE)):
            yield {"event": "delta", "delta": delta, "skill": skill_name}
    else:
        messages = [{"role": "system", "content": _build_system_prompt(context, response_mode=mode)}]
        messages.extend(history_messages)
        messages.append(
            {"role": "user", "content": _build_user_prompt(message, cliente, context, response_mode=mode)}
        )
        try:
            if selected_target["backend"] == "ollama":
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
                        num_predict_override = 96 if lightweight else None
                        for item in _stream_ollama_events(
                            messages,
                            response_mode=mode,
                            model_override=effective_model,
                            num_predict_override=num_predict_override,
                        ):
                            if item.get("kind") == "delta":
                                delta = str(item.get("delta") or "")
                                parts.append(delta)
                                yield {"event": "delta", "delta": delta, "skill": skill_name}
                            else:
                                completion_meta.update(dict(item))
                        content = "".join(parts).strip()
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
                                model_override=effective_model,
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
                            content = f"{content}{''.join(continuation_parts)}".strip()
            elif selected_target["backend"] == "anthropic":
                content = _call_anthropic(messages, response_mode=mode, model=effective_model)
                for delta in _chunk_text(content, chunk_size=int(profile.get("chunk_size") or _STREAM_CHUNK_SIZE)):
                    yield {"event": "delta", "delta": delta, "skill": skill_name}
            elif selected_target["backend"] == "openai-compatible":
                content = _call_openai_compatible(
                    messages,
                    response_mode=mode,
                    model=effective_model,
                    endpoint=str(selected_target.get("endpoint") or ""),
                )
                for delta in _chunk_text(content, chunk_size=int(profile.get("chunk_size") or _STREAM_CHUNK_SIZE)):
                    yield {"event": "delta", "delta": delta, "skill": skill_name}
            else:
                content = _fallback_response(message, skill_name)
                for delta in _chunk_text(content, chunk_size=int(profile.get("chunk_size") or _STREAM_CHUNK_SIZE)):
                    yield {"event": "delta", "delta": delta, "skill": skill_name}
        except Exception as exc:
            _logger.exception("Falha ao consultar a LLM no chat do SOC Copilot.")
            content = (
                f"Falha ao consultar a LLM selecionada: {exc}. "
                f"Skill selecionada: `{skill_name}`."
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
                "selected_backend": str(selected_target.get("backend") or ""),
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
                "selected_backend": str(selected_target.get("backend") or ""),
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
    selected_backend: str = "",
    selected_model: str = "",
) -> dict[str, str]:
    final_response: dict[str, str] | None = None
    for event in stream_chat_reply_events(
        message,
        session_id=session_id,
        cliente=cliente,
        response_mode=response_mode,
        selected_backend=selected_backend,
        selected_model=selected_model,
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
