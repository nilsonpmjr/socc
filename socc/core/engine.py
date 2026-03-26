from __future__ import annotations

from typing import Any

from soc_copilot.config import SOC_PORT
from soc_copilot.modules import draft_engine, parser_engine, rule_loader


def build_app():
    from soc_copilot.main import app

    return app


def serve(
    host: str = "127.0.0.1",
    port: int | None = None,
    reload: bool = False,
    log_level: str = "info",
) -> None:
    import uvicorn

    bind_port = port or SOC_PORT
    print(f"\n  SOCC runtime\n  Access: http://{host}:{bind_port}\n")
    uvicorn.run(
        "soc_copilot.main:app",
        host=host,
        port=bind_port,
        reload=reload,
        log_level=log_level,
    )


def parse_payload(payload_text: str, raw_fields: dict[str, Any] | None = None) -> dict[str, Any]:
    return parser_engine.parse(raw_fields or {}, payload_text)


def analyze_payload(
    payload_text: str,
    raw_fields: dict[str, Any] | None = None,
    cliente: str = "",
    regra: str = "",
    classificacao: str = "TP",
    ti_results: dict[str, str] | None = None,
    analysis: dict[str, Any] | None = None,
    include_draft: bool = True,
) -> dict[str, Any]:
    fields = parse_payload(payload_text, raw_fields)
    regra_contexto = regra or fields.get("Assunto", "")
    pack = rule_loader.load(regra_contexto, cliente)

    result: dict[str, Any] = {
        "fields": fields,
        "rule_pack": {
            "modelo_aderente": pack.modelo_aderente,
            "modelo_nome": pack.modelo_nome,
            "is_icatu": pack.is_icatu,
        },
    }

    if include_draft:
        draft_text, template_used = draft_engine.generate(
            classificacao,
            fields,
            ti_results or {},
            pack,
            analysis or {},
        )
        result["draft"] = draft_text
        result["template_used"] = template_used

    return result
