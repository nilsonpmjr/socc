from __future__ import annotations

from typing import Any

from soc_copilot.modules import (
    analysis_contract,
    analysis_export,
    analysis_priority,
    operational_payload,
    analysis_trace,
    draft_engine,
    rule_loader,
    semi_llm_adapter,
    telemetry_context,
)


LEGACY_MODULES = {
    "rule_loader": "soc_copilot.modules.rule_loader",
    "semi_llm_adapter": "soc_copilot.modules.semi_llm_adapter",
    "draft_engine": "soc_copilot.modules.draft_engine",
    "analysis_contract": "soc_copilot.modules.analysis_contract",
    "analysis_priority": "soc_copilot.modules.analysis_priority",
    "operational_payload": "soc_copilot.modules.operational_payload",
    "analysis_trace": "soc_copilot.modules.analysis_trace",
    "analysis_export": "soc_copilot.modules.analysis_export",
    "telemetry_context": "soc_copilot.modules.telemetry_context",
}

RulePack = rule_loader.RulePack


def load_rule_pack(regra: str = "", cliente: str = "") -> RulePack:
    return rule_loader.load(regra=regra, cliente=cliente)


def run_analysis(
    *,
    fields: dict[str, Any],
    ti_results: dict[str, str],
    raw_text: str,
    regra: str,
    cliente: str,
    pack: RulePack,
    knowledge_context: str = "",
    knowledge_sources: str = "",
) -> dict[str, Any]:
    return semi_llm_adapter.run(
        fields=fields,
        ti_results=ti_results,
        raw_text=raw_text,
        regra=regra,
        cliente=cliente,
        pack=pack,
        knowledge_context=knowledge_context,
        knowledge_sources=knowledge_sources,
    )


def generate_draft(
    classificacao: str,
    fields: dict[str, Any],
    ti_results: dict[str, str],
    pack: RulePack,
    analysis: dict[str, Any],
) -> tuple[str, str]:
    return draft_engine.generate(classificacao, fields, ti_results, pack, analysis)


def build_structured_analysis(
    *,
    analysis: dict[str, Any],
    fields: dict[str, Any],
    ti_results: dict[str, str],
) -> dict[str, Any]:
    return analysis_contract.build_structured_analysis(
        analysis=analysis,
        fields=fields,
        ti_results=ti_results,
    )


def build_analysis_priority(
    *,
    analysis: dict[str, Any],
    fields: dict[str, Any],
    ti_results: dict[str, str],
) -> dict[str, Any]:
    return analysis_priority.build_analysis_priority(
        analysis=analysis,
        fields=fields,
        ti_results=ti_results,
    )


def build_operational_payload(
    *,
    metadata: dict[str, Any] | None = None,
    fields: dict[str, Any],
    analysis_structured: dict[str, Any],
    analysis_priority: dict[str, Any],
    analysis_trace: dict[str, Any],
    analysis_legacy: dict[str, Any] | None = None,
    draft: str = "",
) -> dict[str, Any]:
    return operational_payload.build_operational_payload(
        metadata=metadata,
        fields=fields,
        analysis_structured=analysis_structured,
        analysis_priority=analysis_priority,
        analysis_trace=analysis_trace,
        analysis_legacy=analysis_legacy,
        draft=draft,
    )


def validate_structured_analysis(data: Any) -> list[str]:
    return analysis_contract.validate_structured_analysis(data)


def build_analysis_trace(
    *,
    fields: dict[str, Any],
    analysis: dict[str, Any],
    ti_results: dict[str, str],
) -> dict[str, Any]:
    return analysis_trace.build_analysis_trace(
        fields=fields,
        analysis=analysis,
        ti_results=ti_results,
    )


def enrich_analysis_with_contexts(
    *,
    analysis: dict[str, Any],
    fields: dict[str, Any],
    ti_results: dict[str, str],
    raw_text: str,
) -> dict[str, Any]:
    return telemetry_context.enrich_analysis_with_contexts(
        analysis=analysis,
        fields=fields,
        ti_results=ti_results,
        raw_text=raw_text,
    )


def build_export_bundle(
    *,
    metadata: dict[str, Any],
    fields: dict[str, Any],
    ti_results: dict[str, str],
    analysis_structured: dict[str, Any],
    analysis_priority: dict[str, Any],
    analysis_trace: dict[str, Any],
    operational_payload: dict[str, Any] | None = None,
    draft: str,
    analysis_legacy: dict[str, Any] | None = None,
    **legacy_kwargs: Any,
) -> dict[str, Any]:
    return analysis_export.build_export_bundle(
        metadata=metadata,
        fields=fields,
        ti_results=ti_results,
        analysis_structured=analysis_structured,
        analysis_priority=analysis_priority,
        analysis_trace=analysis_trace,
        operational_payload=operational_payload,
        draft=draft,
        analysis_legacy=analysis_legacy,
        **legacy_kwargs,
    )


def export_filename(export_format: str, run_id: Any = "", session_id: Any = "") -> str:
    return analysis_export.export_filename(export_format, run_id=run_id, session_id=session_id)


def serialize_export(bundle: dict[str, Any], export_format: str) -> tuple[str, str]:
    return analysis_export.serialize_export(bundle, export_format)
