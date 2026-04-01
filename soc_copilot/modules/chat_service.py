from __future__ import annotations

import json
import logging
import os
from time import perf_counter
from typing import Iterator, List
from urllib.parse import urlparse

import requests

from soc_copilot import config as cfg
from soc_copilot.modules import persistence
from soc_copilot.modules.soc_copilot_loader import build_prompt_context, choose_skill
from socc.core import knowledge_base as knowledge_base_runtime
from socc.core.context_budget import (
    apply_budget_to_prompt_context,
    estimate_tokens,
    ContextBudgetResult,
)
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
_OPENAI_CODEX_BASE_URL = "https://chatgpt.com/backend-api"
_RESPONSE_MODE_PROFILES = {
    "fast": {
        "label": "Fast",
        "history_limit": 4,
        "kb_limit": 1,
        "kb_chars": 800,
        "chunk_size": 160,
        "temperature": 0.1,
        "num_ctx": 8192,
        "instruction": (
            "Modo FAST: responda com objetividade, priorizando conclusão, "
            "evidências essenciais e próximos passos. Respostas diretas e completas."
        ),
    },
    "balanced": {
        "label": "Balanced",
        "history_limit": 10,
        "kb_limit": 4,
        "kb_chars": 2000,
        "chunk_size": 120,
        "temperature": 0.15,
        "num_ctx": 32768,
        "instruction": (
            "Modo BALANCED: mantenha objetividade e preserve contexto suficiente "
            "para análise SOC completa, explicável e útil. Responda sem truncar."
        ),
    },
    "deep": {
        "label": "Deep",
        "history_limit": 20,
        "kb_limit": 6,
        "kb_chars": 4000,
        "chunk_size": 100,
        "temperature": 0.2,
        "num_ctx": 65536,
        "instruction": (
            "Modo DEEP: análise aprofundada. Explicite hipóteses, evidências, "
            "limitações, impacto e próximos passos com máximo detalhe. Não trunce."
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


def resolve_ollama_model_for_mode(
    response_mode: str = _DEFAULT_RESPONSE_MODE,
    skill_name: str = "",
) -> str:
    mode = normalize_response_mode(response_mode)
    primary = getattr(cfg, "OLLAMA_MODEL", "qwen3.5:9b")
    fast_model = os.getenv("SOCC_OLLAMA_FAST_MODEL", "llama3.2:3b").strip() or primary
    balanced_model = os.getenv("SOCC_OLLAMA_BALANCED_MODEL", primary).strip() or primary
    deep_model = os.getenv("SOCC_OLLAMA_DEEP_MODEL", primary).strip() or primary

    # Skill de chat livre (soc-generalist) → sempre usa o modelo mais capaz disponível
    # pra não ter o problema do llama3.2:3b não conseguir seguir persona e tom
    if skill_name in {"soc-generalist", ""} and mode in {"balanced", "deep"}:
        return deep_model or balanced_model or primary

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
        "fast":     2048,
        "balanced": 8192,
        "deep":     16384,
    }.get(mode, 8192)


def _is_openai_oauth_transport(endpoint: str, auth_method: str) -> bool:
    normalized_endpoint = str(endpoint or "").strip().rstrip("/")
    return auth_method == "oauth" and normalized_endpoint == _OPENAI_CODEX_BASE_URL


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _llm_chat_enabled(target: dict[str, str]) -> bool:
    if not _env_flag("LLM_ENABLED", bool(getattr(cfg, "LLM_ENABLED", False))):
        return False

    backend = str(target.get("backend") or "").strip().lower()
    endpoint = str(target.get("endpoint") or "").strip()
    if backend == "anthropic":
        auth = resolve_auth_context("anthropic")
        return bool(auth.get("credential"))
    if backend == "openai-compatible":
        if not endpoint:
            return False
        host = (urlparse(endpoint).hostname or "").strip().lower()
        if host in {"127.0.0.1", "localhost", "::1"}:
            return True
        auth = resolve_auth_context("openai-compatible")
        return bool(auth.get("credential"))
    return bool(endpoint)


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
        auth = resolve_auth_context("openai-compatible")
        endpoint = os.getenv("SOCC_OPENAI_COMPAT_URL", "").strip().rstrip("/")
        if auth.get("method") == "oauth" and endpoint in {"", "https://api.openai.com/v1"}:
            endpoint = _OPENAI_CODEX_BASE_URL
        elif not endpoint:
            endpoint = "https://api.openai.com/v1"
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


def _apply_context_budget(
    context: dict[str, str],
    *,
    model_name: str,
    response_mode: str,
) -> tuple[dict[str, str], ContextBudgetResult | None]:
    """Aplica budget de contexto. Retorna (context_ajustado, budget_result)."""
    if not model_name:
        return context, None
    effective_context, budget_result = apply_budget_to_prompt_context(
        model_name=model_name,
        response_mode=response_mode,
        context=context,
        user_input=context.get("user_input", ""),
    )
    metrics = budget_result.metrics()
    _logger.info(
        "Context budget: model=%s utilization=%.0f%% overflow=%s",
        metrics.get("model"),
        metrics.get("utilization_pct", 0),
        metrics.get("overflow"),
    )
    if budget_result.overflow:
        _logger.warning(
            "Context budget overflow: %d tokens over limit for model %s",
            budget_result.overflow_tokens,
            model_name,
        )
    return effective_context, budget_result


def _build_system_prompt(context: dict[str, str], *, response_mode: str = _DEFAULT_RESPONSE_MODE) -> str:
    """Constrói o system prompt a partir de um context já ajustado pelo budget."""
    profile = response_mode_profile(response_mode)

    sections = [
        context.get("identity", ""),
        "Siga a persona e regras abaixo.",
        context.get("soul", ""),
        context.get("user", ""),
        context.get("agents", ""),
        context.get("memory", ""),
        context.get("tools", ""),
    ]

    # References: só inclui as que sobreviveram ao budget
    ref_sections = []
    for ref_key in ("evidence_rules", "ioc_extraction", "security_json_patterns",
                    "telemetry_investigation_patterns", "mitre_guidance", "output_contract"):
        ref_content = context.get(ref_key, "")
        if ref_content:
            ref_sections.append(ref_content)

    if ref_sections:
        sections.append("Referencias operacionais compartilhadas:")
        sections.extend(ref_sections)

    sections.extend([
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
    ])
    return "\n\n".join(section for section in sections if section)


def _build_user_prompt(
    message: str,
    cliente: str,
    context: dict[str, str],
    *,
    response_mode: str = _DEFAULT_RESPONSE_MODE,
    has_history_messages: bool = False,
) -> str:
    mode = normalize_response_mode(response_mode)
    selected_skill = str(context.get("selected_skill") or "").strip()
    parts = []
    if cliente:
        parts.append(f"Cliente: {cliente}")
    parts.append(f"Modo de resposta: {mode}")
    if selected_skill:
        parts.append(f"Skill ativa: {selected_skill}")
    # Evita duplicar histórico: session_context no prompt só quando
    # não existem history_messages passadas diretamente para a API.
    if not has_history_messages and context.get("session_context"):
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
            "A camada da conversa natural ja esta preparada, mas a resposta livre completa ainda depende de um backend LLM ativo.\n\n"
            "Enquanto isso, eu preservo o contexto da conversa e continuo apto a analisar payloads, IOCs e artefatos quando voce trouxer mais dados.\n\n"
            f"Pergunta registrada: {message.strip()[:400]}"
        )
    return (
        f"Recebi sua mensagem e selecionei a skill `{skill_name}` para este contexto. "
        "A conversa geral com a LLM ainda depende de um backend ativo, mas a camada do SOC Copilot "
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
    lightweight = _is_lightweight_chat(message)
    history_limit = 1 if lightweight else int(profile.get("history_limit") or 5)
    kb_limit = 0 if lightweight else int(profile.get("kb_limit") or 3)
    kb_chars = 0 if lightweight else int(profile.get("kb_chars") or 1100)
    skill_name = select_skill(message)
    # Passa título vazio — o título real será gerado via LLM após o primeiro turno.
    # O ON CONFLICT do ensure_chat_session só sobrescreve título não-vazio,
    # então passar vazio aqui garante que títulos gerados nunca sejam sobrescritos.
    persistence.ensure_chat_session(
        session_id=effective_session,
        cliente=cliente,
        titulo="",
    )
    session_context = "" if lightweight else _format_history(effective_session, limit=history_limit)
    artifact_context = "" if lightweight else _find_recent_artifact_context(effective_session, message)
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
    retrieval["lightweight"] = lightweight
    return effective_session, skill_name, context, history_messages, retrieval


def _generate_session_title(message: str, response: str, selected_target: dict) -> str:
    """Gera um título curto para a sessão via LLM baseado no primeiro turno.
    
    Usa o backend/modelo já configurado. Retorna string vazia em caso de falha.
    Prompt minimalista — resposta esperada: 3-6 palavras, sem pontuação final.
    """
    try:
        prompt = (
            "Gere um título curto (3 a 6 palavras, sem pontuação final) para uma conversa "
            "que começa com a mensagem do usuário abaixo. Responda SOMENTE o título, "
            "sem aspas, sem explicação.\n\n"
            f"Mensagem: {message.strip()[:300]}\n"
            f"Resposta inicial: {response.strip()[:300]}"
        )
        messages = [{"role": "user", "content": prompt}]
        backend = str(selected_target.get("backend") or "").lower()

        if backend == "ollama":
            runtime_cfg = resolve_runtime()
            model = resolve_ollama_model_for_mode("fast")
            base_url = getattr(cfg, "OLLAMA_URL", "http://localhost:11434").rstrip("/")
            timeout = float(getattr(cfg, "LLM_TIMEOUT", 60))
            body = {
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {"num_predict": 32, "temperature": 0.3},
            }
            resp = requests.post(
                f"{base_url}/api/chat",
                json=body,
                timeout=min(timeout, 30),
            )
            resp.raise_for_status()
            data = resp.json()
            title = str(data.get("message", {}).get("content") or "").strip()
        else:
            # Anthropic / OpenAI-compatible
            auth = resolve_auth_context(backend=backend, model="")
            api_key = auth.get("api_key") or resolve_api_key(backend)
            model = str(selected_target.get("model") or "").strip()
            if not model:
                import os as _os
                model = _os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001")
            if "anthropic" in backend or "claude" in model.lower():
                base_url = "https://api.anthropic.com/v1"
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                }
                if auth.get("auth_type") == "oauth":
                    headers = {
                        "Authorization": f"Bearer {api_key}",
                        "anthropic-version": "2023-06-01",
                        "anthropic-beta": "oauth-2025-04-20",
                        "content-type": "application/json",
                    }
                body = {
                    "model": model,
                    "max_tokens": 32,
                    "messages": messages,
                }
                resp = requests.post(
                    f"{base_url}/messages",
                    headers=headers,
                    json=body,
                    timeout=20,
                )
                resp.raise_for_status()
                data = resp.json()
                title = str((data.get("content") or [{}])[0].get("text") or "").strip()
            else:
                # OpenAI-compatible
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "content-type": "application/json",
                }
                base_url = getattr(cfg, "OPENAI_BASE_URL", "https://api.openai.com/v1")
                body = {
                    "model": model,
                    "max_tokens": 32,
                    "messages": messages,
                    "temperature": 0.3,
                }
                resp = requests.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=body,
                    timeout=20,
                )
                resp.raise_for_status()
                data = resp.json()
                title = str(
                    (data.get("choices") or [{}])[0]
                    .get("message", {})
                    .get("content") or ""
                ).strip()

        # Sanitiza: remove aspas, pontuação final, limita tamanho
        import re as _re
        title = _re.sub(r'^["\']|["\']$', "", title).strip().rstrip(".,;:")
        return title[:80] if title else ""
    except Exception as exc:
        _logger.debug("Falha ao gerar título de sessão: %s", exc)
        return ""


