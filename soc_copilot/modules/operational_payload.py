from __future__ import annotations

from typing import Any


_DISPOSITION_LABELS = {
    "alerta": "Abertura de alerta",
    "encerramento_administrativo": "Encerramento administrativo",
    "false_positive": "Correção de detecção",
    "true_negative": "Encerramento benigno",
    "falha_de_log": "Tratativa operacional de telemetria",
    "analise": "Análise consultiva",
}

_TEMPLATE_KINDS = {
    "TP": "alerta_operacional",
    "BTP": "encerramento_administrativo",
    "FP": "ajuste_de_deteccao",
    "TN": "encerramento_benigno",
    "LTF": "tratativa_de_telemetria",
}


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _short_list(items: list[Any], limit: int = 5) -> list[str]:
    values: list[str] = []
    for item in items[:limit]:
        text = _clean_text(item)
        if text:
            values.append(text)
    return values


def build_operational_payload(
    *,
    metadata: dict[str, Any] | None = None,
    fields: dict[str, Any] | None = None,
    analysis_structured: dict[str, Any] | None = None,
    analysis_priority: dict[str, Any] | None = None,
    analysis_trace: dict[str, Any] | None = None,
    analysis_legacy: dict[str, Any] | None = None,
    draft: str = "",
) -> dict[str, Any]:
    meta = dict(metadata or {})
    fields = fields or {}
    structured = analysis_structured or {}
    priority = analysis_priority or {}
    trace = analysis_trace or {}
    legacy = analysis_legacy or {}

    iocs = list(structured.get("iocs") or [])
    recommended = list(structured.get("recommended_actions") or [])
    risk_reasons = list(structured.get("risk_reasons") or [])
    sources = list(structured.get("sources") or [])
    vantage_sources = list(legacy.get("vantage_sources") or [])
    vantage_modules = list(legacy.get("vantage_modules") or [])

    observed = list(trace.get("observed_facts") or [])
    evidence = [
        {
            "label": _clean_text(item.get("label") or item.get("category") or "Fato"),
            "value": _clean_text(item.get("value")),
            "source": _clean_text(item.get("source")),
        }
        for item in observed[:8]
        if isinstance(item, dict) and _clean_text(item.get("value"))
    ]

    classificacao = _clean_text(meta.get("classificacao")) or _clean_text((legacy.get("classificacao_sugerida") or {}).get("tipo"))
    title = _clean_text(fields.get("Assunto")) or _clean_text(structured.get("summary")) or "Caso SOC"
    disposition_map = {
        "TP": "alerta",
        "BTP": "encerramento_administrativo",
        "FP": "false_positive",
        "TN": "true_negative",
        "LTF": "falha_de_log",
    }
    normalized_classification = (classificacao or "").upper()
    disposition = disposition_map.get(normalized_classification, "analise")

    return {
        "title": title,
        "classification": classificacao or "-",
        "disposition": disposition,
        "disposition_label": _DISPOSITION_LABELS.get(disposition, "Análise consultiva"),
        "template_kind": _TEMPLATE_KINDS.get(normalized_classification, "analise_consultiva"),
        "summary": _clean_text(structured.get("summary")),
        "verdict": _clean_text(structured.get("verdict")) or "inconclusivo",
        "priority": {
            "level": _clean_text(priority.get("level")),
            "score": priority.get("score"),
            "rank": priority.get("rank"),
            "family": _clean_text(priority.get("primary_label") or priority.get("primary_family")),
        },
        "recommended_actions": _short_list(recommended, limit=6),
        "risk_reasons": _short_list(risk_reasons, limit=5),
        "iocs": iocs[:10],
        "evidence": evidence,
        "sources": sources,
        "vantage": {
            "modules": vantage_modules,
            "sources": vantage_sources[:6],
        },
        "draft": _clean_text(draft),
    }
