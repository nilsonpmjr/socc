"""
Valida o loader declarativo do SOC Copilot e o carregamento de referencias compartilhadas.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from soc_copilot.modules.soc_copilot_loader import (
    build_prompt_context,
    choose_skill,
    load_soc_copilot,
)

PASS = "PASS"
FAIL = "FAIL"
resultados: list[tuple[str, str, str]] = []


def check(nome: str, condicao: bool, detalhe: str = "") -> None:
    status = PASS if condicao else FAIL
    resultados.append((status, nome, detalhe))


try:
    config = load_soc_copilot()
    check("loader_has_schema_path", config.schema_path.exists(), str(config.schema_path))
    check("loader_has_core_skill", "payload-triage" in config.skills)
    check(
        "loader_has_references",
        "evidence-rules" in config.references
        and "output-contract" in config.references
        and "security-json-patterns" in config.references
        and "telemetry-investigation-patterns" in config.references,
    )
    check(
        "loader_reference_content",
        "Facts vs inference" in config.references.get("evidence-rules", ""),
    )
except Exception as exc:
    check("loader_basic_flow", False, str(exc))


try:
    context = build_prompt_context(
        user_input="From: attacker@example.com\nSubject: invoice urgente\nattachment=invoice.zip",
        artifact_type="email",
        session_context="usuario: houve um envio suspeito mais cedo",
    )
    check("context_selects_phishing_skill", context.get("selected_skill") == "phishing-analysis", str(context.get("selected_skill")))
    check("context_has_evidence_rules", "Confidence guidance" in context.get("evidence_rules", ""))
    check("context_has_output_contract", "Required fields" in context.get("output_contract", ""))
    check("context_has_mitre_guidance", "ATT&CK mapping is enrichment" in context.get("mitre_guidance", ""))
    check("context_has_security_json_patterns", "source IP and destination IP" in context.get("security_json_patterns", ""))
    check("context_has_telemetry_patterns", "investigation-ready context" in context.get("telemetry_investigation_patterns", ""))
except Exception as exc:
    check("loader_prompt_context_flow", False, str(exc))


try:
    check("skill_choice_url", choose_skill("https://malicious.example/login") == "suspicious-url")
    check("skill_choice_payload_default", choose_skill("srcip=10.0.0.5 dstip=8.8.8.8 action=blocked") == "payload-triage")
except Exception as exc:
    check("loader_choose_skill_flow", False, str(exc))


print(f"\n{'='*60}")
print(f"SOC Copilot — Loader Declarativo  ({len(resultados)} checks)")
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
