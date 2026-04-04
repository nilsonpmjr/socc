from __future__ import annotations

from typing import Any

from soc_copilot.modules import persistence


LEGACY_MODULE = "soc_copilot.modules.persistence"


def init_db() -> None:
    persistence.init_db()


def hash_input(raw: str) -> str:
    return persistence.hash_input(raw)


def save_run(
    ofensa_id: str,
    cliente: str,
    regra: str,
    raw_input: str,
    classificacao: str,
    template_usado: str,
    status: str = "ok",
) -> int:
    return persistence.save_run(
        ofensa_id=ofensa_id,
        cliente=cliente,
        regra=regra,
        raw_input=raw_input,
        classificacao=classificacao,
        template_usado=template_usado,
        status=status,
    )


def save_analysis(run_id: int, analysis: dict[str, Any], structured_analysis: dict[str, Any] | None = None) -> None:
    persistence.save_analysis(run_id, analysis, structured_analysis=structured_analysis)


def save_intel(run_id: int, ioc: str, tipo: str, ferramenta: str, resultado: str) -> None:
    persistence.save_intel(
        run_id=run_id,
        ioc=ioc,
        tipo=tipo,
        ferramenta=ferramenta,
        resultado=resultado,
    )


def save_output(run_id: int, tipo_saida: str, conteudo: str, salvo_em: str = "") -> None:
    persistence.save_output(run_id, tipo_saida, conteudo, salvo_em=salvo_em)


def get_run(run_id: int) -> dict[str, Any] | None:
    return persistence.get_run(run_id)


def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    return persistence.list_runs(limit=limit)


def ensure_chat_session(session_id: str, cliente: str = "", titulo: str = "") -> None:
    persistence.ensure_chat_session(session_id=session_id, cliente=cliente, titulo=titulo)


def save_chat_message(
    session_id: str,
    role: str,
    content: str,
    skill: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    persistence.save_chat_message(
        session_id=session_id,
        role=role,
        content=content,
        skill=skill,
        metadata=metadata,
    )


def list_chat_messages(session_id: str, limit: int = 8) -> list[dict[str, Any]]:
    return persistence.list_chat_messages(session_id=session_id, limit=limit)


def list_chat_sessions(limit: int = 50) -> list[dict[str, Any]]:
    return persistence.list_chat_sessions(limit=limit)


def get_chat_session(session_id: str) -> dict[str, Any] | None:
    return persistence.get_chat_session(session_id)


def get_chat_session_usage(session_id: str) -> dict[str, Any]:
    return persistence.get_session_usage(session_id)


def get_chat_session_summary(session_id: str, limit: int = 20) -> dict[str, Any] | None:
    session = get_chat_session(session_id)
    if session is None:
        return None
    return {
        **session,
        "usage": get_chat_session_usage(session_id),
        "messages": list_chat_messages(session_id, limit=limit),
    }


def save_feedback(
    feedback_type: str,
    run_id: int | None = None,
    session_id: str = "",
    payload_hash: str = "",
    verdict_correction: str = "",
    comments: str = "",
    source: str = "ui",
) -> int:
    return persistence.save_feedback(
        feedback_type=feedback_type,
        run_id=run_id,
        session_id=session_id,
        payload_hash=payload_hash,
        verdict_correction=verdict_correction,
        comments=comments,
        source=source,
    )
