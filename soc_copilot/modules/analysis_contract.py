from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / ".agents"
    / "soc-copilot"
    / "schemas"
    / "analysis_response.json"
)

_OFFICIAL_KEYS = (
    "summary",
    "verdict",
    "confidence",
    "iocs",
    "ttps",
    "risk_reasons",
    "recommended_actions",
    "sources",
)

_VALID_VERDICTS = {"benigno", "suspeito", "malicioso", "inconclusivo"}
_VALID_IOC_TYPES = {
    "ip",
    "domain",
    "url",
    "hash",
    "email",
    "file",
    "process",
    "registry",
    "other",
}

_CLASSIFICATION_TO_VERDICT = {
    "true positive": "malicioso",
    "tp": "malicioso",
    "benign true positive": "suspeito",
    "btp": "suspeito",
    "false positive": "benigno",
    "fp": "benigno",
    "true negative": "benigno",
    "tn": "benigno",
    "log transmission failure": "inconclusivo",
    "ltf": "inconclusivo",
    "indefinido": "inconclusivo",
}

_IOC_CATEGORY_MAP = {
    "ips_externos": ("ip", "IOC extraido do payload"),
    "ips_internos": ("ip", "IOC extraido do payload"),
    "urls": ("url", "URL identificada no payload"),
    "dominios": ("domain", "Dominio identificado no payload"),
    "hashes": ("hash", "Hash identificado no payload"),
}


def _load_schema() -> dict[str, Any]:
    try:
        return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.upper() in {"N/A", "NONE", "NULL"} else text


