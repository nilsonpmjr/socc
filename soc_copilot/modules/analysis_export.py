from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def build_export_bundle(
    *,
    metadata: dict[str, Any] | None = None,
    fields: dict[str, Any] | None = None,
    ti_results: dict[str, str] | None = None,
    analysis_structured: dict[str, Any] | None = None,
    analysis_priority: dict[str, Any] | None = None,
    analysis_trace: dict[str, Any] | None = None,
    operational_payload: dict[str, Any] | None = None,
    draft: str = "",
    analysis_legacy: dict[str, Any] | None = None,
    **legacy_kwargs: Any,
) -> dict[str, Any]:
    meta = dict(metadata or {})
    meta.setdefault("generated_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    legacy_operational_payload = legacy_kwargs.get("soar" + "_payload") or {}
    normalized_operational_payload = operational_payload or legacy_operational_payload or {}
    return {
        "metadata": meta,
        "fields": fields or {},
        "ti_results": ti_results or {},
        "analysis_structured": analysis_structured or {},
        "analysis_priority": analysis_priority or {},
        "analysis_trace": analysis_trace or {},
        "operational_payload": normalized_operational_payload,
        "analysis_legacy": analysis_legacy or {},
        "draft": draft or "",
    }


def render_export_json(bundle: dict[str, Any]) -> str:
    return json.dumps(bundle, indent=2, ensure_ascii=False)


def render_export_markdown(bundle: dict[str, Any]) -> str:
    metadata = bundle.get("metadata") or {}
    structured = bundle.get("analysis_structured") or {}
    priority = bundle.get("analysis_priority") or {}
    trace = bundle.get("analysis_trace") or {}
    operational_payload = bundle.get("operational_payload") or bundle.get("soar" + "_payload") or {}
    draft = _clean_text(bundle.get("draft"))
    legacy = bundle.get("analysis_legacy") or {}
    contexts = legacy.get("contextos_investigativos") or []

    lines = [
        "# SOC Copilot Analysis Export",
        "",
        "## Metadata",
        f"- generated_at: {_clean_text(metadata.get('generated_at'))}",
        f"- run_id: {_clean_text(metadata.get('run_id')) or '-'}",
        f"- session_id: {_clean_text(metadata.get('session_id')) or '-'}",
        f"- cliente: {_clean_text(metadata.get('cliente')) or '-'}",
        f"- regra: {_clean_text(metadata.get('regra')) or '-'}",
        f"- classificacao: {_clean_text(metadata.get('classificacao')) or '-'}",
        "",
        "## Summary",
        _clean_text(structured.get("summary")) or "-",
        "",
        "## Verdict",
        f"- verdict: {_clean_text(structured.get('verdict')) or '-'}",
        f"- confidence: {structured.get('confidence', 0)}",
        "",
        "## Priority",
        f"- level: {_clean_text(priority.get('level')) or '-'}",
        f"- score: {_clean_text(priority.get('score')) or '-'}",
        f"- rank: {_clean_text(priority.get('rank')) or '-'}",
        f"- family: {_clean_text(priority.get('primary_label')) or _clean_text(priority.get('primary_family')) or '-'}",
        f"- rationale: {_clean_text(priority.get('rationale')) or '-'}",
        "",
        "## Recommended Actions",
    ]

    for item in structured.get("recommended_actions") or []:
        lines.append(f"- {_clean_text(item)}")
    if not (structured.get("recommended_actions") or []):
        lines.append("-")

    lines.extend(["", "## Risk Reasons"])
    for item in structured.get("risk_reasons") or []:
        lines.append(f"- {_clean_text(item)}")
    if not (structured.get("risk_reasons") or []):
        lines.append("-")

    lines.extend(["", "## TTPs"])
    for item in structured.get("ttps") or []:
        lines.append(
            f"- {_clean_text(item.get('id')) or _clean_text(item.get('name'))}: {_clean_text(item.get('reason')) or _clean_text(item.get('name'))}"
        )
    if not (structured.get("ttps") or []):
        lines.append("-")

    lines.extend(["", "## Observed Facts"])
    for item in trace.get("observed_facts") or []:
        lines.append(
            f"- [{_clean_text(item.get('category'))}] {_clean_text(item.get('label'))}: {_clean_text(item.get('value'))} ({_clean_text(item.get('source'))})"
        )
    if not (trace.get("observed_facts") or []):
        lines.append("-")

    lines.extend(["", "## Inferences"])
    for item in trace.get("inferences") or []:
        confidence = item.get("confidence")
        suffix = f" [{confidence:.2f}]" if isinstance(confidence, (int, float)) else ""
        rationale = _clean_text(item.get("rationale"))
        line = f"- {_clean_text(item.get('statement'))}{suffix}"
        if rationale:
            line += f" — {rationale}"
        lines.append(line)
    if not (trace.get("inferences") or []):
        lines.append("-")

    lines.extend(["", "## Investigative Contexts"])
    for item in contexts:
        title = _clean_text(item.get("title")) or "Contexto"
        summary = _clean_text(item.get("summary")) or _clean_text(item.get("rationale"))
        confidence = item.get("confidence")
        suffix = f" [{confidence:.2f}]" if isinstance(confidence, (int, float)) else ""
        lines.append(f"- {title}{suffix}: {summary or '-'}")
    if not contexts:
        lines.append("-")

    lines.extend(["", "## Limitations"])
    for item in trace.get("limitations") or []:
        lines.append(f"- {_clean_text(item)}")
    if not (trace.get("limitations") or []):
        lines.append("-")

    if operational_payload:
        operational_priority = operational_payload.get("priority") or {}
        lines.extend(
            [
                "",
                "## Payload Operacional",
                f"- title: {_clean_text(operational_payload.get('title')) or '-'}",
                f"- classification: {_clean_text(operational_payload.get('classification')) or '-'}",
                f"- disposition: {_clean_text(operational_payload.get('disposition')) or '-'}",
                f"- verdict: {_clean_text(operational_payload.get('verdict')) or '-'}",
                f"- priority: {_clean_text(operational_priority.get('level')) or '-'}",
            ]
        )
        lines.append("- recommended_actions:")
        for item in operational_payload.get("recommended_actions") or []:
            lines.append(f"  - {_clean_text(item)}")
        if not (operational_payload.get("recommended_actions") or []):
            lines.append("  - -")

    if draft:
        lines.extend(["", "## Draft", "```text", draft, "```"])

    return "\n".join(lines).strip() + "\n"


def render_export_ticket(bundle: dict[str, Any]) -> str:
    metadata = bundle.get("metadata") or {}
    structured = bundle.get("analysis_structured") or {}
    priority = bundle.get("analysis_priority") or {}
    operational_payload = bundle.get("operational_payload") or bundle.get("soar" + "_payload") or {}
    draft = _clean_text(bundle.get("draft"))
    legacy = bundle.get("analysis_legacy") or {}
    contexts = legacy.get("contextos_investigativos") or []

    title = _clean_text(operational_payload.get("title")) or _clean_text(structured.get("summary")) or "Caso SOC"
    classification = _clean_text(operational_payload.get("classification")) or _clean_text(metadata.get("classificacao")) or "-"
    disposition = _clean_text(operational_payload.get("disposition_label")) or _clean_text(operational_payload.get("disposition")) or "-"
    verdict = _clean_text(operational_payload.get("verdict")) or _clean_text(structured.get("verdict")) or "-"
    priority_data = operational_payload.get("priority") or {}
    priority_level = _clean_text(priority_data.get("level")) or _clean_text(priority.get("level")) or "-"
    priority_score = _clean_text(priority_data.get("score")) or _clean_text(priority.get("score")) or "-"

    lines = [
        f"Título: {title}",
        f"Classificação: {classification}",
        f"Destino Operacional: {disposition}",
        f"Veredito: {verdict}",
        f"Prioridade: {priority_level}" + (f" (score {priority_score})" if priority_score not in {"", "-"} else ""),
        f"Cliente: {_clean_text(metadata.get('cliente')) or '-'}",
        f"Regra: {_clean_text(metadata.get('regra')) or '-'}",
        "",
        "Resumo:",
        _clean_text(structured.get("summary")) or "-",
        "",
        "Razões de risco:",
    ]

    for item in structured.get("risk_reasons") or []:
        lines.append(f"- {_clean_text(item)}")
    if not (structured.get("risk_reasons") or []):
        lines.append("-")

    lines.extend(["", "Ações recomendadas:"])
    for item in operational_payload.get("recommended_actions") or structured.get("recommended_actions") or []:
        lines.append(f"- {_clean_text(item)}")
    if not ((operational_payload.get("recommended_actions") or structured.get("recommended_actions") or [])):
        lines.append("-")

    lines.extend(["", "IOCs relevantes:"])
    for item in operational_payload.get("iocs") or structured.get("iocs") or []:
        if isinstance(item, dict):
            lines.append(
                f"- {_clean_text(item.get('type')) or 'ioc'}: {_clean_text(item.get('value')) or _clean_text(item.get('indicator')) or '-'}"
            )
        else:
            lines.append(f"- {_clean_text(item)}")
    if not ((operational_payload.get("iocs") or structured.get("iocs") or [])):
        lines.append("-")

    lines.extend(["", "Evidências observadas:"])
    for item in operational_payload.get("evidence") or []:
        if isinstance(item, dict):
            label = _clean_text(item.get("label")) or "Fato"
            value = _clean_text(item.get("value")) or "-"
            source = _clean_text(item.get("source"))
            suffix = f" ({source})" if source else ""
            lines.append(f"- {label}: {value}{suffix}")
    if not (operational_payload.get("evidence") or []):
        lines.append("-")

    if contexts:
        lines.extend(["", "Contextos investigativos:"])
        for item in contexts[:4]:
            title_ctx = _clean_text(item.get("title")) or "Contexto"
            summary_ctx = _clean_text(item.get("summary")) or _clean_text(item.get("rationale")) or "-"
            lines.append(f"- {title_ctx}: {summary_ctx}")

    if draft:
        lines.extend(["", "Draft operacional:", draft])

    return "\n".join(lines).strip() + "\n"


def export_filename(export_format: str, run_id: Any = "", session_id: Any = "") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    identifier = _clean_text(run_id) or _clean_text(session_id) or "analysis"
    safe_identifier = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in identifier)
    if export_format == "json":
        extension = "json"
    elif export_format in {"markdown", "md"}:
        extension = "md"
    else:
        extension = "txt"
    return f"soc_copilot_{safe_identifier}_{stamp}.{extension}"


def serialize_export(bundle: dict[str, Any], export_format: str) -> tuple[str, str]:
    normalized = (export_format or "json").strip().lower()
    if normalized == "json":
        return render_export_json(bundle), "application/json"
    if normalized in {"markdown", "md"}:
        return render_export_markdown(bundle), "text/markdown"
    if normalized == "ticket":
        return render_export_ticket(bundle), "text/plain"
    raise ValueError(f"Unsupported export format: {export_format}")
