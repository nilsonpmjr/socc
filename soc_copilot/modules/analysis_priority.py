from __future__ import annotations

from typing import Any


_CLASSIFICATION_BASE = {
    "true positive": 68,
    "tp": 68,
    "benign true positive": 42,
    "btp": 42,
    "false positive": 20,
    "fp": 20,
    "true negative": 12,
    "tn": 12,
    "log transmission failure": 35,
    "ltf": 35,
    "indefinido": 28,
}

_SEVERITY_POINTS = {"critical": 18, "high": 14, "medium": 8, "low": 3}
_FAMILY_LABELS = {
    "email_auth": "Email e Identidade",
    "dns_http_tls": "Rede e Web",
    "process_endpoint": "Endpoint e Execução",
    "cloud_identity": "Cloud e Identidade",
    "network_flow_nat": "Fluxo de Rede",
    "kubernetes_container": "Kubernetes e Containers",
    "generic": "Geral",
}


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.upper() in {"", "N/A", "NONE", "NULL"} else text


def _classification_score(analysis: dict[str, Any]) -> int:
    suggestion = analysis.get("classificacao_sugerida") or {}
    label = _clean_text(suggestion.get("tipo")).lower()
    return _CLASSIFICATION_BASE.get(label, 25)


def _contexts(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    contexts = analysis.get("contextos_investigativos") or []
    return contexts if isinstance(contexts, list) else []


def _top_family(analysis: dict[str, Any], fields: dict[str, Any]) -> str:
    contexts = _contexts(analysis)
    if contexts:
        family = _clean_text(contexts[0].get("family"))
        if family:
            return family
    if _clean_text(fields.get("Email_Remetente")) or _clean_text(fields.get("Email_Assunto")):
        return "email_auth"
    if _clean_text(fields.get("Processo")) or _clean_text(fields.get("Registro")):
        return "process_endpoint"
    if _clean_text(fields.get("Cloud_Conta_ID")) or _clean_text(fields.get("Cloud_Recurso")):
        return "cloud_identity"
    if _clean_text(fields.get("Kubernetes_Pod")) or _clean_text(fields.get("Container_ID")):
        return "kubernetes_container"
    if _clean_text(fields.get("DNS_Consulta")) or _clean_text(fields.get("URL_Completa")):
        return "dns_http_tls"
    if _clean_text(fields.get("Bytes_Entrada")) or _clean_text(fields.get("Bytes_Saida")):
        return "network_flow_nat"
    return "generic"


def build_analysis_priority(
    *,
    analysis: dict[str, Any],
    fields: dict[str, Any] | None = None,
    ti_results: dict[str, str] | None = None,
) -> dict[str, Any]:
    fields = fields or {}
    ti_results = ti_results or {}
    contexts = _contexts(analysis)
    score = _classification_score(analysis)

    confidence = (analysis.get("classificacao_sugerida") or {}).get("confianca")
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
        score += min(10, max(0, round(float(confidence) * 10)))

    reasons: list[str] = []
    for context in contexts[:3]:
        severity = _clean_text(context.get("severity")).lower() or "low"
        score += _SEVERITY_POINTS.get(severity, 2)
        title = _clean_text(context.get("title"))
        summary = _clean_text(context.get("summary")) or _clean_text(context.get("rationale"))
        if title:
            reason = title if not summary else f"{title}: {summary}"
            if reason not in reasons:
                reasons.append(reason)

    ti_text = " ".join(_clean_text(value).lower() for value in ti_results.values())
    if any(token in ti_text for token in ("malicious", "malicioso", "phishing", "botnet", "ransomware")):
        score += 8
        reasons.append("Threat Intelligence com indicativo malicioso para artefatos consultados.")
    elif any(token in ti_text for token in ("suspicious", "suspeito", "high risk", "alto risco")):
        score += 4
        reasons.append("Threat Intelligence com indicativo suspeito para artefatos consultados.")

    score = max(0, min(100, score))
    if score >= 85:
        level = "critica"
        rank = 1
    elif score >= 65:
        level = "alta"
        rank = 2
    elif score >= 40:
        level = "media"
        rank = 3
    else:
        level = "baixa"
        rank = 4

    if not reasons:
        fallback_reason = _clean_text((analysis.get("classificacao_sugerida") or {}).get("racional"))
        if fallback_reason:
            reasons.append(fallback_reason)
        else:
            reasons.append("Priorização derivada da classificação sugerida e das evidências estruturadas disponíveis.")

    family = _top_family(analysis, fields)
    top_context = contexts[0] if contexts else {}
    rationale = (
        _clean_text(top_context.get("summary"))
        or _clean_text(top_context.get("rationale"))
        or reasons[0]
    )

    return {
        "score": score,
        "level": level,
        "rank": rank,
        "primary_family": family,
        "primary_label": _FAMILY_LABELS.get(family, "Geral"),
        "rationale": rationale,
        "reasons": reasons[:5],
    }
