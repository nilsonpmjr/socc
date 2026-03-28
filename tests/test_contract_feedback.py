"""
Valida o contrato oficial de analise e o fluxo de feedback do analista.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from socc.core.engine import analyze_payload
from soc_copilot.modules import persistence
from soc_copilot.modules.analysis_contract import validate_structured_analysis

PASS = "PASS"
FAIL = "FAIL"
resultados: list[tuple[str, str, str]] = []


def check(nome: str, condicao: bool, detalhe: str = "") -> None:
    status = PASS if condicao else FAIL
    resultados.append((status, nome, detalhe))


tmpdir = tempfile.TemporaryDirectory()
db_path = Path(tmpdir.name) / "test_socc.db"
persistence.DB_PATH = db_path
persistence.init_db()

# ---------------------------------------------------------------------------
# 1. Engine retorna contrato oficial valido
# ---------------------------------------------------------------------------
try:
    result = analyze_payload(
        payload_text="srcip=10.0.0.5 dstip=192.168.1.20 action=blocked devname=FW1 logid=0001",
        include_draft=True,
    )
    structured = result.get("analysis_structured", {})
    errors = validate_structured_analysis(structured)
    check("engine_structured_present", isinstance(structured, dict) and bool(structured))
    check("engine_structured_valid", not errors, "; ".join(errors))
    check("engine_structured_has_iocs", len(structured.get("iocs", [])) >= 1)
except Exception as exc:
    check("engine_structured_flow", False, str(exc))


# ---------------------------------------------------------------------------
# 2. Persistencia do feedback vincula run e payload
# ---------------------------------------------------------------------------
try:
    payload = "srcip=10.0.0.5 dstip=192.168.1.20 action=blocked devname=FW1 logid=0001"
    analyze_result = analyze_payload(payload_text=payload, include_draft=False)
    payload_hash = persistence.hash_input(payload)
    run_id = persistence.save_run(
        ofensa_id="CASE-1",
        cliente="Teste",
        regra="Teste",
        raw_input=payload,
        classificacao="TP",
        template_usado="template_teste",
    )
    persistence.save_analysis(
        run_id=run_id,
        analysis=analyze_result.get("analysis", {}),
        structured_analysis=analyze_result.get("analysis_structured", {}),
    )
    feedback_id = persistence.save_feedback(
        run_id=run_id,
        payload_hash=payload_hash,
        feedback_type="correct",
        verdict_correction="suspeito",
        comments="A resposta precisa de mais contexto antes de virar malicioso.",
        source="test-suite",
    )
    run = persistence.get_run(run_id)
    check("feedback_run_saved", bool(run) and run.get("id") == run_id)
    check("feedback_payload_hash", payload_hash == persistence.hash_input(payload))
    check("feedback_id_created", bool(feedback_id))
except Exception as exc:
    check("contract_feedback_persistence_flow", False, str(exc))


print(f"\n{'='*60}")
print(f"SOC Copilot — Contrato + Feedback  ({len(resultados)} checks)")
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

tmpdir.cleanup()
sys.exit(1 if falhas else 0)
