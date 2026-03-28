"""
Valida a priorizacao estruturada derivada da analise.
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
    high = analyze_payload(
        payload_text='{"sender.address":"phish@example.com","recipient.address":"victim@example.org","subject":"Invoice","url.full":"https://evil.example.com/login","authentication.result":"failure","mfaUsed":"false","sourceIPAddress":"198.51.100.77","process.name":"powershell.exe","process.command_line":"powershell.exe -enc AAAA","registry.path":"HKCU\\\\Software\\\\Microsoft\\\\Windows\\\\CurrentVersion\\\\Run\\\\Updater"}',
        include_draft=False,
    )
    low = analyze_payload(
        payload_text='{"src_ip":"10.0.0.5","dst_ip":"192.168.1.10","action":"allow","devname":"fw-interno","msg":"atividade esperada de monitoramento"}',
        include_draft=False,
    )

    high_priority = high.get("analysis_priority", {})
    low_priority = low.get("analysis_priority", {})

    check("analysis_priority_high_present", isinstance(high_priority, dict) and bool(high_priority))
    check("analysis_priority_low_present", isinstance(low_priority, dict) and bool(low_priority))
    check("analysis_priority_score_order", (high_priority.get("score") or 0) > (low_priority.get("score") or 0))
    check("analysis_priority_rank_order", (high_priority.get("rank") or 9) < (low_priority.get("rank") or 9))
    check("analysis_priority_level_high", high_priority.get("level") in {"alta", "critica"})
    check("analysis_priority_family_high", high_priority.get("primary_family") in {"email_auth", "process_endpoint"})
    check("analysis_priority_label_high", bool(high_priority.get("primary_label")))
    check("analysis_priority_reasons_high", isinstance(high_priority.get("reasons"), list) and len(high_priority.get("reasons")) >= 1)
    check("analysis_priority_rationale_high", bool(high_priority.get("rationale")))
except Exception as exc:
    check("analysis_priority_flow", False, str(exc))


print(f"\n{'='*60}")
print(f"SOC Copilot — Analysis Priority  ({len(resultados)} checks)")
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
