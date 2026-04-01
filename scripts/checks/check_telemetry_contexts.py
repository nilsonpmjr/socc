"""
Valida contextos investigativos derivados das novas familias de telemetria.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from socc.core.engine import analyze_payload

PASS = "PASS"
FAIL = "FAIL"
resultados: list[tuple[str, str, str]] = []


def check(nome: str, condicao: bool, detalhe: str = "") -> None:
    status = PASS if condicao else FAIL
    resultados.append((status, nome, detalhe))


try:
    result = analyze_payload(
        payload_text=(
            '{"sender.address":"phish@example.com","recipient.address":"victim@example.org",'
            '"subject":"Payroll update","url.full":"https://evil.example.com/login",'
            '"dns.question.name":"evil.example.com","http.host":"evil.example.com",'
            '"authentication.result":"failure","mfaUsed":"false",'
            '"sourceIPAddress":"198.51.100.77","destinationIPAddress":"203.0.113.10",'
            '"process.name":"powershell.exe","process.command_line":"powershell.exe -enc AAAA",'
            '"registry.path":"HKCU\\\\Software\\\\Microsoft\\\\Windows\\\\CurrentVersion\\\\Run\\\\Updater",'
            '"bytes_in":512,"bytes_out":4096,'
            '"accountId":"123456789012","resourceId":"i-0abc123","roleArn":"arn:aws:iam::123456789012:role/Admin",'
            '"kubernetes.pod.name":"frontend-abc","kubernetes.namespace":"prod","container.id":"docker://abc123"}'
        ),
        include_draft=True,
    )
    analysis = result.get("analysis", {})
    structured = result.get("analysis_structured", {})
    trace = result.get("analysis_trace", {})
    draft = result.get("draft", "")
    contexts = analysis.get("contextos_investigativos", [])
    context_ids = {item.get("id") for item in contexts if isinstance(item, dict)}

    check("telemetry_contexts_present", len(contexts) >= 5)
    check("telemetry_context_email", "email_phishing_delivery" in context_ids)
    check("telemetry_context_auth", "external_auth_pressure" in context_ids)
    check("telemetry_context_web", "suspicious_web_channel" in context_ids)
    check("telemetry_context_lolbin", "lolbin_execution" in context_ids)
    check("telemetry_context_persistence", "persistence_registry_service" in context_ids)
    check("telemetry_context_exfil", "outbound_exfiltration_signal" in context_ids)
    check("telemetry_context_cloud", "cloud_identity_scope" in context_ids)
    check("telemetry_context_k8s", "kubernetes_workload_scope" in context_ids)

    statements = {item.get("statement", "") for item in trace.get("inferences", []) if isinstance(item, dict)}
    check(
        "telemetry_context_trace",
        any("Contexto investigativo" in statement for statement in statements),
    )
    ttps = {item.get("id") for item in structured.get("ttps", []) if isinstance(item, dict)}
    check("telemetry_context_ttp_phishing", "T1566" in ttps)
    check("telemetry_context_ttp_web", "T1071.001" in ttps)
    check("telemetry_context_ttp_persistence", "T1547.001" in ttps)
    check("telemetry_context_sources", "telemetry_context" in (structured.get("sources") or []))
    risk_reasons = " | ".join(structured.get("risk_reasons") or [])
    check("telemetry_context_risk_reason", "phishing" in risk_reasons.lower() or "telemetria envolve" in risk_reasons.lower())
    recommended_actions = " | ".join(structured.get("recommended_actions") or [])
    check("telemetry_context_actions", "reputacao do remetente" in recommended_actions.lower() or "revisar trilha de auditoria" in recommended_actions.lower())
    check("telemetry_context_draft_priority", "Prioridade Operacional: Alta" in draft)
    check("telemetry_context_draft_highlight", "Contextos investigativos prioritários:" in draft or "Contexto investigativo prioritário:" in draft)
except Exception as exc:
    check("telemetry_context_flow", False, str(exc))


print(f"\n{'='*60}")
print(f"SOC Copilot — Telemetry Contexts  ({len(resultados)} checks)")
print("=" * 60)
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