def _handle_memory_persistence(message: str, response: str, session_id: str) -> None:
    """If the user asked to remember something, persist it to agent memory."""
    try:
        from socc.core.agent_memory import (
            should_remember,
            extract_memory_fact,
            append_long_term_memory,
            append_daily_note,
        )
        if should_remember(message):
            fact = extract_memory_fact(message, response)
            if fact:
                append_long_term_memory(fact)
                _logger.info("Memória persistida: %s", fact[:80])
        # Sempre registra nota diária quando a skill for analítica
        append_daily_note(f"[sessão {session_id[:8]}] {message.strip()[:120]}")
    except Exception:
        pass


def _persist_chat_exchange(
    *,
    session_id: str,
    message: str,
    skill_name: str,
    content: str,
    assistant_payload: dict[str, object] | None = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
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
        tokens_in=tokens_in,
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
        tokens_out=tokens_out,
    )


def _chunk_text(text: str, chunk_size: int = _STREAM_CHUNK_SIZE) -> Iterator[str]:
    content = (text or "").strip()
    if not content:
        return
    for index in range(0, len(content), max(1, chunk_size)):
        yield content[index : index + max(1, chunk_size)]



_MAX_TOOL_ROUNDS = 5  # prevent infinite agentic loops


def _build_ollama_tools() -> list[dict]:
    """Convert registered ToolSpecs to Ollama tool definitions."""
    try:
        from socc.core.tools_registry import list_tools_specs
        tools = []
        for spec in list_tools_specs():
            params: dict = {"type": "object", "properties": {}, "required": []}
            for pname, pspec in (spec.parameters or {}).items():
                prop: dict = {"type": pspec.type, "description": pspec.description}
                if pspec.enum:
                    prop["enum"] = list(pspec.enum)
                params["properties"][pname] = prop
                if pspec.required:
                    params["required"].append(pname)
            tools.append({
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": params,
                },
            })
        return tools
    except Exception:
        return []


