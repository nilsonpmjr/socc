from __future__ import annotations

import logging
from typing import List

import requests

from soc_copilot import config as cfg
from soc_copilot.modules import persistence
from soc_copilot.modules.soc_copilot_loader import build_prompt_context, choose_skill

_logger = logging.getLogger(__name__)
_MAX_HISTORY_MESSAGES = 8


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


def _call_ollama(messages: list[dict[str, str]]) -> str:
    base_url = getattr(cfg, "OLLAMA_URL", "http://localhost:11434").rstrip("/")
    model = getattr(cfg, "OLLAMA_MODEL", "qwen2.5:3b")
    timeout = float(getattr(cfg, "LLM_TIMEOUT", 60))

    body = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.2},
    }
    resp = requests.post(f"{base_url}/api/chat", json=body, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return (data.get("message", {}) or {}).get("content", "").strip()


def generate_chat_reply(
    message: str,
    session_id: str = "",
    cliente: str = "",
) -> dict[str, str]:
    effective_session = session_id or "default"
    skill_name = select_skill(message)
    persistence.ensure_chat_session(
        session_id=effective_session,
        cliente=cliente,
        titulo=message.strip()[:80],
    )
    session_context = _format_history(effective_session)
    context = build_prompt_context(
        user_input=message,
        artifact_type=_detect_artifact_type(message),
        session_context=session_context,
        selected_skill=skill_name,
    )

    if not getattr(cfg, "LLM_ENABLED", False):
        content = _fallback_response(message, skill_name)
    else:
        history_messages = [
            {"role": item.get("role", "user"), "content": item.get("content", "")}
            for item in persistence.list_chat_messages(
                effective_session, limit=_MAX_HISTORY_MESSAGES
            )
        ]
        messages = [{"role": "system", "content": _build_system_prompt(context)}]
        messages.extend(history_messages)
        messages.append(
            {"role": "user", "content": _build_user_prompt(message, cliente, context)}
        )
        try:
            if getattr(cfg, "LLM_PROVIDER", "ollama").lower() != "ollama":
                content = _fallback_response(message, skill_name)
            else:
                content = _call_ollama(messages)
        except Exception as exc:
            _logger.exception("Falha ao consultar a LLM local no chat do SOC Copilot.")
            content = (
                f"Falha ao consultar a LLM local: {exc}. "
                f"Skill selecionada: `{skill_name}`."
            )

    persistence.save_chat_message(
        session_id=effective_session,
        role="user",
        content=message,
        skill=skill_name,
        metadata={"type": "message"},
    )
    persistence.save_chat_message(
        session_id=effective_session,
        role="assistant",
        content=content,
        skill=skill_name,
        metadata={"type": "message"},
    )

    return {
        "type": "message",
        "content": content,
        "skill": skill_name,
        "session_id": effective_session,
    }
