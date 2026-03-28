"""
Valida trilha analitica e exportacao operacional da analise.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from socc.core.engine import analyze_payload
from soc_copilot.modules.analysis_export import (
    build_export_bundle,
    render_export_json,
    render_export_markdown,
)

PASS = "PASS"
FAIL = "FAIL"
resultados: list[tuple[str, str, str]] = []


def check(nome: str, condicao: bool, detalhe: str = "") -> None:
    status = PASS if condicao else FAIL
    resultados.append((status, nome, detalhe))


try:
    result = analyze_payload(
        payload_text='{"srcip": "203.0.113.10", "dstip": "198.51.100.8", "action": "blocked", "msg": "port scan", "serverName": "fw01", "TargetFilename": "malware.exe", "fileHash": "1e8a68027db8e05c87e795c65acfa76b", "sender.address": "phish@example.com", "dns.question.name": "evil.example.com", "url.full": "https://evil.example.com/login"}',
        include_draft=True,
    )
    trace = result.get("analysis_trace", {})
    check("trace_observed_facts_present", len(trace.get("observed_facts", [])) >= 2)
    check("trace_inferences_present", len(trace.get("inferences", [])) >= 1)
    observed_labels = {item.get("label") for item in trace.get("observed_facts", []) if isinstance(item, dict)}
    check("trace_has_server_fact", "Servidor" in observed_labels)
    check("trace_has_file_fact", "Arquivo" in observed_labels)
    check("trace_has_hash_fact", "Hash Observado" in observed_labels)
    check("trace_has_email_fact", "Email Remetente" in observed_labels)
    check("trace_has_dns_fact", "DNS Consulta" in observed_labels)
    check("trace_has_url_fact", "URL Completa" in observed_labels)

    bundle = build_export_bundle(
        metadata={"run_id": 42, "cliente": "Teste", "classificacao": "TP"},
        fields=result.get("fields", {}),
        ti_results={},
        analysis_structured=result.get("analysis_structured", {}),
        analysis_priority=result.get("analysis_priority", {}),
        analysis_trace=trace,
        draft=result.get("draft", ""),
        analysis_legacy=result.get("analysis", {}),
    )
    exported_json = render_export_json(bundle)
    exported_md = render_export_markdown(bundle)

    check("export_json_has_summary", '"analysis_structured"' in exported_json and '"summary"' in exported_json)
    check("export_json_has_priority", '"analysis_priority"' in exported_json and '"score"' in exported_json)
    check("export_markdown_has_sections", "## Observed Facts" in exported_md and "## Inferences" in exported_md)
    check("export_markdown_has_priority", "## Priority" in exported_md)
    check("export_markdown_has_draft", "## Draft" in exported_md)
    check("export_markdown_has_contexts", "## Investigative Contexts" in exported_md)
    check("export_json_has_file_ioc", '"type": "file"' in exported_json)
    check("export_json_has_hash_ioc", '"type": "hash"' in exported_json)
    check("export_json_has_email_ioc", '"type": "email"' in exported_json)
    check("export_json_has_domain_ioc", '"type": "domain"' in exported_json)
    check("export_json_has_url_ioc", '"type": "url"' in exported_json)
except Exception as exc:
    check("trace_export_flow", False, str(exc))


print(f"\n{'='*60}")
print(f"SOC Copilot — Trace + Export  ({len(resultados)} checks)")
print("="*60)
falhas = [(n, d) for s, n, d in resultados if s == FAIL]
aprovados = len(resultados) - len(falhas)
print(f"  Aprovados : {aprovados}/{len(resultados)}")
print(f"  Falhas    : {len(falhas)}/{len(resultados)}")
print()
for nome, detalhe in falhas:
    extra = f" — {detalhe}" if detalhe else ""
    print(f"  FALHA: {nome}{extra}")
if not falhas:
    print("  Todos os checks passaram.")
print()

sys.exit(1 if falhas else 0)