def _run_tool_calls(tool_calls: list[dict]) -> list[dict]:
    """Invoke tool calls returned by the model; return tool-role messages."""
    from socc.core.tools_registry import invoke_tool
    results = []
    for tc in tool_calls:
        fn = tc.get("function") or {}
        name = str(fn.get("name") or "")
        args = fn.get("arguments") or {}
        if not name:
            continue
        try:
            tr = invoke_tool(name, args if isinstance(args, dict) else {})
            content = json.dumps(tr.output, ensure_ascii=False) if tr.ok else json.dumps({"error": tr.error})
        except Exception as exc:
            content = json.dumps({"error": str(exc)})
        results.append({"role": "tool", "content": content})
    return results


def _stream_ollama_events(
    messages: list[dict[str, str]],
    *,
    response_mode: str = _DEFAULT_RESPONSE_MODE,
    model_override: str = "",
    num_predict_override: int | None = None,
    use_tools: bool = True,
) -> Iterator[dict[str, object]]:
    """Stream Ollama chat events, with optional agentic tool-call loop.

    When ``use_tools=True`` (default), registered tools are sent in the
    request.  If the model responds with ``tool_calls``, each tool is
    invoked locally and the result is fed back for up to
    ``_MAX_TOOL_ROUNDS`` rounds before a final text response is forced.

    Yields event dicts with ``kind`` in:
        "delta"       — incremental text token
        "tool_call"   — model requested a tool (name, args)
        "tool_result" — tool invocation result (truncated preview)
        "meta"        — completion metadata
    """
    runtime = resolve_runtime()
    base_url = getattr(cfg, "OLLAMA_URL", "http://localhost:11434").rstrip("/")
    model = str(model_override or "").strip() or resolve_ollama_model_for_mode(response_mode)
    timeout = float(getattr(cfg, "LLM_TIMEOUT", 60))
    profile = response_mode_profile(response_mode)

    base_body: dict = {
        "model": model,
        "stream": False,   # collect full response to inspect tool_calls
        "keep_alive": os.getenv("SOCC_OLLAMA_KEEP_ALIVE", "15m"),
        "options": {
            "temperature": float(profile.get("temperature") or 0.15),
            "num_ctx": int(profile.get("num_ctx") or 32768),
            "num_predict": -1,
        },
    }
    if num_predict_override is not None:
        base_body["options"]["num_predict"] = int(num_predict_override)

    ollama_tools = _build_ollama_tools() if use_tools else []

    started = perf_counter()
    active_messages = list(messages)
    final_payload: dict = {}

    for _round in range(_MAX_TOOL_ROUNDS + 1):
        is_last_round = (_round == _MAX_TOOL_ROUNDS)
        body = dict(base_body)
        body["messages"] = active_messages
        if ollama_tools and not is_last_round:
            body["tools"] = ollama_tools
        # last round: no tools → model must answer in plain text

        try:
            resp = requests.post(
                f"{base_url}/api/chat",
                json=body,
                timeout=timeout,
            )
            resp.raise_for_status()
            raw = resp.json()
            if isinstance(raw, dict):
                final_payload = raw
        except Exception as exc:
            record_inference_event(
                source="chat_service", provider="ollama", model=model,
                requested_device=runtime.device, effective_device=runtime.device,
                latency_ms=(perf_counter() - started) * 1000,
                success=False, fallback_used=False, error=str(exc),
            )
            raise

        msg = final_payload.get("message") or {}
        tool_calls = msg.get("tool_calls") or []

        if tool_calls and not is_last_round:
            # Emit tool events so the UI can show what's happening
            for tc in tool_calls:
                fn = tc.get("function") or {}
                yield {"kind": "tool_call", "tool": fn.get("name", ""), "args": fn.get("arguments", {})}

            # Execute tools and collect results
            active_messages.append({
                "role": "assistant",
                "content": str(msg.get("content") or ""),
                "tool_calls": tool_calls,
            })
            tool_results = _run_tool_calls(tool_calls)
            active_messages.extend(tool_results)

            for tr in tool_results:
                yield {"kind": "tool_result", "content": tr["content"][:200]}

            continue  # feed results back to model

        # No tool calls (or last round) — emit the text as deltas
        content = str(msg.get("content") or "")
        chunk_size = 8
        for i in range(0, max(1, len(content)), chunk_size):
            delta = content[i : i + chunk_size]
            if delta:
                yield {"kind": "delta", "delta": delta}
        break  # done

    done_reason = str(
        final_payload.get("done_reason")
        or ("stop" if final_payload.get("done") else "unknown")
    )
    yield {
        "kind": "meta",
        "done_reason": done_reason,
        "truncated": done_reason in {"length", "max_tokens"} or bool(final_payload.get("truncated")),
        "eval_count": int(final_payload.get("eval_count") or 0),
        "prompt_eval_count": int(final_payload.get("prompt_eval_count") or 0),
        "num_predict": int(num_predict_override) if num_predict_override is not None else None,
    }
    record_inference_event(
        source="chat_service", provider="ollama", model=model,
        requested_device=runtime.device, effective_device=runtime.device,
        latency_ms=(perf_counter() - started) * 1000,
        success=True, fallback_used=False,
    )


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
    output_text = str(payload.get("output_text") or "").strip() if isinstance(payload, dict) else ""
    if output_text:
        return output_text
    outputs = list(payload.get("output") or []) if isinstance(payload, dict) else []
    if outputs:
        parts: list[str] = []
        for item in outputs:
            if not isinstance(item, dict):
                continue
            for content_item in list(item.get("content") or []):
                if not isinstance(content_item, dict):
                    continue
                text = str(
                    content_item.get("text")
                    or content_item.get("output_text")
                    or ""
                ).strip()
                if text:
                    parts.append(text)
        if parts:
            return "".join(parts).strip()
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