def _clamp_confidence(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    if not isinstance(value, (int, float)):
        return 0.0
    return max(0.0, min(1.0, float(value)))


def _map_verdict(analysis: dict[str, Any]) -> str:
    classificacao = _clean_text(
        (analysis.get("classificacao_sugerida") or {}).get("tipo", "")
    ).lower()
    return _CLASSIFICATION_TO_VERDICT.get(classificacao, "inconclusivo")


def _build_summary(analysis: dict[str, Any], fields: dict[str, Any]) -> str:
    factual = analysis.get("resumo_factual") or {}
    summary = _clean_text(factual.get("o_que"))
    if summary:
        return summary

    pieces = [
        _clean_text(fields.get("Assunto")),
        _clean_text(fields.get("LogSource")),
        _clean_text(fields.get("Destino")),
    ]
    pieces = [piece for piece in pieces if piece]
    if pieces:
        return " | ".join(pieces)
    return "Analise concluida com evidencias limitadas."


def _append_ioc(
    items: list[dict[str, str]],
    seen: set[tuple[str, str]],
    ioc_type: str,
    value: Any,
    context: str,
) -> None:
    normalized_value = _clean_text(value)
    if not normalized_value:
        return
    key = (ioc_type, normalized_value.lower())
    if key in seen:
        return
    seen.add(key)
    items.append(
        {
            "type": ioc_type if ioc_type in _VALID_IOC_TYPES else "other",
            "value": normalized_value,
            "context": _clean_text(context) or "IOC identificado na analise",
        }
    )


def _build_iocs(fields: dict[str, Any], ti_results: dict[str, str]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    iocs = fields.get("IOCs") or {}

    for key, (ioc_type, default_context) in _IOC_CATEGORY_MAP.items():
        for value in iocs.get(key, []) or []:
            context = ti_results.get(value) or default_context
            _append_ioc(items, seen, ioc_type, value, context)

    for artifact in (fields.get("Resumo_Scan"), fields.get("Caminho")):
        artifact_text = _clean_text(artifact)
        if artifact_text and len(artifact_text) <= 250:
            _append_ioc(items, seen, "other", artifact_text, "Artefato tecnico relevante")

    _append_ioc(
        items,
        seen,
        "file",
        fields.get("Arquivo"),
        "Arquivo observado no payload",
    )
    _append_ioc(
        items,
        seen,
        "hash",
        fields.get("Hash_Observado"),
        "Hash observado no payload",
    )
    _append_ioc(items, seen, "email", fields.get("Email_Remetente"), "E-mail remetente observado")
    _append_ioc(items, seen, "email", fields.get("Email_Destinatario"), "E-mail destinatario observado")
    _append_ioc(items, seen, "domain", fields.get("DNS_Consulta"), "Dominio DNS observado")
    _append_ioc(items, seen, "domain", fields.get("HTTP_Host"), "HTTP host observado")
    _append_ioc(items, seen, "domain", fields.get("TLS_SNI"), "SNI observado")
    _append_ioc(items, seen, "url", fields.get("URL_Completa"), "URL observada no payload")

    return items


def _build_ttps(analysis: dict[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    mitre = analysis.get("mitre_candidato") or {}
    technique = _clean_text(mitre.get("tecnica"))
    if technique:
        seen.add(technique)
        items.append(
            {
                "id": technique,
                "name": _clean_text(mitre.get("nome")) or technique,
                "reason": _clean_text(mitre.get("justificativa"))
                or "Tecnica inferida a partir do comportamento observado.",
            }
        )

    for context in analysis.get("contextos_investigativos") or []:
        for technique_item in context.get("mitre_techniques") or []:
            technique_id = _clean_text(technique_item.get("id"))
            if not technique_id or technique_id in seen:
                continue
            seen.add(technique_id)
            items.append(
                {
                    "id": technique_id,
                    "name": technique_id,
                    "reason": _clean_text(technique_item.get("reason"))
                    or _clean_text(context.get("summary"))
                    or "Tecnica inferida a partir do contexto investigativo.",
                }
            )

    return items


def _build_risk_reasons(analysis: dict[str, Any], ti_results: dict[str, str]) -> list[str]:
    reasons: list[str] = []
    top_hypothesis = (analysis.get("hipoteses") or [{}])[0]
    for candidate in (
        _clean_text(top_hypothesis.get("justificativa")),
        _clean_text(top_hypothesis.get("racional")),
        _clean_text((analysis.get("classificacao_sugerida") or {}).get("racional")),
    ):
        if candidate and candidate not in reasons:
            reasons.append(candidate)

    for context in (analysis.get("contextos_investigativos") or [])[:3]:
        candidate = _clean_text(context.get("summary")) or _clean_text(context.get("rationale"))
        if candidate and candidate not in reasons:
            reasons.append(candidate)

    for ioc, result in (ti_results or {}).items():
        result_text = _clean_text(result)
        if result_text:
            reasons.append(f"{ioc}: {result_text[:220]}")
        if len(reasons) >= 4:
            break

    if not reasons:
        lacuna = next(iter(analysis.get("lacunas") or []), "")
        fallback = _clean_text(lacuna) or "Evidencias insuficientes para detalhar o risco."
        reasons.append(fallback)

    return reasons[:5]


def _build_sources(analysis: dict[str, Any], ti_results: dict[str, str]) -> list[str]:
    sources = ["parser_engine", "classification_helper", "semi_llm_adapter"]
    if ti_results:
        sources.append("ti_adapter")
    if (analysis.get("mitre_candidato") or {}).get("tecnica"):
        sources.append("mitre_mapping")
    if analysis.get("contextos_investigativos"):
        sources.append("telemetry_context")
    if analysis.get("knowledge_matches"):
        sources.append("knowledge_base")
    if analysis.get("vantage_sources") or any(
        isinstance(match, dict) and str(match.get("module_id") or "").startswith(("feed", "watchlist", "recon", "hunting", "exposure", "users", "admin", "dashboard"))
        for match in (analysis.get("knowledge_matches") or [])
    ):
        sources.append("vantage_api")
    deduped: list[str] = []
    for source in sources:
        if source not in deduped:
            deduped.append(source)
    return deduped


def build_structured_analysis(
    analysis: dict[str, Any],
    fields: dict[str, Any] | None = None,
    ti_results: dict[str, str] | None = None,
) -> dict[str, Any]:
    fields = fields or {}
    ti_results = ti_results or {}
    structured = {
        "summary": _build_summary(analysis, fields),
        "verdict": _map_verdict(analysis),
        "confidence": _clamp_confidence(
            (analysis.get("classificacao_sugerida") or {}).get("confianca")
        ),
        "iocs": _build_iocs(fields, ti_results),
        "ttps": _build_ttps(analysis),
        "risk_reasons": _build_risk_reasons(analysis, ti_results),
        "recommended_actions": [
            _clean_text(item)
            for item in (analysis.get("proximos_passos") or [])
            if _clean_text(item)
        ],
        "sources": _build_sources(analysis, ti_results),
    }
    combined_actions: list[str] = []
    for context in (analysis.get("contextos_investigativos") or [])[:3]:
        for action in context.get("recommended_actions") or []:
            cleaned = _clean_text(action)
            if cleaned and cleaned not in combined_actions:
                combined_actions.append(cleaned)
    for action in structured["recommended_actions"]:
        cleaned = _clean_text(action)
        if cleaned and cleaned not in combined_actions:
            combined_actions.append(cleaned)
    structured["recommended_actions"] = combined_actions[:8]
    if not structured["recommended_actions"]:
        structured["recommended_actions"] = [
            "Revisar manualmente as evidencias e complementar os campos ausentes.",
        ]
    return structured


def validate_structured_analysis(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["Structured analysis must be an object."]

    extra_keys = set(data.keys()) - set(_OFFICIAL_KEYS)
    missing_keys = set(_OFFICIAL_KEYS) - set(data.keys())
    if extra_keys:
        errors.append(f"Unexpected keys: {sorted(extra_keys)}")
    if missing_keys:
        errors.append(f"Missing keys: {sorted(missing_keys)}")

    if not _clean_text(data.get("summary")):
        errors.append("summary must be a non-empty string.")

    if data.get("verdict") not in _VALID_VERDICTS:
        errors.append("verdict must be one of benigno, suspeito, malicioso, inconclusivo.")

    confidence = data.get("confidence")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        errors.append("confidence must be numeric.")
    elif not 0 <= float(confidence) <= 1:
        errors.append("confidence must be between 0 and 1.")

    if not isinstance(data.get("iocs"), list):
        errors.append("iocs must be a list.")
    else:
        for index, item in enumerate(data["iocs"]):
            if not isinstance(item, dict):
                errors.append(f"iocs[{index}] must be an object.")
                continue
            if item.get("type") not in _VALID_IOC_TYPES:
                errors.append(f"iocs[{index}].type is invalid.")
            if not _clean_text(item.get("value")):
                errors.append(f"iocs[{index}].value must be non-empty.")
            if not isinstance(item.get("context"), str):
                errors.append(f"iocs[{index}].context must be a string.")

    if not isinstance(data.get("ttps"), list):
        errors.append("ttps must be a list.")
    else:
        for index, item in enumerate(data["ttps"]):
            if not isinstance(item, dict):
                errors.append(f"ttps[{index}] must be an object.")
                continue
            if not _clean_text(item.get("id")):
                errors.append(f"ttps[{index}].id must be non-empty.")
            if not _clean_text(item.get("name")):
                errors.append(f"ttps[{index}].name must be non-empty.")
            if not _clean_text(item.get("reason")):
                errors.append(f"ttps[{index}].reason must be non-empty.")

    for key in ("risk_reasons", "recommended_actions", "sources"):
        if not isinstance(data.get(key), list):
            errors.append(f"{key} must be a list.")
            continue
        for index, item in enumerate(data[key]):
            if not _clean_text(item):
                errors.append(f"{key}[{index}] must be a non-empty string.")

    return errors


def structured_analysis_schema() -> dict[str, Any]:
    return _load_schema()