def _stream_anthropic_events(
    messages: list[dict[str, str]],
    *,
    response_mode: str = _DEFAULT_RESPONSE_MODE,
    model: str,
) -> Iterator[dict[str, object]]:
    """Stream tokens from Anthropic SSE endpoint."""
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
    started = perf_counter()
    resp = None
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                **(
                    {
                        "Authorization": f"Bearer {credential}",
                        "anthropic-beta": "oauth-2025-04-20",
                    }
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
                "stream": True,
            },
            timeout=timeout,
            stream=True,
        )
        resp.raise_for_status()
        _tokens_in = 0
        _tokens_out = 0
        for raw_line in resp.iter_lines(decode_unicode=True):
            if not raw_line or not raw_line.startswith("data:"):
                continue
            data_str = raw_line[5:].strip()
            if data_str == "[DONE]":
                break
            try:
                payload = json.loads(data_str)
            except Exception:
                continue
            event_type = str(payload.get("type") or "")
            if event_type == "message_start":
                _usage = (payload.get("message") or {}).get("usage") or {}
                _tokens_in = int(_usage.get("input_tokens") or 0)
            elif event_type == "content_block_delta":
                delta = str((payload.get("delta") or {}).get("text") or "")
                if delta:
                    yield {"kind": "delta", "delta": delta}
            elif event_type == "message_delta":
                _usage = payload.get("usage") or {}
                _tokens_out = int(_usage.get("output_tokens") or 0)
            elif event_type == "message_stop":
                break
        yield {"kind": "meta", "done_reason": "stop", "truncated": False, "tokens_in": _tokens_in, "tokens_out": _tokens_out}
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
    finally:
        try:
            resp.close()
        except Exception:
            pass


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
                    {
                        "Authorization": f"Bearer {credential}",
                        "anthropic-beta": "oauth-2025-04-20",
                    }
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
    auth_method = str(auth.get("method") or "none")
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
        is_oauth_transport = _is_openai_oauth_transport(endpoint, auth_method)
        system_prompt = "\n\n".join(
            str(item.get("content") or "")
            for item in messages
            if str(item.get("role") or "").strip().lower() == "system"
        ).strip()
        if is_oauth_transport:
            request_url = f"{endpoint.rstrip('/')}/v1/responses"
            request_payload = {
                "model": model,
                "input": [
                    {
                        "role": str(item.get("role") or "user").strip().lower(),
                        "content": [
                            {
                                "type": "input_text",
                                "text": str(item.get("content") or ""),
                            }
                        ],
                    }
                    for item in messages
                    if str(item.get("role") or "").strip().lower() != "system"
                ],
                "temperature": float(profile.get("temperature") or 0.15),
                "max_output_tokens": _chat_max_tokens(response_mode),
            }
            if system_prompt:
                request_payload["instructions"] = system_prompt
        else:
            request_url = f"{endpoint.rstrip('/')}/chat/completions"
            request_payload = {
                "model": model,
                "messages": messages,
                "temperature": float(profile.get("temperature") or 0.15),
                "max_tokens": _chat_max_tokens(response_mode),
                "stream": False,
            }
        response = requests.post(
            request_url,
            headers=headers,
            json=request_payload,
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
    effective_model = str(selected_target.get("model") or "").strip()
    if not effective_model:
        import os as _os
        effective_model = _os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001").strip()
    effective_session, skill_name, context, history_messages, retrieval = _prepare_chat_context(
        message,
        session_id=session_id,
        cliente=cliente,
        response_mode=mode,
    )

    # Recalcula modelo com skill conhecido — chat livre usa modelo mais capaz
    if selected_target.get("backend") == "ollama" and not selected_model:
        effective_model = resolve_ollama_model_for_mode(mode, skill_name=skill_name)

    runtime = _build_selected_runtime(
        {
            **selected_target,
            "model": effective_model,
        }
    )
    has_session_history = bool(history_messages)
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
        "tokens_in": 0,
        "tokens_out": 0,
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
    elif not _llm_chat_enabled(selected_target):
        content = _strip_repeated_greeting(
            _fallback_response(message, skill_name),
            has_session_history=has_session_history,
        )
        for delta in _chunk_text(content, chunk_size=int(profile.get("chunk_size") or _STREAM_CHUNK_SIZE)):
            yield {"event": "delta", "delta": delta, "skill": skill_name}
    elif not content:
        context, _ = _apply_context_budget(context, model_name=effective_model, response_mode=mode)
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
                        num_predict_override = None  # sem limite artificial
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
                            content = _strip_repeated_greeting(
                                f"{content}{''.join(continuation_parts)}".strip(),
                                has_session_history=has_session_history,
                            )
            elif selected_target["backend"] == "anthropic":
                parts: list[str] = []
                for item in _stream_anthropic_events(messages, response_mode=mode, model=effective_model):
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
            content = _strip_repeated_greeting(
                (
                    f"Falha ao consultar a LLM: {exc}. "
                    f"Skill selecionada: `{skill_name}`."
                ),
                has_session_history=has_session_history,
            )
            for delta in _chunk_text(content, chunk_size=int(profile.get("chunk_size") or _STREAM_CHUNK_SIZE)):
                yield {"event": "delta", "delta": delta, "skill": skill_name}

    _handle_memory_persistence(message, content, effective_session)

    # Detecta primeiro turno: sem histórico E sem título ainda gerado
    existing_titulo = persistence.get_chat_session_titulo(effective_session)
    is_first_turn = not has_session_history and not existing_titulo and persistence.count_chat_messages(effective_session) == 0

    _persist_chat_exchange(
        session_id=effective_session,
        message=message,
        skill_name=skill_name,
        content=content,
        tokens_in=int(completion_meta.get("tokens_in") or completion_meta.get("prompt_eval_count") or 0),
        tokens_out=int(completion_meta.get("tokens_out") or completion_meta.get("eval_count") or 0),
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

    # Gera título de sessão no primeiro turno (assíncrono após resposta)
    session_title: str = ""
    if is_first_turn and content:
        session_title = _generate_session_title(message, content, selected_target)
        if session_title:
            persistence.update_chat_session_titulo(effective_session, session_title)
            _logger.debug("Título de sessão gerado: %s", session_title)

    yield {
        "event": "final",
        "data": {
            "type": "message",
            "content": content,
            "skill": skill_name,
            "session_id": effective_session,
            "session_title": session_title,
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
